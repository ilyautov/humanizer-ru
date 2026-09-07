#!/usr/bin/env python3
"""Согласованность релизных чисел: счётчики и версия во всех местах сразу.

Класс багов, который это убивает: счётчик паттернов и версия запечены в
десятке мест (README, 5 страниц docs, 6 description-полей манифестов, бейдж,
eyebrow), version бампается релизом, а тексты рядом молча отстают. Реальные
случаи 07-08.07.2026: About-поле с «52» и «Обходит» висело месяц; описания
манифестов несли «52 паттерна» при каталоге 54, и Cowork показывал старую
карточку на свежем коммите.

Источники истины (никогда не редактируются этим скриптом):
  - число паттернов  = максимум сплошной нумерации каталога SKILL.md;
  - число hard bans  = len(HARD_BANS) из движка markers.py;
  - число категорий  = сплошные буквы заголовков «### X.» того же каталога;
  - версия           = аргумент --apply vX.Y.Z (или согласованность в --check).

Падеж существительного рядом со счётчиком скрипт теперь ведёт сам
(scripts/ru_plural.py): «58 паттернов» -> «64 паттерна». Только счётная
позиция; после предлога («каталог из 64 признаков», «по всем 64 пунктам»)
падеж задаёт предлог, и слово не трогается.

Режимы:
    python scripts/bump_release.py --check          # CI-гейт: дрейф = exit 1
    python scripts/bump_release.py --apply v3.15.0  # протащить версию+счётчики
    python scripts/bump_release.py --apply          # только счётчики

Что НЕ автоматизируется (печатается напоминанием при --apply): ZIP-ассет
humanizer-ru.zip к GitHub Release (на него ведёт README, issue #45), About-поле
GitHub (gh repo edit), локальная копия ~/.claude/skills, синк маркетплейса в
Cowork, счётчик внутри assets/social-preview.png собирается
скриптом scripts/make_social_preview.py (гейт --check в CI).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT / "skills" / "humanizer-ru" / "scripts"))
from humanizer_metrics.markers import HARD_BANS  # noqa: E402
from ru_plural import agreement_drift, fix_agreement  # noqa: E402

SKILL = ROOT / "skills" / "humanizer-ru" / "references" / "catalog.md"
AGENT_MANIFESTS = sorted(
    str(p.relative_to(ROOT))
    for p in (ROOT / "skills" / "humanizer-ru" / "agents").glob("*.yaml")
)

# Файлы, где живут СЧЁТЧИКИ (SKILL.md намеренно не здесь: он источник истины,
# его правит человек, а линт проверяет сплошную нумерацию).
COUNT_FILES = [
    "README.md", "README.en.md",
    "docs/index.html", "docs/52-priznaka-ai-teksta.html",
    "docs/ai-detektory-na-russkom.html", "docs/antiplagiat-i-neyroset.html",
    "docs/kak-ubrat-sledy-neyroseti.html",
    ".claude-plugin/plugin.json", ".claude-plugin/marketplace.json",
    ".cursor-plugin/plugin.json", ".codex-plugin/plugin.json",
    *AGENT_MANIFESTS,
    "gemini-extension.json",
    # Бандл DeepSeek Harness: description пакета несёт счётчик паттернов.
    "package.json",
]

# Число + существительное, означающее «паттерны каталога». Лукахед не даёт
# задеть чужие числа («20 запретов», «52K текстов», даты). Сама подстановка
# меняет только цифру, поэтому дальше по тексту идёт второй проход,
# ru_plural.fix_agreement: при 58 существительное стоит в форме «паттернов»,
# при 64 нужна «паттерна», и раньше это чинилось руками (а по манифестам не
# чинилось вовсе).
PATTERN_NOUNS = r"(?:паттерн\w*|признак\w*|пункт\w*|маркер\w*|pattern\w*|marker\w*)"
RE_PATTERN_COUNT = re.compile(rf"\b(\d+)(?=\s+{PATTERN_NOUNS})")
# Отдельный случай: таблица README «| Паттернов | 54 | 32 |» (число ПОСЛЕ
# существительного; вторая колонка — конкурент, не трогается).
RE_TABLE = re.compile(r"(\|\s*Паттернов\s*\|\s*)(\d+)")

BAN_NOUNS = r"(?:жёстких|запрет\w*|hard[- ]ban\w*|hard-banned)"
RE_BAN_COUNT = re.compile(rf"\b(\d+)(?=\s+{BAN_NOUNS})")

# Категории каталога (A-M). Раньше это число скрипт намеренно не трогал, и оно
# протухло: категория M появилась в v3.16.0, а карточки всех манифестов
# продолжали обещать «12 категорий» при тринадцати. Тот же класс бага, что
# «52 паттерна» на свежем коммите, только заметить его труднее.
CATEGORY_NOUNS = r"(?:категор\w*|categor\w+)"
RE_CATEGORY_COUNT = re.compile(rf"\b(\d+)(?=\s+{CATEGORY_NOUNS})")

VERSION_TARGETS = [
    # (файл, regex с одной группой-версией)
    (".claude-plugin/plugin.json", r'"version":\s*"([\d.]+)"'),
    (".claude-plugin/marketplace.json", r'"version":\s*"([\d.]+)"'),
    (".cursor-plugin/plugin.json", r'"version":\s*"([\d.]+)"'),
    (".codex-plugin/plugin.json", r'"version":\s*"([\d.]+)"'),
    ("gemini-extension.json", r'"version":\s*"([\d.]+)"'),
    ("package.json", r'"version":\s*"([\d.]+)"'),
    ("README.md", r"версия-([\d.]+)-blueviolet"),
    ("README.en.md", r"version-([\d.]+)-blueviolet"),
    # Заголовок скилла. До v3.15.4 здесь жила отдельная «контент-версия»,
    # которая двигалась только при правке промпта и потому отставала (v3.13 при
    # пакете 3.15.3). Версия теперь одна на весь репозиторий: сравнивать две
    # нумерации всё равно было некому, а расхождение читалось как баг.
    ("skills/humanizer-ru/SKILL.md", r"# Humanizer-RU v([\d.]+)"),
    ("docs/index.html", r"<li>v([\d.]+)</li>"),
]


def derive_pattern_count() -> int:
    text = SKILL.read_text(encoding="utf-8")
    catalog = text.split("## Каталог:", 1)[1]
    nums: set[int] = set()
    # «**17-18. Орфографические мелочи**» — сдвоенный паттерн диапазоном.
    for a, b in re.findall(r"\*\*(\d+)(?:-(\d+))?\.", catalog):
        nums.update(range(int(a), int(b or a) + 1))
    seq = sorted(nums)
    assert seq and seq == list(range(1, seq[-1] + 1)), \
        f"нумерация каталога не сплошная: {sorted(set(range(1, seq[-1] + 1)) - nums)}"
    return seq[-1]


def derive_category_count() -> int:
    """Категории каталога: заголовки вида «### M. Формулы и артефакты 2026»."""
    letters = re.findall(r"^###\s+([A-Z])\.", SKILL.read_text(encoding="utf-8"), re.MULTILINE)
    assert letters, "в каталоге не найдено ни одной категории"
    expected = [chr(ord("A") + i) for i in range(len(letters))]
    assert letters == expected, f"буквы категорий не сплошные: {letters}"
    return len(letters)


