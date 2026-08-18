#!/usr/bin/env python3
"""Self-scan: скилл прогоняет собственную витрину через свои же правила.

lint_skill.py проверяет только одобренные примеры («Стало:»/«После:»). Но
пользователь сначала читает README и сайт, а уже потом SKILL.md. Если в нашей
собственной прозе живёт «является», «в современном мире» или длинное тире —
скилл теряет право требовать этого от других. Гейт закрывает именно эту дыру:
витрина проверяется тем же движком HARD BANS, что и чужой текст.

Что проверяется: README.md, страницы сайта в docs/, SKILL.md, каталог
паттернов, команды.

Что вырезается перед проверкой (это цитаты, а не наша речь):
  * блоки кода, инлайн-код, HTML-теги, script/style;
  * «текст в ёлочках» — так мы цитируем плохие примеры и слова-маркеры;
  * плохая половина примеров: строка «До:»/«Было:» и её blockquote;
  * ссылки в markdown и href: адреса не проза.

Исключения. Строка, где бан стоит осознанно (мета-разговор о самом бане),
помечается комментарием на этой же строке:

    <!-- self-scan: ok — цитируем сам бан -->

Запуск:  python scripts/self_scan.py [--show-text FILE]
Exit code 1 при любом бане в прозе — гейт для CI.
"""

from __future__ import annotations

import argparse
import html
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "skills" / "humanizer-ru" / "scripts"))

from humanizer_metrics.markers import scan_hard_bans  # noqa: E402

TARGETS = [
    ROOT / "README.md",
    ROOT / "skills" / "humanizer-ru" / "SKILL.md",
    ROOT / "skills" / "humanizer-ru" / "references" / "catalog.md",
    ROOT / "commands" / "humanize.md",
    ROOT / "commands" / "audit.md",
    *sorted((ROOT / "docs").glob("*.html")),
]

ALLOW_MARK = "self-scan: ok"


# Вырезанное заменяется этим символом, а не пробелом: иначе «От «В современном
# мире…» и «Стоит отметить…» до клише» схлопывается в «От и до» и ловится как
# ложный диапазон. Заглушка не буква — фразовые регексы через неё не склеиваются.
GAP = "·"


def _blank(match: re.Match[str]) -> str:
    """Заменяет вырезанное заглушкой, сохраняя переводы строк и смещения:
    номера строк в отчёте должны совпадать с файлом."""
    return re.sub(r"[^\n]", GAP, match.group(0))


def strip_html(text: str) -> str:
    text = re.sub(r"(?is)<(script|style)\b.*?</\1>", _blank, text)
    text = re.sub(r"(?is)<pre\b.*?</pre>", _blank, text)
    text = re.sub(r"(?is)<code\b.*?</code>", _blank, text)
    text = re.sub(r"(?s)<!--.*?-->", _blank, text)
    text = re.sub(r"(?s)<[^>]+>", _blank, text)
    return html.unescape(text)


def strip_markdown(text: str) -> str:
    text = re.sub(r"(?s)```.*?```", _blank, text)
    text = re.sub(r"`[^`\n]*`", _blank, text)
    text = re.sub(r"\]\([^)\n]*\)", _blank, text)  # адрес ссылки, текст остаётся
    text = re.sub(r"^\s*\[[^\]]+\]:\s*\S+$", _blank, text, flags=re.MULTILINE)
    return text


def strip_quotes(text: str) -> str:
    """Ёлочки — наш способ цитировать чужой плохой текст и слова-маркеры."""
    return re.sub(r"«[^«»]*»", _blank, text)


def strip_bad_examples(text: str) -> str:
    """Плохая половина пар «До/После»: сама метка и её blockquote."""
    out: list[str] = []
    in_bad = False
    for raw in text.splitlines():
        s = raw.strip()
        m = re.match(r"^>?\s*\*{0,2}(До|Было|После|Стало)(?:\s*\([^)]*\))?:?\*{0,2}:?", s)
        if m:
            in_bad = m.group(1) in ("До", "Было")
            out.append(GAP * len(raw) if in_bad else raw)
            continue
        if in_bad and (s.startswith(">") or s):
            out.append(GAP * len(raw))
            continue
        if not s:
            in_bad = False
        out.append(raw)
    return "\n".join(out)


# Разделы, которые целиком состоят из цитат чужих маркеров: это словарь
# сканера, а не наша речь. Проверять его собственными банами бессмысленно.
SKIP_SECTIONS = ("Быстрый сканер",)


def strip_marker_sections(text: str) -> str:
    out: list[str] = []
    skipping = False
    for raw in text.splitlines():
        m = re.match(r"^(#{2,6})\s+(.*)$", raw)
        if m:
            skipping = any(name in m.group(2) for name in SKIP_SECTIONS)
        out.append(GAP * len(raw) if skipping else raw)
    return "\n".join(out)


def prose_of(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    # Строки с явной пометкой снимаются целиком: там бан цитируется осознанно.
    text = "\n".join(
        GAP * len(line) if ALLOW_MARK in line else line for line in text.splitlines()
    )
    if path.suffix == ".html":
        text = strip_html(text)
    else:
        text = strip_marker_sections(strip_markdown(text))
    text = strip_bad_examples(text)
    return strip_quotes(text)


def line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def snippet(text: str, pos: int, width: int = 70) -> str:
    start = max(0, pos - width // 3)
    return " ".join(text[start:start + width].split())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--show-text", metavar="FILE",
                    help="напечатать очищенную прозу файла (отладка правил вырезания)")
    args = ap.parse_args()

    if args.show_text:
        print(prose_of(Path(args.show_text)))
        return 0

    errors: list[str] = []
    checked = 0
    for path in TARGETS:
        if not path.exists():
            errors.append(f"нет файла для self-scan: {path}")
            continue
        checked += 1
        prose = prose_of(path)
        rel = path.relative_to(ROOT)
        for hit in scan_hard_bans(prose):
            for pos in hit.positions:
                errors.append(f"{rel}:{line_of(prose, pos)} — HARD BAN «{hit.marker}»: "
                              f"…{snippet(prose, pos)}…")

    print("=== self_scan ===")
    print(f"  проверено файлов витрины: {checked}")
    if errors:
        print(f"\nОШИБКИ: собственная проза нарушает {len(errors)} раз(а) свои же HARD BANS:")
        for e in errors:
            print("  ✗", e)
        print("\nЧинить: переписать фразу. Если бан цитируется осознанно — "
              f"добавить в строку пометку «{ALLOW_MARK}».")
        return 1
    print("\nВитрина проходит собственные HARD BANS.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
