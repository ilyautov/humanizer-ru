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


if __name__ == "__main__":
    print(f"OK — {passed} проверок прошли.")
