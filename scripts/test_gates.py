#!/usr/bin/env python3
"""Тесты самих гейтов честности: check_examples.py и self_scan.py.

Гейт, который ничего не ловит, хуже отсутствия гейта: он создаёт ложное
чувство защиты. Здесь проверяется, что каждый гейт срабатывает на заведомо
плохом материале и молчит на заведомо чистом.

Запуск:  python scripts/test_gates.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import check_examples as ce  # noqa: E402
import self_scan as ss  # noqa: E402
import bump_release as br  # noqa: E402
from humanizer_metrics.markers import scan_hard_bans  # noqa: E402

failures: list[str] = []
passed = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global passed
    if ok:
        passed += 1
    else:
        failures.append(f"{name}{': ' + detail if detail else ''}")


def facts_of(text: str) -> set[str]:
    return ce.facts(text)[0]


# --- check_examples: извлечение фактов -----------------------------------
check("цифра ловится", "число:13" in facts_of("выросло на 13%"))
check("год ловится", "число:2023" in facts_of("вышел в 2023-м"))
check("месяц ловится", "месяц:март" in facts_of("в марте выкатили"))
check("имя вне словаря ловится", "имя:стэнфорд" in facts_of("Стэнфорд гонял эксперимент"))
check("латиница ловится", "имя:excel" in facts_of("работали в Excel-таблицах"))
check("организация ловится", "имя:яндекс" in facts_of("Это сделал Яндекс"))
check("число словами ловится", "число словами:сорок" in facts_of("экономит сорок минут"))
check("обычное слово не имя", not any(f.startswith("имя:") for f in facts_of("Команда выросла вдвое")),
      str(facts_of("Команда выросла вдвое")))
check("мелкие количества мягкие", "два" in ce.facts("сделали два подхода")[1])

# --- check_examples: сравнение пары ---------------------------------------
dirty = ce.Pair(path=Path("x.md"), line=1,
                before="Исследования показывают, что удалёнка работает.",
                after="Стэнфорд мерил два года: на 13% продуктивнее.")
hard, _ = ce.check(dirty)
check("выдуманные факты валят пару", bool(hard), str(hard))

clean = ce.Pair(path=Path("x.md"), line=1,
                before="Осуществление процесса оптимизации способствует повышению эффективности.",
                after="Навели порядок в процессах, стало быстрее работать.")
check("честная пара проходит", not ce.check(clean)[0], str(ce.check(clean)[0]))

morph = ce.Pair(path=Path("x.md"), line=1,
                before="В Стэнфорде мерили продуктивность.",
                after="Стэнфорд мерил продуктивность.")
check("словоформа имени не считается новым фактом", not ce.check(morph)[0])

alias = ce.Pair(path=Path("x.md"), line=1,
                before="Искусственный интеллект внедряют повсеместно.",
                after="AI внедряют повсеместно.")
check("алиас сущности не считается новым фактом", not ce.check(alias)[0])

# --- check_examples: разбор разметки --------------------------------------
sample = ROOT.parent / "skills" / "humanizer-ru" / "references" / "catalog.md"
pairs = ce.collect_pairs(sample)
check("пары в каталоге находятся", len(pairs) >= 5, f"найдено {len(pairs)}")
check("метка «факты автора» распознаётся", any(p.author_facts for p in pairs))

# --- self_scan: вырезание цитат -------------------------------------------
check("ёлочки вырезаются", "является" not in ss.strip_quotes("Слово «является» под баном"))
check("код вырезается", "является" not in ss.strip_markdown("Слово `является` под баном"))
check("плохая половина примера вырезается",
      "современном" not in ss.strip_bad_examples("До: В современном мире всё меняется."))
check("хорошая половина примера остаётся",
      "порядок" in ss.strip_bad_examples("После: Навели порядок в процессах."))
check("html-теги вырезаются", "<b>" not in ss.strip_html("<b>Текст</b>"))
check("номера строк не съезжают",
      ss.strip_quotes("а\n«б»\nв").count("\n") == 2)
with tempfile.TemporaryDirectory() as tmp:
    fixture = Path(tmp) / "fixture.md"
    fixture.write_text(
        "Слово является маркером. <!-- self-scan: ok — цитируем сам бан -->\n"
        "## Быстрый сканер\nявляется, стоит отметить\n"
        "## Дальше\nЗдесь текст является плохим.\n",
        encoding="utf-8",
    )
    prose = ss.prose_of(fixture)
    check("пометка снимает строку", "маркером" not in prose, prose[:60])
    check("раздел словаря маркеров снимается", "стоит отметить" not in prose)
    check("остальная проза проверяется", bool(scan_hard_bans(prose)), prose)

# --- self_scan: сам бан ловится -------------------------------------------
check("бан в прозе ловится", bool(scan_hard_bans("Данный подход является ключевым.")))
check("чистая проза не ловится", not scan_hard_bans("Навели порядок в процессах, стало быстрее."))

# --- check_examples: количества без источника -----------------------------
_pair = lambda b, a: ce.Pair(path=Path("x"), line=1, before=b, after=a)  # noqa: E731
_h, _s = ce.check(_pair("В современном мире AI меняет бизнес.",
                        "Я внедрил AI в три проекта. Два ускорились вдвое."))
check("два и больше количеств без числа в исходнике: ошибка", bool(_h), str((_h, _s)))
_h, _s = ce.check(_pair("Скорость выросла на 50%.", "Скорость выросла вдвое."))
check("пересказ числа из исходника остаётся заметкой", not _h and _s, str((_h, _s)))
_h, _s = ce.check(_pair("Команда росла.", "Команда выросла вдвое."))
check("одно количество без источника остаётся заметкой", not _h and _s, str((_h, _s)))

# --- bump_release: счётчики видят числа сквозь HTML-теги -------------------
check("счётчик паттернов сквозь <b></b><span>",
      br.RE_PATTERN_COUNT.findall('<b>54</b><span>признака AI-текста</span>') == ["54"])
check("счётчик банов сквозь теги",
      br.RE_BAN_COUNT.findall('<b>20</b><span>жёстких запретов</span>') == ["20"])
check("обычный текст считается как прежде",
      br.RE_PATTERN_COUNT.findall("каталог из 64 признаков") == ["64"])
check("штраф сканера «-27  маркеры: 14» не принимается за размер каталога",
      br.RE_PATTERN_COUNT.findall("  -27  маркеры: 14 (13.5/100 слов)") == [])
check("год перед тегом без существительного не ловится",
      br.RE_PATTERN_COUNT.findall("<b>2026</b><span>год</span>") == [])

print("=== test_gates ===")
if failures:
    print(f"  прошло {passed}, упало {len(failures)}:")
    for f in failures:
        print("  ✗", f)
    raise SystemExit(1)
print(f"OK — {passed} проверок прошли.")
