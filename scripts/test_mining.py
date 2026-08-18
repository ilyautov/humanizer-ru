#!/usr/bin/env python3
"""Тесты шахты паттернов (eval/mine_patterns.py) на синтетическом корпусе.

Корпус собирается прямо здесь, сеть не нужна, поэтому тест гоняется в CI.
Проверяем три вещи, каждая из которых один раз уже ломала прогон на живых
данных:
  1. подсаженная фраза находится и получает высокий lift;
  2. фраза, общая для обоих классов, в кандидаты не попадает (иначе шахта
     выдаёт тему корпуса за стиль);
  3. выборка не зависит от порядка строк в файле и уравнивает длину классов.
"""

from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "eval"))

passed = 0


def check(cond: bool, label: str) -> None:
    global passed
    if not cond:
        print(f"FAIL: {label}")
        raise SystemExit(1)
    passed += 1


# Общий «наполнитель» держит документы в окне длины 40-160 слов. Тема (озеро,
# вода, берег) одинакова у обоих классов: она НЕ должна всплыть как маркер.
FILLER = ("озеро лежит между гор и питает реку водой каждый год берег меняется "
          "от ветра и льда рыбаки выходят на воду рано утром и возвращаются "
          "поздно вечером с уловом который делят между собой по старому обычаю "
          "деревни стоят вдоль берега и живут этим промыслом много поколений подряд ")
PLANT = "особое внимание уделяется роли фактора"


def make_corpus(path: Path) -> None:
    rows = []
    for i in range(120):
        # Человек: только наполнитель, разная длина внутри окна.
        rows.append({"text": FILLER * 2 + f"вариант {i} без клише", "label": "human"})
    for model in ("model-a", "model-b"):
        for i in range(120):
            rows.append({"text": FILLER * 2 + PLANT + f" номер {i}", "label": model})
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["text", "label"])
        w.writeheader()
        w.writerows(rows)


def test_end_to_end(tmp: Path) -> None:
    corpus = tmp / "synthetic.csv"
    make_corpus(corpus)
    out = ROOT / "eval" / "out" / "mined-train.json"
    backup = out.read_text(encoding="utf-8") if out.exists() else None
    try:
        r = subprocess.run(
            [sys.executable, str(ROOT / "eval" / "mine_patterns.py"), "--csv", str(corpus),
             "--per-class", "120", "--min-support", "1", "--top", "5"],
            capture_output=True, text=True)
        check(r.returncode == 0, f"шахта отработала без ошибки: {r.stderr[-400:]}")
        data = json.loads(out.read_text(encoding="utf-8"))
        grams = {c["ngram"] for c in data["candidates"]}
        check(any("внимание" in g and "уделяться" in g for g in grams),
              "подсаженная фраза попала в кандидаты")
        check(all("озеро" not in g and "рыбак" not in g for g in grams),
              "общая для классов тема в кандидаты не попала")
        top = data["candidates"][0]
        check(top["lift"] >= 10, f"у подсаженной фразы высокий lift, получено {top['lift']}")
        check(top["families"] == 2, "маркер держится на обоих семействах")
    finally:
        if backup is not None:
            out.write_text(backup, encoding="utf-8")
        elif out.exists():
            out.unlink()


def test_sampling() -> None:
    from mine_patterns import sample_rows

    # Файл сгруппирован по меткам, как настоящий AINL: наивная выборка «первые N»
    # взяла бы один сплошной блок.
    rows = ([{"text": "коротко " * 10, "label": "human"} for _ in range(50)]
            + [{"text": "нормальной длины " * 30, "label": "human"} for _ in range(50)]
            + [{"text": "нормальной длины " * 30, "label": "ai"} for _ in range(100)])
    picked = sample_rows(rows, per_class=20, lo=40, hi=160)
    human = [t for lab, t in picked if lab == "human"]
    check(len(human) == 20, "выборка добрала нужное число человеческих документов")
    check(all(40 <= len(t.split()) <= 160 for _, t in picked),
          "окно длины отсекло короткие документы")
    check(any("нормальной" in t for t in human),
          "выборка дотянулась до дальней части блока, а не взяла первые строки")


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as d:
        test_end_to_end(Path(d))
    test_sampling()
    print(f"OK — {passed} проверок прошли.")
