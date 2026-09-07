#!/usr/bin/env python3
"""Калибровка каталога на русской части M4: второй домен и парное сравнение.

Зачем. Вся наша калибровка стояла на научных аннотациях (AINL-Eval), а умолчание
сканера рассчитано на маркетинг и блоги. M4 даёт другой набор регистров:
человеческие тексты там из RuATD (национальный корпус, соцсети, Википедия,
новости, личные дневники, government-документы), а машинные от gpt-3.5-turbo и
davinci-003, которых мы раньше не мерили.

Главное отличие от `ainl_calibration.py`: **корпус парный**. В одной записи
лежат `human_text` и `machine_text` по одному и тому же исходнику, потому что
модель просили переформулировать текст. Тема, предмет и стилевой повод у обеих
половин общие, поэтому сравнение внутри пары честнее, чем сравнение независимых
выборок: в AINL тему приходилось гасить частотным фильтром лемм.

Две поправки, обе выведены из прошлых граблей (см. eval/MINING.md):
  1. Плотность на 100 слов рядом с долей документов. Машинную половину просили
     выдать больше 1000 символов, поэтому она длиннее, а документная частота
     растёт с длиной сама по себе.
  2. Языковой фильтр. В человеческой половине попадаются украинские и
     смешанные тексты, в машинной изредка чужие алфавиты.

Данные НЕ коммитятся: в статье заявлена Apache 2.0, но файла лицензии в
репозитории нет. Скрипт качает во временную папку (около 135 МБ), в репозиторий
едут только числа.

Запуск:
    python eval/m4_calibration.py                 # оба генератора
    python eval/m4_calibration.py --limit 2000    # быстрый прогон
    python eval/m4_calibration.py --genre academic
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import tempfile
import urllib.request
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "skills" / "humanizer-ru" / "scripts"))

from humanizer_metrics.markers import (  # noqa: E402
    GENRE_MUTED_BANS,
    GENRE_MUTED_CATEGORIES,
    effective_hard_bans,
    mute_by_genre,
    scan_hard_bans,
    scan_markers,
)

BASE = "https://raw.githubusercontent.com/mbzuai-nlp/M4/main/data/"
FILES = {"gpt-3.5-turbo": "russian_chatGPT.jsonl", "davinci-003": "russian_davinci.jsonl"}
OUT = "m4.json"

# Буквы, которых в русском алфавите нет. Человеческая половина RuATD местами
# украинская, и без этой проверки она уедет в статистику как «русский человек».
FOREIGN_CYRILLIC = set("іїєґўѣ")
RU = set("абвгдежзийклмнопрстуфхцчшщъыьэюяё")

# Бан «Длинное тире» ловит ровно U+2014. Перепись соседей нужна потому, что на
# первых же парах Пикабу gemma3 выдала дюжину U+2013, которого регулярка не
# видит: если модели ставят короткое тире, бан промахивается мимо цели.
DASHES = {"U+002D дефис": "-", "U+2010 hyphen": "‐", "U+2013 en dash": "–",
          "U+2014 em dash": "—", "U+2015 horbar": "―", "U+2212 minus": "−"}


def is_russian(text: str) -> bool:
    letters = [c for c in text.lower() if c.isalpha()]
    if len(letters) < 50:
        return False
    ru = sum(1 for c in letters if c in RU)
    foreign = sum(1 for c in letters if c in FOREIGN_CYRILLIC)
    return ru / len(letters) > 0.9 and foreign / len(letters) < 0.005


def load(model: str, limit: int | None) -> list[dict]:
    cache = Path(tempfile.gettempdir()) / FILES[model]
    if not cache.exists():
        url = BASE + FILES[model]
        print(f"[скачиваю] {url} -> {cache}", file=sys.stderr)
        urllib.request.urlretrieve(url, cache)  # noqa: S310 (фиксированный https-адрес)
    rows = []
    with cache.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
            if limit and len(rows) >= limit:
                break
    return rows


def measure(text: str, genre: str) -> dict:
    words = len(text.split())
    bans = effective_hard_bans(scan_hard_bans(text), words)
    marks = scan_markers(text)
    return {
        "words": words,
        "bans": [h.marker for h in bans],
        "bans_genre": [h.marker for h in mute_by_genre(bans, genre, GENRE_MUTED_BANS)],
        "marks": [h.category for h in marks],
        "marks_n": sum(h.count for h in marks),
        "dashes": {name: text.count(ch) for name, ch in DASHES.items()},
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, help="взять только первые N записей на генератор")
    ap.add_argument("--jsonl", type=Path,
                    help="свой парный корпус в том же формате (human_text/machine_text/model)")
    ap.add_argument("--genre", default="academic", help="жанровый профиль для второй сводки")
    args = ap.parse_args()

    side_words: dict[str, list[int]] = defaultdict(list)
    side_docs: dict[str, int] = defaultdict(int)
    side_ban_docs: dict[str, int] = defaultdict(int)
    side_genre_docs: dict[str, int] = defaultdict(int)
    side_density: dict[str, list[float]] = defaultdict(list)
    side_dash_docs: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    marker_docs: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    # Парный счёт: у кого маркеров плотнее внутри одной и той же записи.
    paired: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    skipped = 0

    if args.jsonl:
        rows_by_model: dict[str, list[dict]] = defaultdict(list)
        for line in args.jsonl.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                rows_by_model[r.get("model", "machine")].append(r)
        sources = list(rows_by_model)
    else:
        rows_by_model = {}
        sources = list(FILES)

    for model in sources:
        rows = rows_by_model[model] if args.jsonl else load(model, args.limit)
        print(f"[{model}] записей: {len(rows)}", file=sys.stderr)
        for i, row in enumerate(rows):
            human, machine = row.get("human_text", ""), row.get("machine_text", "")
            if not (is_russian(human) and is_russian(machine)):
                skipped += 1
                continue
            h, m = measure(human, args.genre), measure(machine, args.genre)
            for side, res in (("human", h), (model, m)):
                side_docs[side] += 1
                side_words[side].append(res["words"])
                if res["bans"]:
                    side_ban_docs[side] += 1
                if res["bans_genre"]:
                    side_genre_docs[side] += 1
                side_density[side].append(100.0 * res["marks_n"] / max(1, res["words"]))
                for name, n in res["dashes"].items():
                    if n:
                        side_dash_docs[side][name] += 1
                for name in set(res["bans"]):
                    marker_docs["БАН: " + name][side] += 1
                for cat in set(res["marks"]):
                    marker_docs["кат: " + cat][side] += 1
            hd = 100.0 * h["marks_n"] / max(1, h["words"])
            md = 100.0 * m["marks_n"] / max(1, m["words"])
            paired[model]["машина плотнее" if md > hd else
                          ("человек плотнее" if hd > md else "поровну")] += 1
            if i and i % 2000 == 0:
                print(f"  …{i}/{len(rows)}", file=sys.stderr)

    sides = ["human"] + sources
    print(f"\nпропущено по языковому фильтру: {skipped} пар")
    print("\nсторона           док.   слов(медиана)  хотя бы 1 бан   "
          f"с --genre {args.genre}   маркеров/100 слов")
    for s in sides:
        if not side_docs[s]:
            continue
        print(f"{s:<16}{side_docs[s]:>6}{statistics.median(side_words[s]):>14.0f}"
              f"{100.0 * side_ban_docs[s] / side_docs[s]:>15.1f}%"
              f"{100.0 * side_genre_docs[s] / side_docs[s]:>18.1f}%"
              f"{statistics.mean(side_density[s]):>18.2f}")

    print("\nдоля документов с символом (перепись тире):")
    print(f"{'сторона':<16}" + "".join(f"{n.split()[0]:>12}" for n in DASHES))
    for s in sides:
        if side_docs[s]:
            print(f"{s:<16}" + "".join(
                f"{100.0 * side_dash_docs[s][n] / side_docs[s]:>11.1f}%" for n in DASHES))

    print("\nпарное сравнение внутри записи (плотность маркеров):")
    for model, counts in paired.items():
        total = sum(counts.values()) or 1
        parts = "  ".join(f"{k}: {100.0 * v / total:.1f}%" for k, v in sorted(counts.items()))
        print(f"  {model:<16}{parts}")

    rows_out = []
    for marker, by_side in marker_docs.items():
        human = 100.0 * by_side["human"] / side_docs["human"] if side_docs["human"] else 0.0
        ai = statistics.mean([100.0 * by_side[m] / side_docs[m] for m in sources if side_docs[m]])
        rows_out.append({"marker": marker, "human": round(human, 2),
                         **{m: round(100.0 * by_side[m] / side_docs[m], 2)
                            for m in sources if side_docs[m]},
                         "lift": round(ai / human, 1) if human else None})
    rows_out.sort(key=lambda r: -(r["lift"] or 0))
    head = f"\n{'маркер':<40}{'чел.%':>8}{'AI%':>8}{'AI/чел':>8}"
    print(head)
    print("-" * (len(head) - 1))
    for r in rows_out[:20]:
        ai = statistics.mean([r[m] for m in sources if m in r])
        print(f"{r['marker']:<40}{r['human']:>8}{ai:>8.2f}{str(r['lift'] or '∞'):>8}")

    out = ROOT / "eval" / "out" / OUT
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "documents": {s: side_docs[s] for s in sides},
        "median_words": {s: statistics.median(side_words[s]) for s in sides if side_docs[s]},
        "any_ban_pct": {s: round(100.0 * side_ban_docs[s] / side_docs[s], 1)
                        for s in sides if side_docs[s]},
        f"{args.genre}_any_ban_pct": {s: round(100.0 * side_genre_docs[s] / side_docs[s], 1)
                                      for s in sides if side_docs[s]},
        "markers_per_100_words": {s: round(statistics.mean(side_density[s]), 2)
                                  for s in sides if side_docs[s]},
        "dash_docs_pct": {s: {n: round(100.0 * side_dash_docs[s][n] / side_docs[s], 1)
                              for n in DASHES} for s in sides if side_docs[s]},
        "corpus": str(args.jsonl) if args.jsonl else "M4-ru",
        "paired": {m: dict(c) for m, c in paired.items()},
        "markers": rows_out,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[ok] агрегаты -> {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
