#!/usr/bin/env python3
"""CLI-сканер: прогоняет текст через детерминированные метрики humanizer-ru.

Использование:
    python scripts/scan.py path/to/text.txt
    echo "ваш текст" | python scripts/scan.py -
    python scripts/scan.py text.txt --json

Это машинная половина режима «Аудит». Для полного очеловечивания (семантика,
голос, рерайт) нужен сам скилл — этот сканер только подсвечивает грепабельные
маркеры и считает метрики, которые LLM не умеет мерить на глаз.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from humanizer_metrics import analyze
from humanizer_metrics.burstiness import rhythm_verdict
from humanizer_metrics.markers import marker_verdict
from humanizer_metrics.morphology import morph_verdict


def _read(src: str) -> str:
    if src == "-":
        return sys.stdin.read()
    return Path(src).read_text(encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Детерминированный сканер AI-маркеров (humanizer-ru)")
    ap.add_argument("source", help="файл с текстом или '-' для stdin")
    ap.add_argument("--json", action="store_true", help="вывод в JSON")
    args = ap.parse_args()

    text = _read(args.source)
    rep = analyze(text)

    if args.json:
        print(json.dumps(rep.as_dict(), ensure_ascii=False, indent=2))
        return 1 if rep.hard_ban_count else 0

    print(f"=== humanizer-ru scan: {args.source} ===\n")

    print("HARD BANS:")
    if rep.hard_bans:
        for h in rep.hard_bans:
            print(f"  ⛔ {h.marker} ×{h.count}")
    else:
        print("  ✓ чисто")
    print()

    print(f"Маркеры (быстрый сканер): {marker_verdict(rep.markers)}")
    for h in sorted(rep.markers, key=lambda x: -x.count)[:12]:
        print(f"  • [{h.category}] «{h.marker}» ×{h.count}")
    print()

    print("Ритм / типографика:")
    print(f"  {rhythm_verdict(rep.rhythm)}")
    print(f"  предложений: {rep.rhythm.sentences}, средняя длина: {rep.rhythm.mean_len} "
          f"(min {rep.rhythm.min_len} / max {rep.rhythm.max_len}), CV: {rep.rhythm.cv_len}")
    print(f"  многоточий: {rep.rhythm.ellipsis}, скобок: {rep.rhythm.parentheses}, "
          f"вопросов: {rep.rhythm.questions}")
    print()

    print("Морфология:")
    print(f"  {morph_verdict(rep.morph)}")
    print(f"  сущ.: {rep.morph.nouns}, глаг.форм: {rep.morph.verbs}, "
          f"номинализаций: {rep.morph.nominalizations}")

    # Exit code: ненулевой, если есть HARD BANS — удобно для CI/pre-commit.
    return 1 if rep.hard_ban_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
