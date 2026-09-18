#!/usr/bin/env python3
"""Паритет браузерного сканера (docs/scan.js) с движком Python.

Онлайн-аудит на сайте не должен стать вторым, расходящимся сканером. Правила
уходят в веб экспортом (export_web_rules.py), а этот тест проверяет, что и
исполнение совпадает: на всех текстах eval/corpus баны и маркеры сходятся
поштучно, а ПОЛОСА вердикта («чисто» / «правка» / «рерайт») совпадает точно.

Полоса важнее очков: пользователь читает её, а не число. Прежняя версия теста
сверяла только score в допуске ±10, и допуск ровно накрывал единственное
настоящее расхождение: wiki_baikal.txt в строгом режиме это 82 «правка» в
Python и 90 «чисто» в браузере. Разные вердикты проходили как «в допуске».

Поэтому расхождение теперь учитывается адресно. В браузере нет морфологии,
значит нет и штрафа за номинальность (до NV_PENALTY_MAX). Тест прибавляет этот
штраф обратно к питоновскому счёту и получает то, что браузер ОБЯЗАН показать;
дальше полоса сверяется без допуска, а на очки остаётся маленький допуск под
razdel (простой делитель предложений даёт другой ритм).

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
from humanizer_metrics.score import _band  # noqa: E402

# Допуск только под замену razdel простым делителем предложений: штраф за
# номинальность вычитается отдельно и в допуск не прячется. На текущем корпусе
# после этой поправки разрыв нулевой на всех 22 текстах в трёх жанрах, так что
# допуск — это запас на делитель предложений, а не покрытие известной дыры.
SCORE_TOLERANCE = 2
NV_REASON_PREFIX = "номинальность"
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
    for genre in (None, "academic", "news"):
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
            # Счёт, который браузер обязан показать: питоновский плюс то, чего
            # браузер не измеряет. Он же объявляет этот пропуск в поле unmeasured.
            nv_pen = sum(-pts for reason, pts in sc.penalties
                         if reason.startswith(NV_REASON_PREFIX))
            expected = min(100, sc.score + nv_pen)
            expected_band = _band(expected)
            if py_bans != js_bans:
                failures.append(f"{tag}: баны\n      py {py_bans}\n      js {js_bans}")
            elif py_marks != js_marks:
                failures.append(f"{tag}: маркеры\n      py {py_marks}\n      js {js_marks}")
            elif expected_band != w["band"]:
                failures.append(f"{tag}: полоса py {expected_band} (score {sc.score}"
                                f"{f', +{nv_pen} за неизмеримую номинальность' if nv_pen else ''}) "
                                f"vs js {w['band']} (score {w['score']}); "
                                f"py {sc.penalties} js {w['penalties']}")
            elif abs(expected - w["score"]) > SCORE_TOLERANCE:
                failures.append(f"{tag}: score py {expected} vs js {w['score']} (допуск {SCORE_TOLERANCE}); "
                                f"py {sc.penalties} js {w['penalties']}")
            elif nv_pen and not w.get("unmeasured"):
                failures.append(f"{tag}: браузер не объявил неизмеренную номинальность "
                                f"(питон снял {nv_pen})")
            else:
                passed += 1
                if abs(expected - w["score"]) > worst[0]:
                    worst = (abs(expected - w["score"]), f"{tag}: py {expected} vs js {w['score']}")

    print("=== test_web_parity ===")
    print(f"  текстов: {len(files)} × 3 жанра, совпало: {passed}; наибольший разрыв score: {worst[0]} ({worst[1]})")
    if failures:
        for msg in failures:
            print("  ✗", msg)
        return 1
    print("OK — браузерный сканер совпадает с Python по банам, маркерам и полосе "
          "вердикта; score в допуске после поправки на неизмеримую номинальность.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
