#!/usr/bin/env python3
"""Гейт честности примеров: «Факт-замок» применяется к самому скиллу.

Скилл запрещает дописывать факты при правке (SKILL.md, «Факт-замок»): в
результате не может появиться числа, даты, имени или названия, которых не было
в исходнике. Этот гейт проверяет, что собственные примеры скилла это правило не
нарушают. Пример, где «После» содержит выдуманную цифру, учит модель выдумывать
цифры: демонстрация сильнее инструкции.

Что считается фактом:
  * цифры и всё, что из них собрано: 40%, 2023, 13, 10 минут;
  * даты: названия месяцев в любой форме («в марте»);
  * имена собственные: слова с заглавной буквы, неизвестные словарю
    (Стэнфорд), помеченные как Name/Surn/Geox/Orgn (Яндекс), либо стоящие
    не в начале предложения (Fortune 500);
  * латиница целиком: GPT-4, Excel, Python (названия и бренды).

Словесные количества («вдвое», «половина», «два года») выводятся отдельным
списком-предупреждением: они меняют смысл слабее, чем цифра, и часто законны
как пересказ числа из исходника («на 25%» → «на четверть меньше»).

Легальное исключение. Демонстрация «как выглядит правка, когда автор ДАЛ
конкретику» помечается меткой в самом заголовке примера:

    После (факты автора): «...»
    Стало (факты автора):

Метка обязана быть видна читателю: она же объясняет ему, откуда взялись цифры.

Запуск:  python scripts/check_examples.py [--list]
Exit code 1 при любом нарушении — гейт для CI.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "skills" / "humanizer-ru" / "scripts"))
from humanizer_metrics.markers import HARD_BANS  # noqa: E402

FILES = (
    ROOT / "skills" / "humanizer-ru" / "SKILL.md",
    ROOT / "skills" / "humanizer-ru" / "references" / "catalog.md",
    ROOT / "README.md",
    ROOT / "README.en.md",
    ROOT / "commands" / "humanize.md",
    ROOT / "commands" / "audit.md",
)

BAD_LABELS = ("До", "Было")
GOOD_LABELS = ("После", "Стало")
# «После (факты автора):» — явное разрешение на конкретику от автора.
AUTHOR_FACTS_MARK = "факты автора"
INVENTED_QUANTITIES_MIN = 2  # словесных количеств в «После» при исходнике без чисел
# Идиомы с числительными, в которых числа нет: вырезаются до подсчёта фактов.
# Список короткий и проверяемый; порог выше двух был бы компромиссом, через
# который «три проекта, два окупились» проходит без ошибки.
QUANTITY_IDIOMS = (
    r"с\s+одной\s+стороны", r"с\s+другой(\s+стороны)?", r"в\s+два\s+счёта",
    r"одн[оаи]\s+и\s+то\s+же", r"один\s+из", r"одна\s+из", r"одно\s+из", r"ни\s+один",
    r"в\s+один\s+момент", r"в\s+одиночку", r"один\s+на\s+один", r"на\s+первый\s+взгляд",
    r"в\s+первую\s+очередь", r"во\s+вторых", r"в\s+третьих", r"из\s+первых\s+рук",
    r"первым\s+делом", r"вторая\s+половина", r"два\s+слова", r"пара\s+слов", r"раз\s+два",
)
_QUANTITY_IDIOMS_RE = re.compile("|".join(QUANTITY_IDIOMS), re.IGNORECASE)


def strip_quantity_idioms(text: str) -> str:
    return _QUANTITY_IDIOMS_RE.sub(" ", text)

# Метка примера в трёх формах: «До:», «> **Было:** …», «После (факты автора):».
LABEL_RE = re.compile(
    r"^>?\s*\*{0,2}(До|Было|После|Стало)(\s*\(([^)]*)\))?:?\*{0,2}:?\s*(.*)$"
)

MONTHS = (
    "январ", "феврал", "март", "апрел", "ма", "июн", "июл",
    "август", "сентябр", "октябр", "ноябр", "декабр",
)
MONTH_RE = re.compile(
    r"\b(январ|феврал|март|апрел|июн|июл|август|сентябр|октябр|ноябр|декабр)[а-я]*\b",
    re.IGNORECASE,
)

# Мелкие количества и доли: не валят гейт, только заметка. В русском они
# идиоматичны («в одном окне», «с одной стороны») и обычно пересказывают число
# из исходника («на 25%» → «на четверть меньше»).
WORD_QUANTITIES_SOFT = {
    "один", "два", "две", "три", "оба", "обе", "пара",
    "первый", "второй", "третий",
    "вдвое", "втрое", "дважды", "трижды",
    "половина", "треть", "четверть", "полтора",
}
# Крупные числительные словами: «сорок минут», «сто человек». Пересказать
# нечего — такое число либо взято из исходника, либо выдумано.
WORD_NUMERALS_HARD = {
    "четыре", "пять", "шесть", "семь", "восемь", "девять", "десять",
    "одиннадцать", "двенадцать", "пятнадцать", "двадцать", "тридцать",
    "сорок", "пятьдесят", "шестьдесят", "семьдесят", "восемьдесят",
    "девяносто", "сто", "двести", "триста", "тысяча", "миллион", "миллиард",
    "десяток", "сотня", "дюжина",
}

# Одна и та же сущность под разными именами: не считается дописанным фактом.
# Ключ — то, что появилось в «После»; значения — чем она названа в «До».
ALIASES = {
    "ai": ("искусственный", "интеллект", "ии", "нейросеть", "модель"),
    "ии": ("искусственный", "интеллект", "ai", "нейросеть", "модель"),
    "llm": ("модель", "нейросеть", "ai", "ии"),
}

TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z\d\-]*|[А-Яа-яЁё][А-Яа-яЁё\-]*|\d[\d.,:/-]*")

try:
    import pymorphy3

    _MORPH = pymorphy3.MorphAnalyzer()
except ImportError:  # гейт обязан работать и без словаря, просто грубее
    _MORPH = None

PROPER_TAGS = {"Name", "Surn", "Geox", "Orgn", "Patr"}


@dataclass
class Pair:
    path: Path
    line: int
    before: str
    after: str
    author_facts: bool = False
    label: str = "После"
    notes: list[str] = field(default_factory=list)


def _norm(word: str) -> str:
    """Нормальная форма для сравнения: «Стэнфорд» и «Стэнфорда» — одно слово."""
    # «AI-инструменты» токенизируется как «AI-»: дефис на хвосте лишний.
    low = word.lower().replace("ё", "е").strip("-")
    if _MORPH is None:
        return low[:5]  # без словаря сравниваем по основе
    return _MORPH.parse(low)[0].normal_form.replace("ё", "е")


def _is_proper(word: str, at_sentence_start: bool) -> bool:
    if not word[:1].isupper():
        return False
    if word.isascii():
        return True  # латиница: GPT-4, Fortune, Excel
    if _MORPH is None:
        return not at_sentence_start
    p = _MORPH.parse(word.lower())[0]
    if PROPER_TAGS & set(p.tag.grammemes):
        return True
    if not p.is_known:
        return True  # словарь не знает слова с заглавной — почти всегда имя
    return not at_sentence_start


def _sentence_starts(text: str) -> set[int]:
    """Позиции слов, стоящих первыми в предложении."""
    starts = {0}
    for m in re.finditer(r"[.!?…]\s+|^[>\-*]\s+|«|\n", text):
        starts.add(m.end())
    return starts


def facts(text: str) -> tuple[set[str], set[str], set[str]]:
    """(жёсткие факты, словесные количества, латиница) из текста."""
    hard: set[str] = set()
    soft: set[str] = set()
    latin: set[str] = set()
    starts = _sentence_starts(text)
    for m in MONTH_RE.finditer(text):
        hard.add("месяц:" + m.group(1).lower())
    for m in TOKEN_RE.finditer(text):
        tok = m.group(0)
        if tok[0].isdigit():
            digits = re.sub(r"\D", "", tok)
            if digits:
                hard.add("число:" + digits.lstrip("0").rjust(1, "0"))
            continue
        norm = _norm(tok)
        if norm in WORD_QUANTITIES_SOFT:
            soft.add(norm)
            continue
        if norm in WORD_NUMERALS_HARD:
            hard.add("число словами:" + norm)
            continue
        if _is_proper(tok, at_sentence_start=any(abs(m.start() - s) <= 1 for s in starts)):
            key = "имя:" + norm
            hard.add(key)
            if tok.isascii():
                latin.add(norm)
    return hard, soft, latin


def _alias_covered(fact: str, before_words: set[str]) -> bool:
    name = fact.split(":", 1)[1] if ":" in fact else fact
    for alias in ALIASES.get(name, ()):
        if alias in before_words:
            return True
    return False


def _words(text: str) -> set[str]:
    return {_norm(m.group(0)) for m in TOKEN_RE.finditer(text) if not m.group(0)[0].isdigit()}


def collect_pairs(path: Path) -> list[Pair]:
    """Пары «До/После» в двух формах: inline («До: «...»») и блочной
    (метка на своей строке, цитата blockquote ниже)."""
    pairs: list[Pair] = []
    pending: tuple[int, str] | None = None  # ждём «После» к этому «До»
    label: str | None = None
    label_mark = ""
    buf: list[str] = []
    buf_line = 0

    def flush() -> None:
        nonlocal pending, label, buf, label_mark, buf_line
        text = " ".join(buf).strip()
        if label and text:
            if label in BAD_LABELS:
                pending = (buf_line, text)
            elif pending:
                pairs.append(
                    Pair(
                        path=path,
                        line=buf_line,
                        before=pending[1],
                        after=text,
                        author_facts=AUTHOR_FACTS_MARK in label_mark.lower(),
                        label=label,
                    )
                )
                pending = None
        buf = []
        label = None
        label_mark = ""

    for i, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        s = raw.strip()
        m = LABEL_RE.match(s)
        if m:
            flush()
            label = m.group(1)
            label_mark = m.group(3) or ""
            buf_line = i
            if m.group(4):
                buf = [m.group(4)]
                flush_inline = True
            else:
                buf = []
                flush_inline = False
            if flush_inline:
                flush()
            continue
        if s.startswith(">") and label:
            if not buf:
                buf_line = i
            buf.append(s.lstrip("> "))
            continue
        if s and label:
            flush()
    flush()
    return pairs


def check(pair: Pair) -> tuple[list[str], list[str]]:
    """(нарушения, заметки) по одной паре."""
    # Хвост-пояснение в скобках после цитаты («(числа взяты из исходника…)»)
    # — это авторская ремарка о примере, а не сам пример: из проверки убираем.
    after = re.sub(r"»\s*\(.*$", "»", pair.after)
    b_hard, b_soft, _ = facts(pair.before)
    a_hard, a_soft, _ = facts(strip_quantity_idioms(after))
    before_words = _words(pair.before)
    new_hard = sorted(f for f in a_hard - b_hard if not _alias_covered(f, before_words))
    new_soft = sorted(a_soft - b_soft)
    # Словесные количества («три», «вдвое») мягкие, когда пересказывают число
    # из исходника. Если в исходнике количеств нет вовсе, а в правке их два и
    # больше, это не пересказ, а придуманная конкретика: пример «Пост в блог»
    # с «три проекта, два ускорились вдвое, третий» проходил гейт через эту
    # щель. Идиомы с числительными вырезаны заранее (QUANTITY_IDIOMS).
    b_quant = {f for f in b_hard if f.startswith("число")} | b_soft
    if not b_quant and len(new_soft) >= INVENTED_QUANTITIES_MIN:
        new_hard = sorted(set(new_hard) | {f"количество:{w}" for w in new_soft})
        new_soft = []
    return new_hard, new_soft


# Гейт примера аудита в README: подпись «N жёстких банов», строки «⛔ ...» и
# «ЧИСТОТА: N/100» обязаны совпадать с тем, что scan.py печатает на тексте «До»
# из того же README. Класс бага: подпись обещала пять банов, сканер находил три.
README_AUDIT_FILES = (ROOT / "README.md", ROOT / "README.en.md")
SCAN_PY = ROOT / "skills" / "humanizer-ru" / "scripts" / "scan.py"
_BEFORE_RE = re.compile(r"^(?:До|Before):\s*\n>\s*(.+)$", re.MULTILINE)
# Подпись: «Сработали 3 бана из 21» / «3 of the 21 hard-ban phrases fired».
_BAN_COUNT_RE = re.compile(r"\b(\d+)\s+(?:бан\w*\s+из|of\s+the)\s+(\d+)", re.IGNORECASE)
_BAN_LINE_RE = re.compile(r"^\s*⛔\s+(.+?)\s+×\d+", re.MULTILINE)
_SCORE_RE = re.compile(r"ЧИСТОТА:\s*(\d+)/100")


def real_scan(text: str) -> dict:
    with tempfile.NamedTemporaryFile("w", suffix=".txt", encoding="utf-8", delete=False) as f:
        f.write(text)
        name = f.name
    try:
        # exit 1 у scan.py означает «нашёл баны», это штатно
        out = subprocess.run([sys.executable, str(SCAN_PY), name, "--json"],
                             capture_output=True, text=True, encoding="utf-8")
        if out.returncode > 1:
            raise RuntimeError(f"scan.py упал (exit {out.returncode}): {out.stderr[-300:]}")
        data = json.loads(out.stdout)
        data["_score"] = None
        out2 = subprocess.run([sys.executable, str(SCAN_PY), name],
                              capture_output=True, text=True, encoding="utf-8")
        m = _SCORE_RE.search(out2.stdout)
        if m:
            data["_score"] = int(m.group(1))
        return data
    finally:
        Path(name).unlink(missing_ok=True)


def check_readme_audit(path: Path) -> list[str]:
    """Ошибки примера аудита в одном README (пусто = всё сходится)."""
    text = path.read_text(encoding="utf-8")
    rel = path.relative_to(ROOT)
    m = _BEFORE_RE.search(text)
    if not m:
        return [f"{rel}: не найден блок «До:» с исходным текстом примера"]
    start = m.end()
    nxt = text.find("\n## ", start)
    section = text[start: nxt if nxt != -1 else len(text)]
    real = real_scan(m.group(1))
    errors: list[str] = []
    captions = [(int(a), int(b)) for a, b in _BAN_COUNT_RE.findall(section)]
    if not captions:
        errors.append(f"{rel}: в подписи к примеру нет числа сработавших банов")
    for hit, total in captions:
        if hit != real["hard_ban_count"]:
            errors.append(f"{rel}: подпись обещает {hit} банов, сканер находит "
                          f"{real['hard_ban_count']}")
        if total != len(HARD_BANS):
            errors.append(f"{rel}: в подписи всего банов {total}, в движке {len(HARD_BANS)}")
    shown = {x.strip() for x in _BAN_LINE_RE.findall(section)}
    real_names = {name for name, _ in real["hard_bans"]}
    if shown and shown != real_names:
        errors.append(f"{rel}: баны в примере {sorted(shown)} не совпадают с реальными "
                      f"{sorted(real_names)}")
    for sc in (int(x) for x in _SCORE_RE.findall(section)):
        if real["_score"] is not None and sc != real["_score"]:
            errors.append(f"{rel}: в примере ЧИСТОТА {sc}/100, сканер даёт {real['_score']}/100")
    return errors


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--list", action="store_true", help="показать все найденные пары")
    args = ap.parse_args()

    errors: list[str] = []
    notes: list[str] = []
    total = 0
    exempt = 0

    for path in FILES:
        if not path.exists():
            errors.append(f"нет файла для проверки примеров: {path}")
            continue
        for pair in collect_pairs(path):
            total += 1
            rel = path.relative_to(ROOT)
            new_hard, new_soft = check(pair)
            if args.list:
                print(f"— {rel}:{pair.line} {pair.label}"
                      f"{' (факты автора)' if pair.author_facts else ''}")
                print(f"    До:    {pair.before[:90]}")
                print(f"    После: {pair.after[:90]}")
            if pair.author_facts:
                exempt += 1
                if not new_hard:
                    notes.append(
                        f"метка «факты автора» без новых фактов: {rel}:{pair.line} "
                        "(снимите метку, она вводит читателя в заблуждение)")
                continue
            if new_hard:
                errors.append(
                    f"{rel}:{pair.line} — в «{pair.label}» появились факты, которых нет "
                    f"в исходнике: {', '.join(new_hard)}\n"
                    f"      До:    {pair.before[:100]}\n"
                    f"      После: {pair.after[:100]}")
            elif new_soft:
                notes.append(f"{rel}:{pair.line} — словесные количества "
                             f"({', '.join(new_soft)}), проверьте глазами")

    for readme in README_AUDIT_FILES:
        try:
            errors.extend(check_readme_audit(readme))
        except (RuntimeError, ValueError, OSError) as exc:
            errors.append(f"пример аудита {readme.name}: не удалось сверить со сканером: {exc}")

    print("=== check_examples ===")
    print(f"  пар «До/После»: {total}, из них с меткой «факты автора»: {exempt}")
    if _MORPH is None:
        print("  ! pymorphy3 не установлен: сравнение по основам, точность ниже")
    for n in notes:
        print("  ·", n)
    if errors:
        print("\nОШИБКИ (нарушен Факт-замок в собственных примерах):")
        for e in errors:
            print("  ✗", e)
        print("\nЧинить одним из двух способов:\n"
              "  1) переписать «После» так, чтобы новых фактов не было;\n"
              "  2) если пример намеренно показывает правку с конкретикой от\n"
              "     автора — пометить заголовок: «После (факты автора):».")
        return 1
    print("\nВсе примеры проходят Факт-замок; пример аудита в README совпадает со сканером.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
