#!/usr/bin/env python3
"""Смоук-тесты CLI-сканера: краевые случаи и человекочитаемый вывод.

Без pytest: subprocess + assert, запуск `python scripts/test_scan.py`.
Фиксируют пользовательский контракт scan.py:
- пустой ввод и не-русский текст не дают бессмысленного отчёта;
- ошибки файла/кодировки отдаются сообщением, а не трейсбеком;
- у находок показан номер строки, чтобы маркер можно было найти в тексте.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCAN = ROOT / "skills" / "humanizer-ru" / "scripts" / "scan.py"

# Консоль Windows (cp1252, cp1251) не печатает кириллицу и ✓: тест пишет UTF-8.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

passed = 0


def check(cond: bool, msg: str) -> None:
    global passed
    assert cond, f"FAIL: {msg}"
    passed += 1


def run(args: list[str], stdin: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCAN), *args],
                          input=stdin, capture_output=True, text=True, encoding="utf-8")


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

# --- BOM: не невидимый символ ------------------------------------------------
_bom_dir = Path(tempfile.mkdtemp())
_bom = _bom_dir / "bom.txt"
_bom.write_bytes("\ufeffПривет, как дела? Поедем завтра на дачу.\n".encode("utf-8"))


def _tech(stdout: str) -> list:
    return [h for h in json.loads(stdout)["markers"] if h["category"] == "Технические маркеры"]


r = run([str(_bom), "--json"])
check(r.returncode == 0 and not _tech(r.stdout), f"файл с BOM: 0 технических маркеров, {r.stdout[:200]}")
r = run(["-", "--json"], stdin="\ufeffПривет, как дела? Поедем завтра на дачу.\n")
check(r.returncode == 0 and not _tech(r.stdout), "stdin с BOM: 0 технических маркеров")
check(_tech(run(["-", "--json"], stdin="При\u200bвет, как дела?").stdout),
      "невидимый символ внутри текста по-прежнему ловится")

# --- CRLF: номера строк и баны как у LF --------------------------------------
_crlf = _bom_dir / "crlf.txt"
_crlf.write_bytes("Чистая строка.\r\n\r\nВ современном мире всё сложно.\r\n".encode("utf-8"))
r = run([str(_crlf)])
check(r.returncode == 1 and "стр. 3" in r.stdout, f"CRLF: бан найден на строке 3, {r.stdout[-300:]}")

# --- HTML-блок: теги не ломают сканер, текст внутри сканируется --------------
r = run(["-", "--json"], stdin="<div class=\"note\">\n<p>В современном мире всё сложно.</p>\n</div>\n")
check(r.returncode == 1 and json.loads(r.stdout)["hard_ban_count"] == 1, "HTML-блок: бан внутри <p> найден")

# --- --genre: жанр снимает законные баны и попадает в отчёт ------------------
_acad = "Данный метод является основным. Данная модель является базовой. Результат — 5%."
r = run(["-", "--json"], stdin=_acad)
check(r.returncode == 1 and json.loads(r.stdout)["genre"] == "marketing", "без жанра строгий режим, exit 1")
r = run(["-", "--json", "--genre", "academic"], stdin=_acad)
_j = json.loads(r.stdout)
check(r.returncode == 0 and _j["genre"] == "academic" and _j["muted_by_genre"]["hard_bans"] >= 2,
      f"--genre academic снимает «данный», «является», тире: {_j['muted_by_genre']}")
r = run(["-", "--genre", "academic"], stdin=_acad)
check("жанр: academic" in r.stdout, "текстовый отчёт называет жанр")
r = run(["-", "--genre", "poetry"], stdin=_acad)
check(r.returncode == 2 and "Traceback" not in r.stderr, "неизвестный жанр: ошибка argparse, без трейсбека")

# --- JSON CLI несёт позиции находок -----------------------------------------
r = run(["-", "--json"], stdin="Чистая строка. В современном мире всё сложно.")
_ban = json.loads(r.stdout)["hard_bans"][0]
check(_ban["name"] == "В современном мире" and _ban["positions"] == [15], f"позиция бана в JSON: {_ban}")
check("warning" not in json.loads(r.stdout), "у русского текста нет предупреждения о языке")
check("warning" in json.loads(run(["-", "--json"], stdin="Plain English text only.").stdout),
      "--json на английском несёт warning")

# --- нет прав на чтение: сообщение и exit 2 ----------------------------------
# На Windows chmod не снимает право чтения, кейс там не моделируется.
if os.name != "nt" and hasattr(os, "geteuid") and os.geteuid() != 0:
    _locked = _bom_dir / "locked.txt"
    _locked.write_text("Текст.", encoding="utf-8")
    _locked.chmod(0)
    r = run([str(_locked)])
    _locked.chmod(0o600)
    check(r.returncode == 2 and "Traceback" not in r.stderr and "не могу прочитать" in r.stderr,
          f"PermissionError: exit 2 и сообщение, получено {r.returncode} {r.stderr!r}")
r = run([str(_bom_dir)])
check(r.returncode == 2 and "Traceback" not in r.stderr, "папка вместо файла: exit 2 без трейсбека")

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
check(re.search(r"ЧИСТОТА: было \d+, стало \d+/100", r.stdout) is not None, "печатается «было N, стало M»")
r = run([str(_d / "kept.txt"), "--before", str(_d / "before.txt")])
check(r.returncode == 0, f"факты сохранены: exit 0, получено {r.returncode}")
check("изменений в них не найдено" in r.stdout and "ручной сверки" in r.stdout, "совпадение элементов не гарантирует сохранение смысла")
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

# --- факт-замок: начало пункта списка и строки разметки не имя ---------------
sys.path.insert(0, str(SCAN.parent))
from humanizer_metrics import diff_facts  # noqa: E402

_list_before = ("Как готовиться:\n- Повторите основы\n* Говорите спокойно\n1. Логика важнее ответа\n"
                "2) Возьмите резюме\n**Тема:** перенос сроков\n✅ Готовность\n\nСовет: Не паникуйте.\n"
                "**Простыми словами:** Прививка учит иммунитет.")
_list_after = "Как готовиться: повторите основы, говорите спокойно, логика важнее ответа, возьмите резюме."
_names = [x for x in diff_facts(_list_before, _list_after).lost if x.startswith("имя:")]
check(not _names, f"слово в начале пункта списка, после «**», эмодзи и двоеточия не имя: {_names}")
_d2 = diff_facts("- Работали с Яндексом и Стэнфордом.", "Работали вместе.")
check("имя:яндекс" in _d2.lost and "имя:стэнфорд" in _d2.lost,
      f"настоящие имена в пункте списка по-прежнему ловятся: {_d2.lost}")
check("имя:excel" in diff_facts("- Excel выгружает отчёт.", "Отчёт выгружается.").lost,
      "латиница в начале пункта списка остаётся именем")

# --- факт-замок: снятая оговорка при факте попадает в потери -----------------
_h = diff_facts("Прививка обычно защищает от 5000 штаммов, но может вызвать жар.",
                "Прививка защищает 5000 штаммов и вызывает жар.").lost
check({"оговорка:обычно", "оговорка:от", "оговорка:может"} <= set(_h), f"снятые оговорки видны: {_h}")
check(not [x for x in diff_facts("Может показаться, что это сложно. Обычно нет.",
                                 "Обычно это несложно.").lost if x.startswith("оговорка:")],
      "оговорка мнения «может показаться» снимается без потери")
_h2 = diff_facts("Есть риск переделок, если бюджет урежут. Это один из сервисов, по данным Росстата.",
                 "Придётся переделывать, бюджет урежут. Это сервис Росстата.").lost
check({"оговорка:риск", "оговорка:если", "оговорка:один из", "оговорка:по данным"} <= set(_h2),
      f"«риск», «если», «один из», «по данным» тоже оговорки: {_h2}")
check("утверждение:главный" in diff_facts("Это ключевой сервис.", "Это главный сервис.").claims_added,
      "«ключевой» → «главный» усиливает утверждение")

# --- факт-замок: структура разметки в потерях, снятое выделение отдельно ------
_m = diff_facts("# Тема\n\n- раз\n- два\n\n<h2>Итог</h2>\n\n**Важно**, <em>да</em>.",
                "Тема\n\nРаз и два.\n\nИтог\n\nВажно, да.")
check({"разметка:заголовок 2→0", "разметка:пункт списка 2→0"} <= set(_m.lost), f"пропавшая структура в потерях: {_m.lost}")
check(set(_m.emphasis_lost) == {"выделение:жирный 1→0", "выделение:курсив 1→0"} and _m.ok,
      f"снятое выделение только предупреждение: {_m.emphasis_lost}")
check(not diff_facts("```\n# не заголовок\n```\nТекст.", "Текст.").lost,
      "решётка внутри ограды кода не заголовок")


if __name__ == "__main__":
    print(f"OK — {passed} проверок прошли.")
