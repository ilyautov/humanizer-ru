#!/usr/bin/env python3
"""CLI-сканер: прогоняет текст через детерминированные метрики humanizer-ru.

Использование (из корня репо; у установленного скилла путь: <папка скилла>/scripts/scan.py):
    python skills/humanizer-ru/scripts/scan.py path/to/text.txt
    echo "ваш текст" | python skills/humanizer-ru/scripts/scan.py -
    python skills/humanizer-ru/scripts/scan.py text.txt --json

Это машинная половина режима «Аудит». Для полного очеловечивания (семантика,
голос, рерайт) нужен сам скилл — этот сканер только подсвечивает грепабельные
маркеры и считает метрики, которые LLM не умеет мерить на глаз.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from humanizer_metrics import analyze, cleanliness_score
    from humanizer_metrics.burstiness import rhythm_verdict
    from humanizer_metrics.markers import effective_hard_bans, marker_verdict
    from humanizer_metrics.morphology import morph_verdict
    from humanizer_metrics.structure import structure_verdict
except ImportError as exc:
    print(f"[ошибка] не хватает зависимостей сканера ({exc.name}).\n"
          "Поставьте один раз: pip install razdel pymorphy3", file=sys.stderr)
    raise SystemExit(2)


def _read(src: str) -> str:
    if src == "-":
        return sys.stdin.read()
    try:
        return Path(src).read_text(encoding="utf-8")
    except FileNotFoundError:
        print(f"[ошибка] файл не найден: {src}", file=sys.stderr)
        raise SystemExit(2)
    except (IsADirectoryError, UnicodeDecodeError) as exc:
        print(f"[ошибка] не могу прочитать {src}: {exc}", file=sys.stderr)
        raise SystemExit(2)


def _line_numbers(text: str, positions: list[int], limit: int = 3) -> str:
    """Номера строк первых вхождений: «стр. 3, 7» — чтобы находку можно
    было найти в тексте глазами."""
    lines = sorted({text.count("\n", 0, p) + 1 for p in positions})
    shown = ", ".join(str(n) for n in lines[:limit])
    more = f", +{len(lines) - limit}" if len(lines) > limit else ""
    return f"стр. {shown}{more}"


def _cyrillic_share(text: str) -> float:
    letters = re.findall(r"[^\W\d_]", text)
    if not letters:
        return 0.0
    cyr = sum(1 for ch in letters if "а" <= ch.lower() <= "я" or ch.lower() == "ё")
    return cyr / len(letters)


def main() -> int:
    ap = argparse.ArgumentParser(description="Детерминированный сканер AI-маркеров (humanizer-ru)")
    ap.add_argument("source", help="файл с текстом или '-' для stdin")
    ap.add_argument("--json", action="store_true", help="вывод в JSON")
    args = ap.parse_args()

    text = _read(args.source)

    if not text.strip():
        if args.json:
            print(json.dumps({"empty": True}, ensure_ascii=False))
        else:
            print("Текст пуст, сканировать нечего.")
        return 0

    rep = analyze(text)
    sc = cleanliness_score(rep)
    # Частотные баны («Является» до порога 1/500 слов) не валят exit и не
    # показываются как ⛔ — они остаются в мягких маркерах.
    bans = effective_hard_bans(rep.hard_bans, rep.rhythm.words)

    if args.json:
        out = rep.as_dict()
        out["score"] = sc.as_dict()
        if _cyrillic_share(text) < 0.3:
            out["warning"] = "текст не похож на русский, метрики не применимы"
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 1 if bans else 0

    print(f"=== humanizer-ru scan: {args.source} ===\n")

    if _cyrillic_share(text) < 0.3:
        print("⚠ Текст не похож на русский: скилл и метрики рассчитаны на русский "
              "язык, отчёт ниже не показателен.\n")

    print(f"ЧИСТОТА: {sc.score}/100  [{sc.band}]")
    print("  (≥85 чисто · 60-84 точечная правка · <60 рерайт)")
    if sc.penalties:
        for reason, pts in sc.penalties:
            print(f"  {pts:+d}  {reason}")
    else:
        print("  без штрафов")
    print()

    print("HARD BANS:")
    if bans:
        for h in bans:
            note = " (штраф по плотности, допуск ~2/100 слов)" if h.marker == "Длинное тире" else ""
            print(f"  ⛔ {h.marker} ×{h.count} ({_line_numbers(text, h.positions)}){note}")
    else:
        print("  ✓ чисто")
    print()

    print(f"Маркеры (быстрый сканер): {marker_verdict(rep.markers)}")
    top = sorted(rep.markers, key=lambda x: -x.count)
    for h in top[:12]:
        print(f"  • [{h.category}] «{h.marker}» ×{h.count} ({_line_numbers(text, h.positions)})")
    if len(top) > 12:
        print(f"  … и ещё {len(top) - 12}")
    print()

    print("Ритм / типографика:")
    print(f"  {rhythm_verdict(rep.rhythm)}")
    print(f"  предложений: {rep.rhythm.sentences}, средняя длина: {rep.rhythm.mean_len:.1f} "
          f"(min {rep.rhythm.min_len} / max {rep.rhythm.max_len}), CV: {rep.rhythm.cv_len}")
    print(f"  многоточий: {rep.rhythm.ellipsis}, скобок: {rep.rhythm.parentheses}, "
          f"вопросов: {rep.rhythm.questions}")
    print()

    print("Морфология:")
    print(f"  {morph_verdict(rep.morph)}")
    print(f"  сущ.: {rep.morph.nouns}, глаг.форм: {rep.morph.verbs}, "
          f"номинализаций: {rep.morph.nominalizations}")
    print()

    print("Структура (уровень документа):")
    print(f"  {structure_verdict(rep.structure)}")

    # Exit code: ненулевой, если есть HARD BANS — удобно для CI/pre-commit.
    return 1 if bans else 0


if __name__ == "__main__":
    raise SystemExit(main())
