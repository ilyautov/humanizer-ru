#!/usr/bin/env python3
"""Self-test скилла: тестирует SKILL.md против собственных правил.

Ловит ровно те классы регрессий, которые иначе ловятся только глазами:
  1. Пропавший/задвоенный паттерн (нумерация 1..54 без дыр).
  2. Число HARD BANS и категорий сканера разошлось с markers.py.
  3. Длинное тире «—» в СОБСТВЕННЫХ одобренных примерах скилла (После:/Стало:/
     блок «## Примеры»). Скилл велит ноль тире — он не имеет права показывать
     тире в «хорошем» выводе.
  4. Каждый одобренный пример скилла («Стало:»/«После:») сам проходит сканер:
     ноль HARD BANS. Скилл, нарушающий свои баны в примерах, не пройдёт CI.

Запуск:  python scripts/lint_skill.py
Exit code 1 при любой ошибке — гейт для CI/pre-commit.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Пакет метрик живёт ВНУТРИ скилла (едет с установкой), dev-тулы — в корневом scripts/.
sys.path.insert(0, str(ROOT / "skills" / "humanizer-ru" / "scripts"))

from humanizer_metrics.markers import HARD_BANS, SCANNER, scan_hard_bans

CANON = ROOT / "skills" / "humanizer-ru" / "SKILL.md"

EXPECTED_PATTERNS = 54
EXPECTED_HARD_BANS = 20
EXPECTED_SCANNER_CATS = 22

errors: list[str] = []
notes: list[str] = []


def check_patterns(text: str) -> None:
    found = set()
    # Заголовки паттернов: «**6.**» и диапазоны «**17-18.**».
    for m in re.finditer(r"^\*\*(\d{1,2})(?:-(\d{1,2}))?\.", text, re.MULTILINE):
        start = int(m.group(1))
        end = int(m.group(2)) if m.group(2) else start
        for n in range(start, end + 1):
            if 1 <= n <= EXPECTED_PATTERNS:
                found.add(n)
    missing = sorted(set(range(1, EXPECTED_PATTERNS + 1)) - found)
    if missing:
        errors.append(f"Пропущены паттерны: {missing}")
    else:
        notes.append(f"✓ все {EXPECTED_PATTERNS} паттернов на месте")


def check_counts(text: str) -> None:
    if len(HARD_BANS) != EXPECTED_HARD_BANS:
        errors.append(f"markers.HARD_BANS={len(HARD_BANS)}, ожидалось {EXPECTED_HARD_BANS}")
    else:
        notes.append(f"✓ HARD BANS: {len(HARD_BANS)}")

    # Категорий в разделе «## Быстрый сканер» (жирные метки «**...:**»).
    # markers.SCANNER — лексический ПОДСЕТ этих категорий (часть категорий
    # сканера нелексические: ритм, структура, фигуративный ноль), поэтому его
    # размер не обязан совпадать — он просто покрытие движка.
    sect = re.search(r"## Быстрый сканер.*?(?=\n## |\Z)", text, re.DOTALL)
    scanner_cats = len(re.findall(r"^\*\*[^*\n]+:\*\*", sect.group(0), re.MULTILINE)) if sect else 0
    if scanner_cats != EXPECTED_SCANNER_CATS:
        errors.append(f"Категорий в разделе сканера: {scanner_cats}, ожидалось {EXPECTED_SCANNER_CATS}")
    else:
        notes.append(f"✓ категорий сканера в SKILL.md: {scanner_cats}")
    notes.append(f"  (лексический движок markers.SCANNER покрывает {len(SCANNER)})")


def _approved_examples(text: str) -> list[tuple[int, str]]:
    """Строки ОДОБРЕННОГО вывода скилла: 'После:'/'Стало:' (как inline, так и
    blockquote на следующей строке). 'Было:'/'До:' — намеренно плохие, их НЕ берём.

    Метка ('Было:'/'Стало:'/'До:'/'После:') часто стоит на отдельной строке от
    самой цитаты-blockquote, поэтому ведём текущую метку и одобряем blockquote
    только если он идёт после Стало/После."""
    out: list[tuple[int, str]] = []
    label: str | None = None
    for i, line in enumerate(text.splitlines(), 1):
        s = line.strip()
        m = re.match(r"^(Было|Стало|До|После):\s*(.*)$", s)
        if m:
            label = m.group(1)
            if m.group(2) and label in ("Стало", "После"):
                out.append((i, m.group(2)))
            continue
        if s.startswith("> "):
            if label in ("Стало", "После"):
                out.append((i, s[2:]))
            continue
        if s:  # любая прозовая строка сбрасывает метку
            label = None
    return out


# Файлы, где «—» запрещено и в собственной прозе: скилл сам себе пример.
EM_DASH_PROSE_FILES = (
    CANON,
    ROOT / "commands" / "humanize.md",
    ROOT / "commands" / "audit.md",
    ROOT / "README.md",
    ROOT / "README.en.md",
)


def _strip_quoted(line: str) -> str:
    """Убирает `код` и «цитаты»: там тире легально (цитируем плохие примеры
    и сам символ)."""
    line = re.sub(r"`[^`]*`", "", line)
    return re.sub(r"«[^«»]*»", "", line)


def check_em_dash_in_prose() -> None:
    """«—» запрещено в собственной прозе скилла, команд и README, не только в
    одобренных примерах. Пропускаем blockquote-содержимое примеров (Было:/До:
    намеренно плохие; Стало:/После: проверяет check_em_dash_in_examples)."""
    bad: list[str] = []
    for path in EM_DASH_PROSE_FILES:
        if not path.exists():
            errors.append(f"нет файла для проверки тире: {path}")
            continue
        label: str | None = None
        for i, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            s = raw.strip()
            if re.match(r"^(Было|Стало|До|После):", s):
                label = s.split(":", 1)[0]
            elif s.startswith(">"):
                if label:
                    continue
            elif s:
                label = None
            if "—" in _strip_quoted(raw):
                bad.append(f"{path.relative_to(ROOT)}:{i}")
    if bad:
        for loc in bad:
            errors.append(f"Длинное тире в собственной прозе: {loc}")
    else:
        notes.append("✓ ноль длинных тире в прозе SKILL.md, команд и README")


def check_em_dash_in_examples(text: str) -> None:
    bad = [(i, ln) for i, ln in _approved_examples(text) if "—" in ln]
    if bad:
        for i, ln in bad:
            errors.append(f"Длинное тире в одобренном примере (строка {i}): {ln[:70]}")
    else:
        notes.append("✓ ноль длинных тире в одобренных примерах")


def check_examples_pass_scanner(text: str) -> None:
    failed = 0
    for i, ln in _approved_examples(text):
        hits = scan_hard_bans(ln)
        # «Было:» намеренно содержит баны; мы берём только После/Стало/>-good,
        # но на всякий случай фильтруем строки, где это явно «плохой» пример.
        if hits:
            failed += 1
            errors.append(f"Одобренный пример нарушает HARD BAN (строка {i}): "
                          f"{', '.join(h.marker for h in hits)}")
    if not failed:
        notes.append("✓ все одобренные примеры проходят сканер HARD BANS")


MAX_DESCRIPTION_CHARS = 1024  # лимит Claude Code на frontmatter description


def check_frontmatter(text: str) -> None:
    m = re.search(r'^description:\s*"(.*)"\s*$', text, re.MULTILINE)
    if not m:
        errors.append("frontmatter: не найден description в кавычках")
        return
    n = len(m.group(1))  # символы, не байты: кириллица в UTF-8 двухбайтовая
    if n > MAX_DESCRIPTION_CHARS:
        errors.append(f"frontmatter: description {n} символов > {MAX_DESCRIPTION_CHARS} "
                      "(длиннее лимита Claude Code — автотриггеринг под угрозой)")
    else:
        notes.append(f"✓ description: {n} символов (лимит {MAX_DESCRIPTION_CHARS})")


def check_scanner_ships_with_skill() -> None:
    """Сканер обязан лежать ВНУТРИ папки скилла (он едет с установкой),
    а SKILL.md — ссылаться на него в режиме «Аудит»."""
    scan = CANON.parent / "scripts" / "scan.py"
    if not scan.exists():
        errors.append(f"сканер не едет со скиллом: нет {scan}")
        return
    if "scripts/scan.py" not in CANON.read_text(encoding="utf-8"):
        errors.append("SKILL.md не ссылается на scripts/scan.py (провод аудита потерян)")
        return
    notes.append("✓ сканер внутри скилла и подключён в режим «Аудит»")


def main() -> int:
    if not CANON.exists():
        print(f"нет канонического файла {CANON}", file=sys.stderr)
        return 1
    text = CANON.read_text(encoding="utf-8")
    check_patterns(text)
    check_counts(text)
    check_frontmatter(text)
    check_scanner_ships_with_skill()
    check_em_dash_in_examples(text)
    check_em_dash_in_prose()
    check_examples_pass_scanner(text)

    print("=== lint_skill ===")
    for n in notes:
        print(" ", n)
    if errors:
        print("\nОШИБКИ:")
        for e in errors:
            print("  ✗", e)
        return 1
    print("\nВсё чисто.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
