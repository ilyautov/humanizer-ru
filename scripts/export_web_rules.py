#!/usr/bin/env python3
"""Экспорт правил сканера для браузерной версии: docs/scan-rules.js.

Онлайн-аудит на сайте считает те же баны, маркеры и штрафы, что scan.py, но
на JavaScript. Чтобы веб не стал вторым расходящимся сканером, правила не
переписываются руками: этот скрипт читает markers.py, score.py, burstiness.py,
structure.py, lexical.py и repeats.py и печатает их в один JS-файл. В CI стоит `--check`:
если файл в репозитории отличается от свежего экспорта, сборка падает.

Что переводится из Python-регулярок в JavaScript (флаги `iu`):
- `\\b` в Python знает кириллицу, в JS только ASCII. Заменяется на явную
  границу через lookaround по `\\p{L}\\p{N}_`, в любой позиции паттерна.
- `\\w` в Python это буквы/цифры/подчёркивание любого алфавита, в JS ASCII.
  Заменяется на класс `[\\p{L}\\p{N}_]`; внутри `[...]` не встречается, скрипт
  это проверяет.
- Локальных флагов `(?-i:...)` нет в части браузеров. Паттерн с ними уходит
  с флагами `gu` (регистрозависимо): группа `(?-i:X)` становится `(?:X)`, а
  буквы вне таких групп раскрываются в пары `[аА]`. Классы `[...]` вне
  `(?-i:...)` в таком паттерне скрипт не переводит и падает. Паритет
  проверяет scripts/test_web_parity.py на корпусе.
Литеральные фразы уходят как есть, экранирует их уже JS.

Использование:
  python scripts/export_web_rules.py            # перезаписать docs/scan-rules.js
  python scripts/export_web_rules.py --check    # гейт: файл актуален?
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "humanizer-ru" / "scripts"))

from humanizer_metrics import (burstiness, lexical, markdown, markers,  # noqa: E402
                                morphology, repeats, score, structure)

OUT = ROOT / "docs" / "scan-rules.js"

# Граница слова, одинаковая для начала и конца: слева буква и справа нет,
# либо слева нет и справа буква.
JS_BOUNDARY = r"(?:(?<=[\p{L}\p{N}_])(?![\p{L}\p{N}_])|(?<![\p{L}\p{N}_])(?=[\p{L}\p{N}_]))"
JS_WORD = r"[\p{L}\p{N}_]"


def js_rule(pattern: str) -> dict:
    """{"re": ..., "flags": ...} для одной Python-регулярки."""
    if "(?-i:" in pattern:
        return {"re": py_to_js(case_sensitive_js(pattern)), "flags": "gu"}
    return {"re": py_to_js(pattern)}


def case_sensitive_js(pattern: str) -> str:
    """Python-регулярка с локальными `(?-i:...)` под флагом IGNORECASE как
    регистрозависимая JS-регулярка: внутри групп `(?-i:...)` всё как есть, вне
    их каждая буква раскрыта в `[аА]`. Нумерация захватов не меняется."""
    out: list[str] = []
    i, strict = 0, []  # strict: глубины скобок, на которых открыта (?-i:
    depth = 0
    while i < len(pattern):
        c = pattern[i]
        if c == "\\":
            out.append(pattern[i:i + 2])
            i += 2
            continue
        if pattern.startswith("(?-i:", i):
            depth += 1
            strict.append(depth)
            out.append("(?:")
            i += 5
            continue
        if c == "[":
            end = i + 1
            while pattern[end] != "]":
                end += 2 if pattern[end] == "\\" else 1
            if not strict:
                raise SystemExit(f"[export] класс [...] вне (?-i:...): {pattern!r}")
            out.append(pattern[i:end + 1])
            i = end + 1
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            if strict and strict[-1] == depth:
                strict.pop()
            depth -= 1
        if not strict and c.lower() != c.upper():
            out.append(f"[{c.lower()}{c.upper()}]")
        else:
            out.append(c)
        i += 1
    return "".join(out)


def py_to_js(pattern: str) -> str:
    if "(?-i" in pattern or "(?i" in pattern:
        raise SystemExit(f"[export] локальные флаги без перевода: {pattern!r}")
    # \w внутри класса символов менять нельзя (получится вложенный класс).
    depth = 0
    i = 0
    while i < len(pattern):
        c = pattern[i]
        if c == "\\":
            if pattern[i + 1] in "wb" and depth > 0:
                raise SystemExit(f"[export] \\{pattern[i + 1]} внутри [...]: {pattern!r}")
            i += 2
            continue
        if c == "[":
            depth += 1
        elif c == "]" and depth:
            depth -= 1
        i += 1
    out = pattern.replace(r"\b", JS_BOUNDARY).replace(r"\w", JS_WORD)
    return out


def scanner_rules() -> dict[str, list[dict]]:
    cats: dict[str, list[dict]] = {}
    for cat, phrases in markers.SCANNER.items():
        rows = []
        for phrase in phrases:
            if isinstance(phrase, tuple):
                rows.append({"label": phrase[0], **js_rule(phrase[1])})
            elif phrase.startswith("re:"):
                rows.append({"label": phrase[3:], **js_rule(phrase[3:])})
            else:
                rows.append({"label": phrase, "lit": phrase})
        cats[cat] = rows
    return cats


def build() -> dict:
    return {
        "generated_by": "scripts/export_web_rules.py",
        "hard_bans": [{"name": n, **js_rule(p)} for n, p in markers.HARD_BANS],
        "freq_bans": markers.FREQ_BANS,
        "scanner": scanner_rules(),
        "genre_muted_bans": {g: sorted(v) for g, v in markers.GENRE_MUTED_BANS.items()},
        "genre_muted_categories": {g: sorted(v) for g, v in markers.GENRE_MUTED_CATEGORIES.items()},
        "genres": list(markers.GENRES),
        "score": {
            "em_dash_name": score.EM_DASH_NAME,
            "copy_paste_category": score.COPY_PASTE_CATEGORY,
            "signature_category": score.SIGNATURE_CATEGORY,
            "signature_first": score.SIGNATURE_FIRST,
            "signature_next": score.SIGNATURE_NEXT,
            "signature_max": score.SIGNATURE_MAX,
            "chat_wrap_category": score.CHAT_WRAP_CATEGORY,
            "chat_wrap_each": score.CHAT_WRAP_EACH,
            "chat_wrap_max": score.CHAT_WRAP_MAX,
            "band_clean": score.BAND_CLEAN,
            "band_edit": score.BAND_EDIT,
            "cv_human_target": burstiness.CV_HUMAN_TARGET,
            "density_min_words": score.DENSITY_MIN_WORDS,
            "para_cv_ai": structure.PARA_CV_AI,
            "para_min_count": structure.PARA_MIN_COUNT,
            "listicle_share_ai": structure.LISTICLE_SHARE_AI,
            "listicle_min_items": structure.LISTICLE_MIN_ITEMS,
            "human_zero_share": list(score.HUMAN_ZERO_SHARE),
            "sterile_min_words": score.STERILE_MIN_WORDS,
            "staccato_max_words": burstiness.STACCATO_MAX_WORDS,
            "staccato_min_run": burstiness.STACCATO_MIN_RUN,
            "staccato_penalty": score.STACCATO_PENALTY,
            "staccato_penalty_max": score.STACCATO_PENALTY_MAX,
            "nv_target": morphology.NV_TARGET,
            "nv_max_penalty": score.NV_PENALTY_MAX,
            "lex_window": lexical.LEX_WINDOW,
            "lex_max_tokens": lexical.LEX_MAX_TOKENS,
            "lex_min_tokens": lexical.LEX_MIN_TOKENS,
            "lex_threshold": score.LEX_THRESHOLD,
            "lex_slope": score.LEX_SLOPE,
            "lex_penalty_max": score.LEX_PENALTY_MAX,
            "lex_muted_genres": sorted(score.LEX_MUTED_GENRES),
        },
        "markdown": {"quote_max_words": markdown.QUOTE_MAX_WORDS, "gap": markdown.GAP},
        "repeats": {
            "n": repeats.REPEAT_N,
            "max_tokens": repeats.REPEAT_MAX_TOKENS,
            "min_content": repeats.REPEAT_MIN_CONTENT,
            "min_phrases": repeats.REPEAT_MIN_PHRASES,
            "show": score.REPEAT_SHOW,
            "function_words": sorted(repeats.FUNCTION_WORDS),
        },
    }


def render() -> str:
    body = json.dumps(build(), ensure_ascii=False, indent=1)
    return (
        "// Сгенерировано scripts/export_web_rules.py из humanizer_metrics.\n"
        "// Не править руками: гейт `export_web_rules.py --check` в CI сравнит с источником.\n"
        f"globalThis.HUMANIZER_RULES = {body};\n"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="не писать, только сравнить с docs/scan-rules.js")
    args = ap.parse_args()
    fresh = render()
    if args.check:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current != fresh:
            print(f"[export] ✗ {OUT.relative_to(ROOT)} отстаёт от markers.py/score.py: "
                  "запустите python scripts/export_web_rules.py")
            return 1
        n = len(markers.HARD_BANS)
        m = sum(len(v) for v in markers.SCANNER.values())
        print(f"[export] ✓ scan-rules.js актуален: банов {n}, маркеров {m}")
        return 0
    OUT.write_text(fresh, encoding="utf-8")
    print(f"[export] записан {OUT.relative_to(ROOT)} ({len(fresh)} байт)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
