#!/usr/bin/env python3
"""Калибровка маркеров по внешнему размеченному корпусу AINL-Eval 2025.

Зачем. Наш собственный корпус это десятки текстов, и человеческий контроль в
нём маленький. AINL-Eval 2025 (shared task конференции AINL) даёт 35 158
русских научных аннотаций с разметкой по автору: `human`, `gpt-4-turbo`,
`gemma-2-27b`, `llama-3.3-70b`. Это первая возможность померить ложные
срабатывания каталога на человеческом русском тексте в масштабе.

Что считает. Долю ДОКУМЕНТОВ с попаданием на класс для каждого HARD BAN и
каждой категории быстрого сканера, плюс сводку по документам с жанровым
фильтром и без. Колонка «человек» это ложные срабатывания, отношение AI к
человеку это разделяющая сила маркера.

Данные НЕ коммитятся. Корпус лежит в открытом репозитории организаторов, но
файла лицензии там нет, поэтому скрипт скачивает его во временную папку.
Машинные агрегаты пишутся в `eval/out/ainl-<split>.json` (папка в .gitignore), а в
репозиторий едет только человекочитаемый отчёт `eval/AINL-CALIBRATION.md`,
который обновляется руками по итогам прогона.

Запуск:
    python eval/ainl_calibration.py                  # train, скачает во временную папку
    python eval/ainl_calibration.py --split dev      # плюс класс `unknown`
    python eval/ainl_calibration.py --csv путь.csv   # взять готовый файл
    python eval/ainl_calibration.py --limit 4000     # быстрый прогон на выборке

Требуется сеть при первом запуске. В CI НЕ гоняется: внешний источник,
несколько минут работы и 48 МБ трафика.
"""

from __future__ import annotations

import argparse
import csv
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

BASE = "https://raw.githubusercontent.com/iis-research-team/AINL-Eval-2025/main/data/"
# train: четыре класса, все модели известны. dev: те же плюс `unknown` — тексты
# модели, которой в train нет. Это проверка на генератор, которого мы не видели.
SPLITS = {"train": "train.csv", "dev": "dev_full.csv"}
# В dev-выгрузке человеческий класс называется `abstract`.
LABEL_ALIASES = {"abstract": "human"}
OUT_TEMPLATE = "ainl-{split}.json"


def load(csv_path: Path | None, limit: int | None, split: str) -> list[dict]:
    if csv_path is None:
        cache = Path(tempfile.gettempdir()) / f"ainl_{split}.csv"
        if not cache.exists():
            url = BASE + SPLITS[split]
            print(f"[скачиваю] {url} -> {cache}", file=sys.stderr)
            urllib.request.urlretrieve(url, cache)  # noqa: S310 (фиксированный https-адрес)
        csv_path = cache
    csv.field_size_limit(10 ** 7)
    with csv_path.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    return rows[:limit] if limit else rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", type=Path, help="локальный train.csv вместо скачивания")
    ap.add_argument("--limit", type=int, help="взять только первые N строк")
    ap.add_argument("--genre", default="academic", help="жанровый профиль для сводки")
    ap.add_argument("--split", choices=sorted(SPLITS), default="train",
                    help="train (четыре класса) или dev (плюс невиданная модель `unknown`)")
    args = ap.parse_args()

    rows = load(args.csv, args.limit, args.split)
    labels = {LABEL_ALIASES.get(r["label"], r["label"]) for r in rows}
    classes = ["human"] + sorted(labels - {"human"})
    totals: dict[str, int] = defaultdict(int)
    doc_hits: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    strict_any: dict[str, int] = defaultdict(int)
    genre_any: dict[str, int] = defaultdict(int)
    soft_per_doc: dict[str, list[int]] = defaultdict(list)

    for i, row in enumerate(rows):
        text = row["text"]
        label = LABEL_ALIASES.get(row["label"], row["label"])
        if label not in classes:
            continue
        totals[label] += 1
        words = len(text.split())

        bans = effective_hard_bans(scan_hard_bans(text), words)
        for h in bans:
            doc_hits["БАН: " + h.marker][label] += 1
        if bans:
            strict_any[label] += 1
        if mute_by_genre(bans, args.genre, GENRE_MUTED_BANS):
            genre_any[label] += 1

        marks = scan_markers(text)
        for h in marks:
            doc_hits["кат: " + h.category][label] += 1
        soft_per_doc[label].append(
            sum(h.count for h in mute_by_genre(marks, args.genre, GENRE_MUTED_CATEGORIES)))

        if i and i % 5000 == 0:
            print(f"  …{i}/{len(rows)}", file=sys.stderr)

    def rate(marker: str, cls: str) -> float:
        return 100.0 * doc_hits[marker][cls] / totals[cls] if totals[cls] else 0.0

    table = []
    for marker in doc_hits:
        human = rate(marker, "human")
        ai = statistics.mean(rate(marker, c) for c in classes[1:])
        table.append({
            "marker": marker,
            "human": round(human, 1),
            **{c: round(rate(marker, c), 1) for c in classes[1:]},
            "lift": round(ai / human, 1) if human else None,
        })
    table.sort(key=lambda r: -r["human"])

    # На --limit в выборку может не попасть какой-то класс: делим только там,
    # где документы есть.
    present = [c for c in classes if totals[c]]
    if not present:
        print("[ошибка] в выборке нет ни одного размеченного класса", file=sys.stderr)
        return 2
    summary = {
        "split": args.split,
        "documents": {c: totals[c] for c in present},
        "strict_any_ban_pct": {c: round(100.0 * strict_any[c] / totals[c], 1) for c in present},
        f"{args.genre}_any_ban_pct": {c: round(100.0 * genre_any[c] / totals[c], 1) for c in present},
        "soft_markers_per_doc": {c: round(statistics.mean(soft_per_doc[c]), 2) for c in present},
    }

    out = ROOT / "eval" / "out" / OUT_TEMPLATE.format(split=args.split)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"summary": summary, "markers": table},
                              ensure_ascii=False, indent=2), encoding="utf-8")

    print("\nдокументов: " + ", ".join(f"{c}={totals[c]}" for c in present))
    print("\nдоля документов с баном:")
    for key in ("strict_any_ban_pct", f"{args.genre}_any_ban_pct"):
        print(f"  {key:<26}" + "  ".join(f"{c}={summary[key][c]}%" for c in present))
    head = f"\n{'маркер':<44}{'чел.%':>8}{'AI/чел':>8}"
    print(head)
    print("-" * (len(head) - 1))
    for r in table[:15]:
        lift = "∞" if r["lift"] is None else r["lift"]
        print(f"{r['marker']:<44}{r['human']:>8}{str(lift):>8}")
    print(f"\n[ok] агрегаты -> {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
