#!/usr/bin/env python3
"""Балл сканера по условиям парного прогона probe_installed_skill.py.

Дополняет слепую оценку смысла: показывает, снимает ли инструкция маркеры,
а не только бережёт ли она исходник. Не заменяет чтение ответов.

  .venv/bin/python eval/probe_scanner.py eval/out/<run>
"""
from __future__ import annotations

import glob
import json
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "humanizer-ru" / "scripts"))
from humanizer_metrics import analyze, cleanliness_score  # noqa: E402


def score(text: str) -> float:
    return cleanliness_score(analyze(text)).score


def main() -> int:
    run = Path(sys.argv[1])
    blind = {json.load(open(p))["id"]: json.load(open(p)) for p in glob.glob(str(run / "blind/*.json"))}
    by: dict[tuple[str, str], list] = {}
    for p in sorted(glob.glob(str(run / "raw/*.json"))):
        r = json.load(open(p))
        b = blind.get(r["id"])
        if not b or not r.get("ok"):
            continue
        by.setdefault((r["case"], r["arm"]), []).append(
            (score(b["source"]), score(b["output"]), b["output"].strip() == b["source"].strip()))
    arms = sorted({a for _, a in by})
    cases = sorted({c for c, _ in by})
    print(f"{'case':16}{'src':>5}  " + "  ".join(f"{a:>18}" for a in arms))
    totals: dict[str, list] = {a: [] for a in arms}
    for c in cases:
        src = ""
        line = ""
        for a in arms:
            v = by.get((c, a))
            if not v:
                line += f"  {'-':>18}"
                continue
            src = f"{v[0][0]:.0f}"
            outs = [o for _, o, _ in v]
            totals[a] += outs
            line += f"  {st.mean(outs):6.1f} (=src {sum(1 for *_, s in v if s)}/{len(v)})"
        print(f"{c:16}{src:>5}" + line)
    print("mean:", {a: round(st.mean(v), 1) for a, v in totals.items() if v})
    return 0


if __name__ == "__main__":
    sys.exit(main())