def scan_counts(patterns: int, bans: int, categories: int) -> list[str]:
    """Возвращает список расхождений счётчиков по всем файлам."""
    drift = []
    for rel in COUNT_FILES:
        s = (ROOT / rel).read_text(encoding="utf-8")
        for m in RE_PATTERN_COUNT.finditer(s):
            if int(m.group(1)) != patterns:
                ctx = s[m.start():m.start() + 40].replace("\n", " ")
                drift.append(f"{rel}: «{ctx}...» ожидалось {patterns}")
        for m in RE_TABLE.finditer(s):
            if int(m.group(2)) != patterns:
                drift.append(f"{rel}: таблица «Паттернов | {m.group(2)}» ожидалось {patterns}")
        for m in RE_BAN_COUNT.finditer(s):
            if int(m.group(1)) != bans:
                ctx = s[m.start():m.start() + 40].replace("\n", " ")
                drift.append(f"{rel}: «{ctx}...» ожидалось {bans} банов")
        for m in RE_CATEGORY_COUNT.finditer(s):
            if int(m.group(1)) != categories:
                ctx = s[m.start():m.start() + 40].replace("\n", " ")
                drift.append(f"{rel}: «{ctx}...» ожидалось {categories} категорий")
        for _, found, want in agreement_drift(s):
            drift.append(f"{rel}: «{found}» ожидалось «{want}» (падеж при числе)")
    return drift


