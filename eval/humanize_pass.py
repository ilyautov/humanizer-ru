#!/usr/bin/env python3
"""Отпечаток самого хуманайзера: во что превращается текст после нашего скилла.

Три вопроса, на которые отвечает этот прогон.

1. Куда сдвигается текст. Скор говорит «стало лучше», но скор мерит расстояние
   до нуля, а не до человека. Человек нулём не бывает: на текстах в 200-400 слов
   полностью чистых людей 15%, а не 100%. Значит выход скилла надо мерить
   расстоянием до человеческого распределения, и «сто из ста» может оказаться
   попаданием в редкий хвост, а не в середину.

2. Переживает ли отпечаток базовой модели. Каталог снимает то, что у моделей
   общего; идиосинкразия каждой в каталог не попала именно потому, что не общая.
   Если после скилла тексты gemma и qwen всё ещё разделяются, значит
   «Claude плюс хуманайзер» это своя подпись, а не человек.

3. Не заводит ли скилл собственную подпись. Общая для всех, кто им пользуется:
   для одного автора это выигрыш, для корпуса на сто тысяч документов проигрыш.

Про исполнителя. Скилл рассчитан на фронтир-модель, и запуск его на локальной
27B меряет способность gemma следовать инструкции на 25 тысяч токенов, а не сам
скилл. Поэтому локальный прогон помечается в выходе как `proxy`, а честный ответ
даёт удалённый бэкенд (у Gemini бесплатный тариф с окном на миллион токенов).

Отдельная грабля: Ollama по умолчанию режет окно до 4096 токенов молча. Без
явного num_ctx модель увидит инструкцию покалеченной и ошибки не будет.

Запуск:
    python eval/humanize_pass.py --cells gemma3-27b__P1-перепиши qwen3-4b__P1-перепиши
    python eval/humanize_pass.py --model 'google|gemini-2.5-flash' --cells все
    python eval/humanize_pass.py --report
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "eval"))
sys.path.insert(0, str(ROOT / "skills" / "humanizer-ru" / "scripts"))

import remote_backend  # noqa: E402
from author_profiles import distance, profile  # noqa: E402
from llm_backend import generate  # noqa: E402
from m4_calibration import is_russian  # noqa: E402

from humanizer_metrics.markers import (  # noqa: E402
    effective_hard_bans,
    scan_hard_bans,
    scan_markers,
)

CELLS_DIR = ROOT / "eval" / "out" / "matrix"
OUT = ROOT / "eval" / "out" / "humanized"
SKILL = ROOT / "skills" / "humanizer-ru" / "SKILL.md"

TASK = ("\n\n---\n\nПрименяя инструкцию выше, перепиши текст ниже. "
        "Верни только переписанный текст, без комментариев и разметки.\n\n{text}")


def score(text: str) -> tuple[int, float]:
    """Банов в документе и маркеров на 100 слов. Обе метрики нашего сканера."""
    words = len(text.split())
    bans = len(effective_hard_bans(scan_hard_bans(text), words))
    marks = 100.0 * sum(h.count for h in scan_markers(text)) / max(1, words)
    return bans, marks


def run(cell: Path, model: str, workers: int, num_ctx: int) -> int:
    provider, name = remote_backend.parse_target(model)
    prompt_head = SKILL.read_text(encoding="utf-8")
    recs = [json.loads(s) for s in cell.read_text(encoding="utf-8").splitlines() if s]
    lock, done = threading.Lock(), {"n": 0}
    out_path = OUT / f"{cell.stem}__by-{name.replace('/', '_').replace(':', '-')}.jsonl"

    def work(rec: dict, fh) -> None:
        prompt = prompt_head + TASK.format(text=rec["machine_text"])
        out = (remote_backend.generate(prompt, name, provider, num_predict=1600) if provider
               else generate(prompt, num_predict=1600, temperature=0.3, model=name,
                             timeout=1200, num_ctx=num_ctx))
        if not out or not is_russian(out):
            return
        with lock:
            fh.write(json.dumps({**rec, "humanized_text": out.strip(),
                                 "humanizer": model,
                                 "proxy": provider is None}, ensure_ascii=False) + "\n")
            fh.flush()
            done["n"] += 1

    OUT.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            list(pool.map(lambda r: work(r, fh), recs))
    print(f"    переписано: {done['n']} -> {out_path.name}", file=sys.stderr)
    return done["n"]


def report() -> int:
    files = sorted(OUT.glob("*.jsonl")) if OUT.exists() else []
    if not files:
        print("[пусто] прогонов нет, запустите без --report", file=sys.stderr)
        return 1

    human_texts, rows, profiles = [], [], {}
    for path in files:
        recs = [json.loads(s) for s in path.read_text(encoding="utf-8").splitlines() if s]
        if not recs:
            continue
        human_texts.extend(r["human_text"] for r in recs)
        before = [score(r["machine_text"]) for r in recs]
        after = [score(r["humanized_text"]) for r in recs]
        rows.append({
            "cell": path.stem, "n": len(recs), "proxy": recs[0].get("proxy", True),
            "ban_before": 100.0 * sum(1 for b, _ in before if b) / len(recs),
            "ban_after": 100.0 * sum(1 for b, _ in after if b) / len(recs),
            "marks_before": statistics.mean(m for _, m in before),
            "marks_after": statistics.mean(m for _, m in after),
        })
        profiles[path.stem] = profile([r["humanized_text"] for r in recs])

    human = profile(human_texts)
    head = f"{'прогон':<46}{'n':>4}{'бан до':>9}{'бан после':>11}{'марк до':>9}{'марк после':>12}"
    print(head)
    print("-" * len(head))
    for r in sorted(rows, key=lambda r: r["cell"]):
        print(f"{r['cell'][:45]:<46}{r['n']:>4}{r['ban_before']:>8.1f}%{r['ban_after']:>10.1f}%"
              f"{r['marks_before']:>9.2f}{r['marks_after']:>12.2f}")
    if any(r["proxy"] for r in rows):
        print("\n[осторожно] прогоны с proxy=истина считались локальной моделью: они мерят\n"
              "            её способность следовать инструкции, а не сам скилл.")

    print(f"\nрасстояние до человеческого профиля (п.п., меньше значит ближе к человеку):")
    print(f"  {'человек сам с собой (база)':<44}{0.0:>7.2f}")
    for name, prof in sorted(profiles.items()):
        print(f"  {name[:43]:<44}{distance(prof, human):>7.2f}")

    if len(profiles) > 1:
        names = sorted(profiles)
        pairs = [(a, b, distance(profiles[a], profiles[b]))
                 for i, a in enumerate(names) for b in names[i + 1:]]
        print("\nрасстояние между прогонами (жив ли отпечаток базовой модели):")
        for a, b, d in pairs:
            print(f"  {a[:28]:<30}{b[:28]:<30}{d:>7.2f}")

    out = ROOT / "eval" / "out" / "humanized.json"
    out.write_text(json.dumps({
        "runs": rows,
        "distance_to_human_pp": {k: round(distance(v, human), 2) for k, v in profiles.items()},
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[ok] -> {out.relative_to(ROOT)}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cells", nargs="*", help="имена ячеек матрицы без .jsonl; пусто = все")
    ap.add_argument("--model", default="gemma3:27b",
                    help="кто исполняет скилл; удалённый как 'google|gemini-2.5-flash'")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--num-ctx", type=int, default=32768,
                    help="окно локальной модели; SKILL.md это около 25 тысяч токенов")
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args()

    if args.report:
        return report()
    cells = [CELLS_DIR / f"{c}.jsonl" for c in args.cells] if args.cells \
        else sorted(CELLS_DIR.glob("*.jsonl"))
    cells = [c for c in cells if c.exists()]
    if not cells:
        print("[ошибка] ячеек матрицы не найдено", file=sys.stderr)
        return 1
    for i, cell in enumerate(cells, 1):
        print(f"[{i}/{len(cells)}] {cell.stem} через {args.model}", file=sys.stderr)
        run(cell, args.model, args.workers, args.num_ctx)
    print("\n[ok] дальше: python eval/humanize_pass.py --report")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
