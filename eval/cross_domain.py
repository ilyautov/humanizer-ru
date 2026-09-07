#!/usr/bin/env python3
"""Проверка добытых кандидатов на втором домене: что переживает смену регистра.

Зачем отдельный шаг. `mine_patterns.py` держит кандидата, если он разделяет
классы внутри одного корпуса, и честно предупреждает, что этого мало: маркер без
указания домена бессмысленен (см. SOURCES.md). Пока второго русского корпуса не
было, фильтр оставался словами в документации. Теперь их два, и проверка стала
исполнимой: добываем на AINL (научные аннотации), меряем на M4 (национальный
корпус, новости, соцсети) или на своём парном корпусе блогов.

Что считает:
  1. Плотность всех кандидатов на 100 слов по сторонам — грубая проверка, что
     набор вообще переносится.
  2. Пофразный лифт на втором корпусе и список переживших.

Порог держим тот же, что в шахте: опора не ниже `--min-support` процентов
машинных документов и лифт не ниже `--min-lift`. Кандидат, который на втором
домене не набирает опоры, не «слабый» — он просто про первый домен.

Запуск:
    python eval/mine_patterns.py --split train        # даст mined-train.json
    python eval/cross_domain.py                       # проверить на M4
    python eval/cross_domain.py --jsonl eval/out/blog-pairs.jsonl
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "eval"))

from m4_calibration import FILES, is_russian, load  # noqa: E402
from mine_patterns import MAX_N, MIN_N, _deps, build_lemmatizer, doc_sentences  # noqa: E402


def load_pairs(jsonl: Path | None, limit: int | None) -> list[tuple[str, str, str]]:
    """Пары (модель, человеческий текст, машинный текст) из M4 или своего файла."""
    pairs = []
    if jsonl:
        for line in jsonl.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                pairs.append((r.get("model", "machine"),
                              r.get("human_text", ""), r.get("machine_text", "")))
        return pairs
    for model in FILES:
        for row in load(model, limit):
            pairs.append((model, row.get("human_text", ""), row.get("machine_text", "")))
    return pairs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mined", type=Path, default=ROOT / "eval" / "out" / "mined-train.json",
                    help="выход mine_patterns.py с кандидатами")
    ap.add_argument("--jsonl", type=Path, help="свой парный корпус вместо M4")
    ap.add_argument("--limit", type=int, help="взять только первые N записей на генератор")
    ap.add_argument("--min-support", type=float, default=0.5,
                    help="минимум процентов машинных документов на втором корпусе")
    ap.add_argument("--min-lift", type=float, default=2.0, help="минимум AI/человек")
    ap.add_argument("--top", type=int, default=25)
    args = ap.parse_args()

    cands = json.loads(args.mined.read_text(encoding="utf-8"))["candidates"]
    # Кандидат — это лемма-n-грамма; ключом служит она сама, а не пример из
    # отчёта: пример это одна словоформа из корпуса, по нему искать нельзя.
    key_idx = {tuple(r["ngram"].split()): i for i, r in enumerate(cands)}
    morph, sentenize, tokenize = _deps()
    lemma = build_lemmatizer(morph)

    totals: dict[str, int] = defaultdict(int)
    density: dict[str, list[float]] = defaultdict(list)
    per_cand: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    models: list[str] = []

    pairs = load_pairs(args.jsonl, args.limit)
    print(f"[инфо] пар: {len(pairs)}", file=sys.stderr)
    for i, (model, human, machine) in enumerate(pairs):
        if not (is_russian(human) and is_russian(machine)):
            continue
        if model not in models:
            models.append(model)
        for side, text in (("human", human), (model, machine)):
            hits = set()
            for lemmas, _ in doc_sentences(text, sentenize, tokenize, lemma):
                for n in range(MIN_N, MAX_N + 1):
                    for k in range(len(lemmas) - n + 1):
                        j = key_idx.get(tuple(lemmas[k:k + n]))
                        if j is not None:
                            hits.add(j)
            totals[side] += 1
            density[side].append(100.0 * len(hits) / max(1, len(text.split())))
            for j in hits:
                per_cand[j][side] += 1
        if i and i % 1000 == 0:
            print(f"  …{i}/{len(pairs)}", file=sys.stderr)

    sides = ["human"] + models
    corpus = args.jsonl.name if args.jsonl else "M4-ru"
    print(f"\nплотность кандидатов на 100 слов, корпус {corpus}:")
    for s in sides:
        if totals[s]:
            print(f"  {s:<16}{statistics.mean(density[s]):>7.2f}  (документов {totals[s]})")

    held = []
    for j, r in enumerate(cands):
        human = 100.0 * per_cand[j]["human"] / totals["human"] if totals["human"] else 0.0
        ai = statistics.mean([100.0 * per_cand[j][m] / totals[m] for m in models if totals[m]])
        if ai >= args.min_support and human * args.min_lift <= ai:
            held.append({**r, "x_human": round(human, 2), "x_ai": round(ai, 2),
                         "x_lift": round(ai / human, 1) if human else None})

    print(f"\nпережили смену домена (лифт>={args.min_lift}, опора>={args.min_support}%): "
          f"{len(held)} из {len(cands)}")
    head = f"{'кандидат':<38}{'исх. lift':>10}{'чел.%':>9}{'AI%':>8}{'lift':>8}"
    print(head)
    print("-" * len(head))
    for r in sorted(held, key=lambda r: -(r["x_lift"] or 999))[:args.top]:
        print(f"{r['example'][:37]:<38}{r['lift']:>10}{r['x_human']:>9}"
              f"{r['x_ai']:>8}{str(r['x_lift'] or '∞'):>8}")

    out = ROOT / "eval" / "out" / "cross-domain.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "corpus": corpus,
        "documents": dict(totals),
        "density_per_100_words": {s: round(statistics.mean(density[s]), 2)
                                  for s in sides if totals[s]},
        "candidates_in": len(cands),
        "survivors": held,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[ok] -> {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