def scan_versions() -> tuple[list[str], list[str]]:
    """Полные версии обязаны совпадать; eyebrow сайта = vX.Y от них же."""
    full, eyebrow, details, drift = set(), None, [], []
    for rel, rx in VERSION_TARGETS:
        s = (ROOT / rel).read_text(encoding="utf-8")
        m = re.search(rx, s)
        if not m:
            drift.append(f"{rel}: версия не найдена ({rx})")
            continue
        v = m.group(1)
        details.append(f"{rel}: {v}")
        if rel == "docs/index.html":
            eyebrow = v
        else:
            full.add(v)
    if len(full) > 1:
        drift.append(f"версии манифестов/бейджа разъехались: {sorted(full)}")
    if full and eyebrow is not None:
        short = ".".join(next(iter(full)).split(".")[:2])
        if eyebrow != short:
            drift.append(f"eyebrow сайта v{eyebrow} != v{short} из манифестов")
    return drift, details


def apply_all(patterns: int, bans: int, categories: int, version: str | None) -> int:
    changed = 0
    for rel in COUNT_FILES:
        p = ROOT / rel
        s = orig = p.read_text(encoding="utf-8")
        s = RE_PATTERN_COUNT.sub(str(patterns), s)
        s = RE_TABLE.sub(rf"\g<1>{patterns}", s)
        s = RE_BAN_COUNT.sub(str(bans), s)
        s = RE_CATEGORY_COUNT.sub(str(categories), s)
        s = fix_agreement(s)
        if s != orig:
            p.write_text(s, encoding="utf-8")
            changed += 1
            print(f"[apply] {rel}: счётчики -> {patterns}/{bans}/{categories}")
    if version:
        full = version.lstrip("v")
        short = "v" + ".".join(full.split(".")[:2])
        for rel, rx in VERSION_TARGETS:
            p = ROOT / rel
            s = orig = p.read_text(encoding="utf-8")
            new = short.lstrip("v") if rel == "docs/index.html" else full
            s = re.sub(rx, lambda m: m.group(0).replace(m.group(1), new), s)
            if s != orig:
                p.write_text(s, encoding="utf-8")
                changed += 1
                print(f"[apply] {rel}: версия -> {new}")
    return changed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true", help="проверить согласованность (CI-гейт)")
    g.add_argument("--apply", nargs="?", const="", metavar="vX.Y.Z",
                   help="протащить счётчики (и версию, если указана) по всем местам")
    args = ap.parse_args()

    patterns = derive_pattern_count()
    bans = len(HARD_BANS)
    categories = derive_category_count()
    print(f"[истина] паттернов: {patterns} (из SKILL.md), hard bans: {bans} (из markers.py)")

    if args.check:
        drift = scan_counts(patterns, bans, categories)
        vdrift, details = scan_versions()
        for d in details:
            print(f"[версии] {d}")
        drift.extend(vdrift)
        if drift:
            for d in drift:
                print(f"[дрейф] ✗ {d}")
            return 1
        print("[гейт] ✓ счётчики и версия согласованы во всех местах")
        return 0

    changed = apply_all(patterns, bans, categories, args.apply or None)
    print(f"[итог] файлов изменено: {changed}")
    print("[напоминание] руками после релиза: приложить humanizer-ru.zip к"
          " GitHub Release (cd skills && zip -r ../humanizer-ru.zip humanizer-ru"
          " -x '*/__pycache__/*'; README ведёт на"
          " releases/latest/download/humanizer-ru.zip — без ассета ссылка"
          " ломается), About-поле GitHub (gh repo edit,"
          " текст = 1-я строка README), локальная копия"
          " (cp -R skills/humanizer-ru/. ~/.claude/skills/humanizer-ru/),"
          " синк маркетплейса в Cowork.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
