#!/usr/bin/env python3
"""Self-scan: скилл прогоняет собственную витрину через свои же правила.

lint_skill.py проверяет только одобренные примеры («Стало:»/«После:»). Но
пользователь сначала читает README и сайт, а уже потом SKILL.md. Если в нашей
собственной прозе живёт «является», «в современном мире» или длинное тире —
скилл теряет право требовать этого от других. Гейт закрывает именно эту дыру:
витрина проверяется тем же движком HARD BANS, что и чужой текст.

Что проверяется: README.md, страницы сайта в docs/, SKILL.md, каталог
паттернов, команды, попап и README Chrome-расширения. Отдельно: строковые
литералы docs/*.js, docs/*.ts и extension/*.js на длинное тире.

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
    ROOT / "CONTRIBUTING.md",
    ROOT / "SECURITY.md",
    ROOT / "CONTRIBUTORS.md",
    ROOT / "PRIVACY_POLICY.md",
    ROOT / "SOURCES.md",
    ROOT / "eval" / "README.md",
    ROOT / "commands" / "humanize.md",
    ROOT / "commands" / "audit.md",
    *sorted((ROOT / "docs").glob("*.html")),
    # Chrome-расширение: интерфейс и текст карточки Web Store.
    ROOT / "extension" / "popup.html",
    ROOT / "extension" / "README.md",
]

ALLOW_MARK = "self-scan: ok"

# Строковые литералы скриптов сайта и расширения: они попадают на экран
# (подсказки, вердикты, отчёт), а HTML-гейт их не видит. Здесь не HARD BANS
# целиком, а только длинное тире: оно чаще всего пролезает в шаблонные
# строки вроде «${name} [тире] до N баллов». Комментарии и регулярные
# выражения не проверяются: это не текст для читателя. Данные-примеры с тире
# пишутся escape-последовательностью \u2014, как EXAMPLE в popup.js.
# scan-rules.js не проверяется: его генерирует export_web_rules.py из правил
# сканера, имена правил с тире интерфейс показывает через ruleName().
JS_TARGETS = [
    *sorted(p for p in (ROOT / "docs").glob("*.js") if p.name != "scan-rules.js"),
    *sorted((ROOT / "docs").glob("*.ts")),
    *sorted((ROOT / "extension").glob("*.js")),
]
EM_DASH = "\u2014"

# После этих символов «/» начинает регулярное выражение, а не деление.
_REGEX_PREV = set("(,=:[!&|?{};+-*%<>~^") | {""}
_REGEX_WORDS = ("return", "typeof", "case", "of", "in", "void", "delete", "throw")


def js_string_dashes(src: str) -> list[int]:
    """Номера строк, где длинное тире стоит внутри строкового литерала
    ('…', "…", `…`) JS/TS. Упрощённый лексер: комментарии и регулярки
    пропускает, ${…} внутри шаблона считает частью строки."""
    hits: list[int] = []
    i, n, line = 0, len(src), 1
    prev = ""  # последний значимый символ вне строк и комментариев
    while i < n:
        c = src[i]
        if c == "\n":
            line += 1
            i += 1
            continue
        if c in " \t\r":
            i += 1
            continue
        if src.startswith("//", i):
            j = src.find("\n", i)
            i = n if j < 0 else j
            continue
        if src.startswith("/*", i):
            j = src.find("*/", i + 2)
            j = n if j < 0 else j + 2
            line += src.count("\n", i, j)
            i = j
            continue
        if c in "'\"`":
            q, i = c, i + 1
            while i < n and src[i] != q:
                if src[i] == "\\":
                    i += 2
                    continue
                if src[i] == "\n":
                    line += 1
                elif src[i] == EM_DASH and (not hits or hits[-1] != line):
                    hits.append(line)
                i += 1
            i += 1
            prev = q
            continue
        if c == "/":
            word = re.search(r"([A-Za-z_$]+)\s*$", src[max(0, i - 12):i])
            if prev in _REGEX_PREV or (word and word.group(1) in _REGEX_WORDS):
                i += 1
                in_class = False
                while i < n and src[i] != "\n":
                    ch = src[i]
                    if ch == "\\":
                        i += 2
                        continue
                    if ch == "[":
                        in_class = True
                    elif ch == "]":
                        in_class = False
                    elif ch == "/" and not in_class:
                        break
                    i += 1
                i += 1
                while i < n and src[i].isalpha():
                    i += 1
                prev = "/"
                continue
        prev = c if not (c.isalnum() or c in "_$") else "a"
        i += 1
    return hits


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

    js_checked = 0
    for path in JS_TARGETS:
        js_checked += 1
        rel = path.relative_to(ROOT)
        src_lines = path.read_text(encoding="utf-8").splitlines()
        for ln in js_string_dashes(path.read_text(encoding="utf-8")):
            if ALLOW_MARK in src_lines[ln - 1]:
                continue
            errors.append(f"{rel}:{ln}: длинное тире в строковом литерале: "
                          f"{src_lines[ln - 1].strip()[:90]}")

    print("=== self_scan ===")
    print(f"  проверено файлов витрины: {checked}")
    print(f"  проверено скриптов (строки на экран): {js_checked}")
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
