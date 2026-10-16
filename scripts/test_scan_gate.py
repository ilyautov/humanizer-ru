#!/usr/bin/env python3
"""Тесты гейта CI (scripts/scan_gate.py, основа action.yml).

Без pytest: subprocess + assert, запуск `python scripts/test_scan_gate.py`.
Фиксируют контракт гейта:
- текст не на русском пропускается с пометкой и не даёт 100/100 молча;
- маска не заходит в node_modules, .venv, vendor, dist и другие служебные папки;
- exit 0 при выдержанном пороге, 1 ниже порога, 2 если файл не прочитать;
- BOM в начале файла не штрафуется как невидимый символ.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GATE = ROOT / "scripts" / "scan_gate.py"

# Консоль Windows (cp1252, cp1251) не печатает кириллицу и ✓: тест пишет UTF-8.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

passed = 0

CLEAN = "Я попробовал три раза. Не вышло. Потом понял, в чём дело: забыл про кэш.\n"
SLOP = ("В современном мире данный подход является ключевым. Стоит отметить, что это "
        "не просто инструмент, а комплексное решение. Таким образом, он открывает новые "
        "горизонты и выводит бизнес на новый уровень.\n")
ENGLISH = "This README is written in plain English and has no Russian words at all.\n"


def check(cond: bool, msg: str) -> None:
    global passed
    assert cond, f"FAIL: {msg}"
    passed += 1


def gate(cwd: Path, files: str, *extra: str) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k not in ("GITHUB_OUTPUT", "GITHUB_STEP_SUMMARY")}
    return subprocess.run([sys.executable, str(GATE), "--files", files, *extra],
                          cwd=cwd, capture_output=True, text=True, encoding="utf-8", env=env)


def tree(files: dict[str, str | bytes]) -> Path:
    root = Path(tempfile.mkdtemp())
    for rel, body in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(body, bytes):
            p.write_bytes(body)
        else:
            p.write_text(body, encoding="utf-8")
    return root


# --- нерусский текст пропускается с пометкой ------------------------------
d = tree({"README.md": ENGLISH, "docs/ru.md": CLEAN})
r = gate(d, "**/*.md")
check(r.returncode == 0, f"английский рядом с чистым русским: exit 0, получено {r.returncode}")
check("README.md: skipped: не русский текст" in r.stdout, f"пометка пропуска: {r.stdout}")
check("файлов 1" in r.stdout and "100/100" not in r.stdout.split("skipped")[0],
      "английский файл не попал в таблицу баллов")
r = gate(tree({"README.md": ENGLISH}), "*.md")
check(r.returncode == 0 and "проверять нечего" in r.stdout,
      f"только английский: проверять нечего, exit 0: {r.stdout}")

# --- служебные папки не обходятся маской -----------------------------------
d = tree({"docs/a.md": CLEAN, "node_modules/pkg/README.md": SLOP, ".venv/lib/x.md": SLOP,
          "venv/y.md": SLOP, "vendor/z.md": SLOP, "dist/d.md": SLOP, "build/b.md": SLOP})
r = gate(d, "**/*.md", "--min-score", "60")
check(r.returncode == 0, f"слоп в служебных папках не валит гейт: {r.stdout}")
for folder in ("node_modules", ".venv", "venv", "vendor", "dist", "build"):
    check(folder not in r.stdout, f"{folder} не попал в отчёт")
r = gate(d, "vendor/z.md", "--min-score", "60")
check(r.returncode == 1, "файл, названный явно, проверяется и в vendor/")

# --- коды выхода ----------------------------------------------------------
d = tree({"clean.md": CLEAN, "slop.md": SLOP})
check(gate(d, "clean.md", "--min-score", "60").returncode == 0, "чистый файл: exit 0")
r = gate(d, "*.md", "--min-score", "60")
check(r.returncode == 1 and "ниже порога" in r.stdout, f"слоп ниже порога: exit 1: {r.stdout}")
check(gate(d, "nothing/*.md").returncode == 0, "пустая маска: exit 0")
d = tree({"bom.md": "﻿" + CLEAN})
r = gate(d, "bom.md", "--min-score", "95")
check(r.returncode == 0, f"BOM не невидимый символ: {r.stdout}")
d = tree({"cp1251.md": "Привет, как дела?".encode("cp1251"), "ok.md": CLEAN})
r = gate(d, "*.md")
check(r.returncode == 0 and "не в кодировке UTF-8" in r.stdout, f"не UTF-8 пропускается с пометкой: {r.stdout}")
if os.name != "nt" and hasattr(os, "geteuid") and os.geteuid() != 0:
    d = tree({"locked.md": CLEAN, "ok.md": CLEAN})
    (d / "locked.md").chmod(0)
    r = gate(d, "*.md")
    (d / "locked.md").chmod(0o600)
    check(r.returncode == 2 and "не удалось прочитать" in r.stderr and "Traceback" not in r.stderr,
          f"нечитаемый файл: exit 2 и сообщение, получено {r.returncode} {r.stderr!r}")

# --- выходы GitHub Actions --------------------------------------------------
d = tree({"clean.md": CLEAN})
out = d / "gh_output"
r = subprocess.run([sys.executable, str(GATE), "--files", "clean.md"], cwd=d, capture_output=True,
                   text=True, encoding="utf-8", env={**os.environ, "GITHUB_OUTPUT": str(out)})
check(r.returncode == 0 and out.read_text(encoding="utf-8").startswith("score="),
      "в GITHUB_OUTPUT пишется score")


if __name__ == "__main__":
    print(f"OK — {passed} проверок прошли.")
