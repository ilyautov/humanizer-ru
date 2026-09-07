#!/usr/bin/env python3
"""Паритет браузерного сканера (docs/scan.js) с движком Python.

Онлайн-аудит на сайте не должен стать вторым, расходящимся сканером. Правила
уходят в веб экспортом (export_web_rules.py), а этот тест проверяет, что и
исполнение совпадает: на всех текстах eval/corpus баны и маркеры сходятся
поштучно, score в допуске. Допуск нужен, потому что в браузере нет морфологии
(штраф до 8) и razdel заменён простым делителем предложений (ритм).

Без Node тест пропускается с пометкой; в CI Node ставится отдельным шагом.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "humanizer-ru" / "scripts"))

from humanizer_metrics import analyze, cleanliness_score  # noqa: E402

SCORE_TOLERANCE = 10
CORPUS_DIRS = ("raw", "human", "humanized", "literary")
# Синтетика на границы Markdown и жанры: то, чего в корпусе нет.
SYNTHETIC = {
    "markdown": "Разбор:\n\n> В современном мире данная технология играет ключевую роль.\n\n"
                "```\nx = \"```\"\n```\n\nСтоит отметить, что `данный` код ``a`b`` не является примером. "
                "Он назвал книгу «Война — и мир» и ушёл — навсегда.\n",
    "ranges": "От Москвы до Питера ехать ночь. Цены от низких до высоких, от простого до сложного.",
    "copy_paste": "Ответ готов :contentReference[oaicite:3] и ещё citeturn0search1 текст.",
    "sterile": " ".join(["Гайка лежала на верстаке. Я взял её и пошёл домой, было поздно и холодно."] * 12),
}


def main() -> int:
    node = shutil.which("node")
    if not node:
        print("[web-parity] ! node не найден, паритет не проверен")
        return 0
    files = [p for d in CORPUS_DIRS for p in sorted((ROOT / "eval" / "corpus" / d).glob("*.txt"))]
    tmp = ROOT / "eval" / "out" / "web_parity"
    tmp.mkdir(parents=True, exist_ok=True)
    for name, text in SYNTHETIC.items():
        (tmp / f"{name}.txt").write_text(text, encoding="utf-8")
        files.append(tmp / f"{name}.txt")

    failures: list[str] = []
    passed = 0
    worst = (0, "")
    for genre in (None, "academic"):
        cmd = [node, str(ROOT / "scripts" / "web_scan_cli.mjs")]
        if genre:
            cmd += ["--genre", genre]
        res = subprocess.run(cmd + [str(f) for f in files], capture_output=True, text=True, check=False)
        if res.returncode != 0:
            print(res.stderr)
            print("[web-parity] ✗ node упал")
            return 1
        web = {r["file"]: r for r in json.loads(res.stdout)}
        for f in files:
            text = f.read_text(encoding="utf-8")
            rep = analyze(text)
            sc = cleanliness_score(rep, genre)
            w = web[str(f)]
            py_bans = sorted((h.marker, h.count) for h in rep.hard_bans)
            js_bans = sorted((n, c) for n, c in w["hard_bans"])
            py_marks = sorted((h.category, h.marker, h.count) for h in rep.markers)
            js_marks = sorted((c, n, k) for c, n, k in w["markers"])
            tag = f"{f.name}{' [' + genre + ']' if genre else ''}"
            if py_bans != js_bans:
                failures.append(f"{tag}: баны\n      py {py_bans}\n      js {js_bans}")
            elif py_marks != js_marks:
                failures.append(f"{tag}: маркеры\n      py {py_marks}\n      js {js_marks}")
            elif abs(sc.score - w["score"]) > SCORE_TOLERANCE:
                failures.append(f"{tag}: score py {sc.score} vs js {w['score']} (допуск {SCORE_TOLERANCE}); "
                                f"py {sc.penalties} js {w['penalties']}")
            else:
                passed += 1
                if abs(sc.score - w["score"]) > worst[0]:
                    worst = (abs(sc.score - w["score"]), f"{tag}: py {sc.score} vs js {w['score']}")

    print("=== test_web_parity ===")
    print(f"  текстов: {len(files)} × 2 жанра, совпало: {passed}; наибольший разрыв score: {worst[0]} ({worst[1]})")
    if failures:
        for msg in failures:
            print("  ✗", msg)
        return 1
    print("OK — браузерный сканер совпадает с Python по банам и маркерам, score в допуске.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
