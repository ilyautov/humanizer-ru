#!/usr/bin/env python3
"""Добыча кандидатов в маркеры из размеченного корпуса.

Зачем. `ainl_calibration.py` умеет ПРОВЕРЯТЬ готовый маркер на корпусе, но не
умеет его НАХОДИТЬ. Каталог собран руками, и разделяющая сила измерена только у
части паттернов, остальные держатся на вкусе автора. Этот скрипт делает обратную
операцию: берёт размеченный корпус и вытаскивает из него n-граммы, которые чаще
встречаются у моделей, чем у людей.

Метод. Леммы, n-граммы длиной 2-4 внутри предложения, Apriori-отсечение по опоре
(длинная n-грамма считается только если её части пережили отсев). Для каждого
кандидата считается доля ДОКУМЕНТОВ класса, где он встретился, как в калибровке.

Три фильтра, и каждый вырос из измеренного провала (см. eval/AINL-CALIBRATION.md):
  1. опора: редкая n-грамма даёт красивый lift на шуме;
  2. два семейства моделей: маркер, который есть только у одного генератора, это
     привычка этого генератора, а не след машины (наш класс `unknown` не ловится
     как раз поэтому);
  3. проверка на отложенном сплите: кандидат обязан удержать lift на dev, где
     есть невиданная модель.
Фильтр «держится на двух доменах» здесь НЕ применяется: AINL это один домен
(научные аннотации). Для многодоменного корпуса его надо добавить.

⚠ Что скрипт НЕ делает. Он не отличает стиль от темы: если у моделей другая
лексика по существу, она всплывёт как «маркер». Он не знает регистра: канцелярит
в аннотации это норма жанра, и на корпусе он выглядит отлично. И он не говорит,
чем заменять. Выход отсюда это СПИСОК КАНДИДАТОВ на разметку носителем языка, а
не готовый каталог. Отгружать его пользователю без ручной приёмки нельзя.

Запуск:
    python eval/mine_patterns.py --per-class 3000
    python eval/mine_patterns.py --per-class 3000 --validate dev
    python eval/mine_patterns.py --per-class 300 --top 40      # быстрый прогон
    python eval/mine_patterns.py --csv свой.csv                # свой корпус
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "skills" / "humanizer-ru" / "scripts"))
sys.path.insert(0, str(ROOT / "eval"))

from ainl_calibration import LABEL_ALIASES, load  # noqa: E402
from humanizer_metrics.markers import scan_hard_bans, scan_markers  # noqa: E402

MIN_N, MAX_N = 2, 4
OUT_TEMPLATE = "mined-{split}.json"


def _deps():
    try:
        import pymorphy3
        from razdel import sentenize, tokenize
    except ImportError:
        print("[ошибка] нужны razdel и pymorphy3: pip install -r requirements.txt",
              file=sys.stderr)
        raise SystemExit(2)
    return pymorphy3.MorphAnalyzer(), sentenize, tokenize


def build_lemmatizer(morph):
    @lru_cache(maxsize=200_000)
    def lemma(word: str) -> str:
        return morph.parse(word)[0].normal_form
    return lemma


def doc_sentences(text: str, sentenize, tokenize, lemma) -> list[tuple[list[str], list[str]]]:
    """Предложения как пара (леммы, исходные словоформы).

    N-граммы строятся ВНУТРИ предложения: иначе через точку склеиваются куски
    разных фраз и получается мусор вроде «работы заключение».
    """
    out = []
    for s in sentenize(text):
        surface, lemmas = [], []
        for t in tokenize(s.text):
            w = t.text.lower().replace("ё", "е")
            # Только кириллица: цифры, латиница и пунктуация в n-граммах дают
            # темовой мусор вместо стиля.
            if not w.isalpha() or not all("а" <= c <= "я" for c in w):
                continue
            surface.append(w)
            lemmas.append(lemma(w))
        if len(lemmas) >= MIN_N:
            out.append((lemmas, surface))
    return out


def sample_rows(rows: list[dict], per_class: int, lo: int, hi: int) -> list[tuple[str, str]]:
    """Ровная выборка по классу внутри окна длины.

    Две ловушки корпуса, обе измерены перед тем как сюда попасть.
    Первая: файл сгруппирован по меткам (39 переключений на 35 158 строк), и
    «первые N строк класса» это сплошной блок, отсортированный по тематике. Берём
    равномерный шаг по всему блоку.
    Вторая: классы сильно разной длины (человек 103 слова медианы, gemma 61).
    Документная частота растёт с длиной, поэтому без окна длинный класс
    автоматически «богаче на маркеры». Окно уравнивает экспозицию.
    """
    by_label: dict[str, list[str]] = defaultdict(list)
    for r in rows:
        text = r["text"]
        if lo <= len(text.split()) <= hi:
            by_label[LABEL_ALIASES.get(r["label"], r["label"])].append(text)
    out: list[tuple[str, str]] = []
    for label, texts in by_label.items():
        step = max(1, len(texts) // per_class)
        out.extend((label, t) for t in texts[::step][:per_class])
    return out


def mine(docs: list[tuple[str, list]], classes: list[str], min_docs: int):
    """Apriori по n-граммам: считаем документную частоту по классам.

    На каждом уровне выживают только n-граммы с достаточной опорой, и уровень
    n+1 строится ТОЛЬКО из выживших префиксов. Без этого счётчик 4-грамм на
    35 тысячах документов не помещается в память.
    """
    idx = {c: i for i, c in enumerate(classes)}
    counts: dict[tuple[str, ...], list[int]] = {}
    examples: dict[tuple[str, ...], str] = {}
    survivors: set[tuple[str, ...]] = set()

    for n in range(MIN_N, MAX_N + 1):
        level: dict[tuple[str, ...], list[int]] = {}
        level_examples: dict[tuple[str, ...], str] = {}
        for label, sents in docs:
            j = idx[label]
            seen: set[tuple[str, ...]] = set()
            for lemmas, surface in sents:
                for k in range(len(lemmas) - n + 1):
                    key = tuple(lemmas[k:k + n])
                    if n > MIN_N and (key[:-1] not in survivors or key[1:] not in survivors):
                        continue
                    if key in seen:
                        continue
                    seen.add(key)
                    row = level.get(key)
                    if row is None:
                        row = level[key] = [0] * len(classes)
                        level_examples[key] = " ".join(surface[k:k + n])
                    row[j] += 1
        survivors = {k for k, row in level.items() if sum(row) >= min_docs}
        counts.update({k: level[k] for k in survivors})
        examples.update({k: level_examples[k] for k in survivors})
        print(f"  n={n}: {len(level)} кандидатов, прошло опору {len(survivors)}", file=sys.stderr)
        if not survivors:
            break
    return counts, examples


def rates(row: list[int], totals: list[int]) -> list[float]:
    return [100.0 * c / t if t else 0.0 for c, t in zip(row, totals)]


def covered_by_catalog(example: str) -> str | None:
    """Ловит ли кандидата действующий каталог. Проверяем по словоформе."""
    for h in scan_hard_bans(example):
        return "БАН: " + h.marker
    for h in scan_markers(example):
        return "кат: " + h.category
    return None


def drop_subsumed(rows: list[dict]) -> list[dict]:
    """Убирает короткую n-грамму, если длинная накрывает почти ту же опору.

    «играть роль» и «играть важный роль» это один паттерн, в отчёте нужен более
    конкретный.
    """
    by_key = {tuple(r["ngram"].split()): r for r in rows}
    drop = set()
    for key, r in by_key.items():
        for other, ro in by_key.items():
            if len(other) <= len(key):
                continue
            if any(other[i:i + len(key)] == key for i in range(len(other) - len(key) + 1)):
                if ro["ai_docs"] >= 0.7 * r["ai_docs"]:
                    drop.add(key)
    return [r for r in rows if tuple(r["ngram"].split()) not in drop]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--split", default="train", choices=("train", "dev"))
    ap.add_argument("--csv", type=Path,
                    help="локальный корпус (колонки text,label) вместо скачивания")
    ap.add_argument("--per-class", type=int, default=3000,
                    help="сколько документов каждого класса брать (память и время)")
    ap.add_argument("--min-support", type=float, default=0.5,
                    help="минимальная доля документов AI-классов, %%")
    ap.add_argument("--min-lift", type=float, default=2.0, help="минимум AI/человек")
    ap.add_argument("--families", type=int, default=2,
                    help="на скольких семействах моделей маркер обязан держаться")
    ap.add_argument("--min-words", type=int, default=40,
                    help="нижняя граница окна длины документа")
    ap.add_argument("--max-words", type=int, default=160,
                    help="верхняя граница окна длины документа")
    ap.add_argument("--validate", choices=("dev", "train"),
                    help="перепроверить выживших на другом сплите (там есть `unknown`)")
    ap.add_argument("--top", type=int, default=60)
    args = ap.parse_args()

    morph, sentenize, tokenize = _deps()
    lemma = build_lemmatizer(morph)

    rows_raw = load(args.csv, None, args.split)
    picked = sample_rows(rows_raw, args.per_class, args.min_words, args.max_words)
    per_class: dict[str, int] = defaultdict(int)
    words: dict[str, list[int]] = defaultdict(list)
    docs: list[tuple[str, list]] = []
    for label, text in picked:
        per_class[label] += 1
        words[label].append(len(text.split()))
        docs.append((label, doc_sentences(text, sentenize, tokenize, lemma)))
        if len(docs) % 2000 == 0:
            print(f"  …разобрано {len(docs)}", file=sys.stderr)

    classes = ["human"] + sorted(set(per_class) - {"human"})
    totals = [per_class[c] for c in classes]
    print("документов: " + ", ".join(
        f"{c}={t} (слов {statistics.mean(words[c]):.0f})" for c, t in zip(classes, totals)),
        file=sys.stderr)

    ai_docs_total = sum(totals[1:])
    min_docs = max(5, int(args.min_support / 100.0 * ai_docs_total))
    counts, examples = mine(docs, classes, min_docs)

    out_rows = []
    for key, row in counts.items():
        r = rates(row, totals)
        human, ai = r[0], sum(row[1:]) / ai_docs_total * 100.0
        if ai < args.min_support:
            continue
        # Сглаживание Лапласа: без него редкая n-грамма с нулём у людей даёт
        # бесконечный lift и вытесняет из топа честные маркеры.
        human_s = 100.0 * (row[0] + 0.5) / (totals[0] + 1)
        lift = ai / human_s
        if lift < args.min_lift:
            continue
        # Фильтр семейств: сколько генераторов дают заметное превышение над людьми.
        holds = sum(1 for x in r[1:] if x >= max(human * 1.5, args.min_support))
        if holds < args.families:
            continue
        out_rows.append({
            "ngram": " ".join(key),
            "example": examples[key],
            "human_pct": round(human, 2),
            "ai_pct": round(ai, 2),
            "lift": round(lift, 1),
            "families": holds,
            "by_class": {c: round(x, 2) for c, x in zip(classes, r)},
            "ai_docs": sum(row[1:]),
            "covered": covered_by_catalog(examples[key]),
        })

    out_rows = drop_subsumed(out_rows)
    out_rows.sort(key=lambda r: (-r["lift"], -r["ai_pct"]))

    if args.validate:
        val_rows = load(None, None, args.validate)
        keys = [tuple(r["ngram"].split()) for r in out_rows]
        wanted = {k for k in keys}
        vtot: dict[str, int] = defaultdict(int)
        vhit: dict[tuple[str, ...], dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for i, row in enumerate(val_rows):
            label = LABEL_ALIASES.get(row["label"], row["label"])
            vtot[label] += 1
            seen: set[tuple[str, ...]] = set()
            for lemmas, _ in doc_sentences(row["text"], sentenize, tokenize, lemma):
                for n in range(MIN_N, MAX_N + 1):
                    for k in range(len(lemmas) - n + 1):
                        key = tuple(lemmas[k:k + n])
                        if key in wanted and key not in seen:
                            seen.add(key)
                            vhit[key][label] += 1
            if i and i % 5000 == 0:
                print(f"  …проверка {i}/{len(val_rows)}", file=sys.stderr)
        vclasses = ["human"] + sorted(set(vtot) - {"human"})
        for r in out_rows:
            key = tuple(r["ngram"].split())
            v = {c: round(100.0 * vhit[key][c] / vtot[c], 2) if vtot[c] else 0.0 for c in vclasses}
            ai_mean = sum(v[c] for c in vclasses if c != "human") / max(1, len(vclasses) - 1)
            r["validation"] = {
                "split": args.validate,
                "by_class": v,
                "lift": round(ai_mean / v["human"], 1) if v["human"] else None,
                "unknown_pct": v.get("unknown"),
            }

    out = ROOT / "eval" / "out" / OUT_TEMPLATE.format(split=args.split)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"classes": classes, "documents": dict(per_class),
                               "min_docs": min_docs, "candidates": out_rows},
                              ensure_ascii=False, indent=2), encoding="utf-8")

    new = [r for r in out_rows if not r["covered"]]
    print(f"\nкандидатов после фильтров: {len(out_rows)}, из них НЕ покрыто каталогом: {len(new)}")
    head = f"\n{'n-грамма':<34}{'чел.%':>7}{'AI%':>7}{'lift':>7}{'сем.':>6}  каталог"
    print(head)
    print("-" * 88)
    for r in out_rows[:args.top]:
        cov = r["covered"] or ""
        print(f"{r['ngram']:<34}{r['human_pct']:>7}{r['ai_pct']:>7}{r['lift']:>7}"
              f"{r['families']:>6}  {cov}")
    print(f"\n[ok] кандидаты -> {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
