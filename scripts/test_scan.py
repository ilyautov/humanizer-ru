#!/usr/bin/env python3
"""Смоук-тесты CLI-сканера: краевые случаи и человекочитаемый вывод.

Без pytest: subprocess + assert, запуск `python scripts/test_scan.py`.
Фиксируют пользовательский контракт scan.py:
- пустой ввод и не-русский текст не дают бессмысленного отчёта;
- ошибки файла/кодировки отдаются сообщением, а не трейсбеком;
- у находок показан номер строки, чтобы маркер можно было найти в тексте.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCAN = ROOT / "skills" / "humanizer-ru" / "scripts" / "scan.py"

passed = 0


def check(cond: bool, msg: str) -> None:
    global passed
    assert cond, f"FAIL: {msg}"
    passed += 1


def run(args: list[str], stdin: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCAN), *args],
                          input=stdin, capture_output=True, text=True)


# --- пустой ввод ------------------------------------------------------------
r = run(["-"], stdin="   \n")
check(r.returncode == 0, f"пустой ввод: exit 0, получено {r.returncode}")
check("пуст" in r.stdout.lower(), "пустой ввод: сообщение «текст пуст», а не отчёт")

r = run(["-", "--json"], stdin="")
check(r.returncode == 0, f"--json на пустом вводе: exit 0, получено {r.returncode}")

# --- несуществующий файл -----------------------------------------------------
r = run(["/nonexistent/file.txt"])
check(r.returncode == 2, f"несуществующий файл: exit 2, получено {r.returncode}")
check("Traceback" not in r.stderr, "несуществующий файл: без трейсбека")
check("не найден" in (r.stderr + r.stdout), "несуществующий файл: человеческое сообщение")

# --- не-русский текст --------------------------------------------------------
r = run(["-"], stdin="This is plain English text with no Russian words at all. " * 3)
check(r.returncode == 0, f"английский текст не роняет сканер, получено {r.returncode}")
check("не похож на русский" in r.stdout, "английский текст: предупреждение о языке")

# --- позиции находок: номер строки ------------------------------------------
text = "Чистая строка.\n\nВ современном мире всё сложно.\n"
r = run(["-"], stdin=text)
check(r.returncode == 1, f"хард-бан даёт exit 1, получено {r.returncode}")
check("стр. 3" in r.stdout, "у хард-бана показан номер строки (стр. 3)")

# --- обычный русский текст по-прежнему работает ------------------------------
r = run(["-"], stdin="Я попробовал три раза. Не вышло. Потом понял: забыл про кэш.")
check(r.returncode == 0, f"чистый текст: exit 0, получено {r.returncode}")
check("ЧИСТОТА" in r.stdout, "обычный отчёт печатается")

# --- факт-замок: --before ---------------------------------------------------
import tempfile as _tmp  # noqa: E402
_d = Path(_tmp.mkdtemp())
(_d / "before.txt").write_text("Мы внедрили удалёнку в 2023 году, документация на https://example.com/docs.\n",
                               encoding="utf-8")
(_d / "invented.txt").write_text("Стэнфорд мерил два года: на 13% продуктивнее. В 2023-м внедрили, "
                                 "документация на example.com/docs.\n", encoding="utf-8")
(_d / "kept.txt").write_text("Удалёнка у нас с 2023 года, документация лежит на example.com/docs.\n",
                             encoding="utf-8")
r = run([str(_d / "invented.txt"), "--before", str(_d / "before.txt")])
check(r.returncode == 2, f"выдуманный факт даёт exit 2, получено {r.returncode}")
check("число:13" in r.stdout and "имя:стэнфорд" in r.stdout, "выдуманные число и имя названы")
check("было 100" in r.stdout or "было " in r.stdout, "печатается «было N, стало M»")
r = run([str(_d / "kept.txt"), "--before", str(_d / "before.txt")])
check(r.returncode == 0, f"факты сохранены: exit 0, получено {r.returncode}")
check("факт-замок цел" in r.stdout, "сохранённые факты: вердикт «цел»")
check("ссылка" not in r.stdout.split("Факт-замок")[-1], "https:// и www. не делают ссылку новым фактом")
(_d / "claim_before.txt").write_text("Первый в России сервис, единственный с офлайн-режимом.\n", encoding="utf-8")
(_d / "claim_cut.txt").write_text("Сервис с офлайн-режимом.\n", encoding="utf-8")
(_d / "claim_new.txt").write_text("Первый в России сервис, единственный с офлайн-режимом, впервые без подписки.\n",
                                   encoding="utf-8")
r = run([str(_d / "claim_cut.txt"), "--before", str(_d / "claim_before.txt")])
check(r.returncode == 0 and "потеряно: утверждение:первый" in r.stdout
      and "потеряно: утверждение:единственный" in r.stdout,
      "срезанные кванторы попадают в потери, проверку не валят")
r = run([str(_d / "claim_new.txt"), "--before", str(_d / "claim_before.txt")])
check(r.returncode == 0 and "утверждение появилось: утверждение:впервые" in r.stdout,
      "появившийся квантор предупреждает, но не валит")
r = run([str(_d / "kept.txt"), "--before", str(_d / "before.txt"), "--json"])
check('"facts"' in r.stdout and '"before"' in r.stdout, "--json несёт facts и before")


if __name__ == "__main__":
    print(f"OK — {passed} проверок прошли.")
