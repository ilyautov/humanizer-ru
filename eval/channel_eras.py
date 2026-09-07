#!/usr/bin/env python3
"""Что менялось в живом канале: отдельно от модели, отдельно от скилла.

Зачем. В канале одного автора время склеивает два фактора: версию Opus, которой
он пишет, и версию скилла, которым правит. По периодам их не разделить, они
двигались вместе. Но даты релизов не совпадают, и в календаре остаются окна, где
меняется РОВНО ОДНО:

  модель меняется, скилл стоит   → чистое сравнение поколений Opus по-русски;
  скилл меняется, модель стоит   → чистая оценка эффекта наших же правок.

Первого замера не существует ни у кого: публичные корпуса про русский стоят на
генераторах 2023-2024 годов. Второй мы обязаны иметь про себя.

Что считает:
  1. Раскладку постов по парам (Opus, скилл) и какие окна пригодны для вывода.
  2. Метрики сканера по каждому окну.
  3. Лемма-n-граммы, которые появились или исчезли между соседними периодами,
     той же машиной, что и eval/mine_patterns.py.

Данные приватные: экспорт лежит вне репозитория, в `eval/out/` едут агрегаты.

Запуск:
    python eval/channel_eras.py ~/Downloads/ChatExport/result.json
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "eval"))
sys.path.insert(0, str(ROOT / "skills" / "humanizer-ru" / "scripts"))

from channel_profile import plain_text  # noqa: E402
from m4_calibration import is_russian  # noqa: E402
from mine_patterns import MAX_N, MIN_N, _deps, build_lemmatizer, doc_sentences  # noqa: E402

from humanizer_metrics import analyze, cleanliness_score  # noqa: E402
from humanizer_metrics.markers import effective_hard_bans, scan_hard_bans, scan_markers  # noqa: E402

# Даты официальных релизов Opus. Автор переходил вместе с ними, поэтому дата
# поста однозначно задаёт модель, которой он тогда пользовался.
OPUS_RELEASES = [
    ("2025-11-24", "Opus 4.5"),
    ("2026-02-05", "Opus 4.6"),
    ("2026-04-16", "Opus 4.7"),
    ("2026-05-28", "Opus 4.8"),
    ("2026-07-24", "Opus 5"),
]


def version_at(date: str, releases: list[tuple[str, str]], before: str) -> str:
    current = before
    for released, name in releases:
        if released <= date:
            current = name
        else:
            break
    return current


def skill_releases() -> list[tuple[str, str]]:
    out = subprocess.run(["git", "tag", "--sort=creatordate",
                          "--format=%(creatordate:short)\t%(refname:short)"],
                         cwd=ROOT, capture_output=True, text=True)
    rel = []
    for line in out.stdout.splitlines():
        date, _, name = line.partition("\t")
        if name.startswith("v"):
            # Один день может нести несколько тегов; для окна важен последний.
            rel = [r for r in rel if r[0] != date] + [(date, name)]
    return sorted(rel)


def metrics(text: str) -> dict:
    rep = analyze(text)
    words = len(text.split())
    return {
        "words": words,
        "score": cleanliness_score(rep).score,
        "bans": len(effective_hard_bans(scan_hard_bans(text), words)),
        "marks": 100.0 * sum(h.count for h in scan_markers(text)) / max(1, words),
        "cats": {h.category for h in scan_markers(text)},
        "cv": rep.rhythm.cv_len,
        "em": text.count("—"),
        "sent_len": rep.rhythm.mean_len,
    }


def ngram_counts(texts: list[str], lemma, sentenize, tokenize) -> tuple[Counter, int]:
    """Документная частота лемма-n-грамм: в скольких постах встретилась."""
    docs: Counter[tuple[str, ...]] = Counter()
    for text in texts:
        seen = set()
        for lemmas, _ in doc_sentences(text, sentenize, tokenize, lemma):
            for n in range(MIN_N, MAX_N + 1):
                for k in range(len(lemmas) - n + 1):
                    seen.add(tuple(lemmas[k:k + n]))
        docs.update(seen)
    return docs, len(texts)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("export", type=Path)
    ap.add_argument("--min-words", type=int, default=40)
    ap.add_argument("--min-posts", type=int, default=8,
                    help="меньше этого в окне — не выводим, шум")
    ap.add_argument("--top", type=int, default=12)
    args = ap.parse_args()

    skill = skill_releases()
    data = json.loads(args.export.read_text(encoding="utf-8"))
    posts = []
    for m in data.get("messages", []):
        if m.get("type") != "message":
            continue
        text = plain_text(m).strip()
        if len(text.split()) < args.min_words or not is_russian(text):
            continue
        date = (m.get("date") or "")[:10]
        posts.append({"text": text, "date": date,
                      "opus": version_at(date, OPUS_RELEASES, "до Opus 4.5"),
                      "skill": version_at(date, skill, "до скилла")})
    posts.sort(key=lambda p: p["date"])
    print(f"[инфо] постов: {len(posts)}, период {posts[0]['date']} .. {posts[-1]['date']}",
          file=sys.stderr)
    for p in posts:
        p.update(metrics(p["text"]))

    # --- 1. Раскладка по парам ------------------------------------------
    cells: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for p in posts:
        cells[(p["opus"], p["skill"])].append(p)
    print("\nраскладка постов по парам (модель × скилл):")
    print(f"{'Opus':<14}{'скилл':<14}{'постов':>8}{'период':>26}")
    for (opus, sk), rows in sorted(cells.items(), key=lambda kv: kv[1][0]["date"]):
        print(f"{opus:<14}{sk:<14}{len(rows):>8}"
              f"{rows[0]['date'] + ' .. ' + rows[-1]['date']:>26}")

    def summarize(label: str, rows: list[dict]) -> None:
        print(f"  {label:<34}{len(rows):>5}"
              f"{statistics.mean(r['score'] for r in rows):>8.1f}"
              f"{statistics.mean(r['marks'] for r in rows):>10.2f}"
              f"{100.0 * sum(1 for r in rows if r['em']) / len(rows):>8.1f}%"
              f"{statistics.mean(r['cv'] for r in rows):>8.3f}"
              f"{statistics.mean(r['sent_len'] for r in rows):>8.1f}")

    header = (f"  {'окно':<34}{'n':>5}{'score':>8}{'марк/100':>10}"
              f"{'тире%':>9}{'CV':>8}{'длина':>8}")

    # --- 2. Окна, где меняется ровно одно --------------------------------
    print("\nМОДЕЛЬ МЕНЯЕТСЯ, СКИЛЛ СТОИТ (сравнение поколений Opus по-русски)")
    print(header)
    by_skill: dict[str, list[dict]] = defaultdict(list)
    for p in posts:
        by_skill[p["skill"]].append(p)
    shown = 0
    for sk, rows in by_skill.items():
        groups = defaultdict(list)
        for r in rows:
            groups[r["opus"]].append(r)
        usable = {k: v for k, v in groups.items() if len(v) >= args.min_posts}
        if len(usable) > 1:
            for opus, g in sorted(usable.items(), key=lambda kv: kv[1][0]["date"]):
                summarize(f"скилл {sk} · {opus}", g)
            shown += 1
    if not shown:
        print("  нет окна, где при одной версии скилла набралось бы два поколения модели")

    print("\nСКИЛЛ МЕНЯЕТСЯ, МОДЕЛЬ СТОИТ (эффект наших правок)")
    print(header)
    by_opus: dict[str, list[dict]] = defaultdict(list)
    for p in posts:
        by_opus[p["opus"]].append(p)
    shown = 0
    for opus, rows in by_opus.items():
        groups = defaultdict(list)
        for r in rows:
            groups[r["skill"]].append(r)
        usable = {k: v for k, v in groups.items() if len(v) >= args.min_posts}
        if len(usable) > 1:
            for sk, g in sorted(usable.items(), key=lambda kv: kv[1][0]["date"]):
                summarize(f"{opus} · скилл {sk}", g)
            shown += 1
    if not shown:
        print("  нет окна, где при одной модели набралось бы две версии скилла")

    # --- 3. Что появилось и что ушло -------------------------------------
    morph, sentenize, tokenize = _deps()
    lemma = build_lemmatizer(morph)
    eras = sorted({p["opus"] for p in posts},
                  key=lambda o: min(p["date"] for p in posts if p["opus"] == o))
    print("\nОБОРОТЫ, КОТОРЫЕ ПОЯВИЛИСЬ И УШЛИ (лемма-n-граммы, доля постов периода)")
    prev_name, prev = None, None
    for era in eras:
        texts = [p["text"] for p in posts if p["opus"] == era]
        if len(texts) < args.min_posts:
            continue
        docs, n = ngram_counts(texts, lemma, sentenize, tokenize)
        if prev is not None:
            pd, pn = prev
            deltas = []
            for gram in set(docs) | set(pd):
                a, b = 100.0 * pd[gram] / pn, 100.0 * docs[gram] / n
                # Порог по опоре: одиночное вхождение это не тренд, а совпадение.
                if max(pd[gram], docs[gram]) >= max(3, n // 8):
                    deltas.append((b - a, " ".join(gram), a, b))
            deltas.sort(reverse=True)
            print(f"\n  {prev_name} → {era}   (постов {pn} → {n})")
            print(f"    {'появилось':<34}{'было':>8}{'стало':>8}")
            for _, gram, a, b in deltas[:args.top]:
                print(f"    {gram[:33]:<34}{a:>7.0f}%{b:>7.0f}%")
            print(f"    {'ушло':<34}{'было':>8}{'стало':>8}")
            for _, gram, a, b in deltas[-args.top:][::-1]:
                print(f"    {gram[:33]:<34}{a:>7.0f}%{b:>7.0f}%")
        prev_name, prev = era, (docs, n)

    # --- 4. Категории маркеров по периодам --------------------------------
    print("\nКАТЕГОРИИ МАРКЕРОВ ПО ПОКОЛЕНИЯМ МОДЕЛИ (доля постов)")
    cats = sorted({c for p in posts for c in p["cats"]})
    usable_eras = [e for e in eras if sum(1 for p in posts if p["opus"] == e) >= args.min_posts]
    print(f"    {'категория':<30}" + "".join(f"{e.replace('Opus ', ''):>9}" for e in usable_eras))
    for cat in cats:
        row = []
        for era in usable_eras:
            rows = [p for p in posts if p["opus"] == era]
            row.append(100.0 * sum(1 for p in rows if cat in p["cats"]) / len(rows))
        if max(row) >= 5:
            print(f"    {cat[:29]:<30}" + "".join(f"{v:>8.0f}%" for v in row))

    out = ROOT / "eval" / "out" / "channel-eras.json"
    out.write_text(json.dumps({
        "posts": len(posts),
        "cells": {f"{o} | {s}": len(v) for (o, s), v in cells.items()},
        "by_opus": {e: {
            "posts": sum(1 for p in posts if p["opus"] == e),
            "score": round(statistics.mean(p["score"] for p in posts if p["opus"] == e), 1),
            "marks_per_100": round(statistics.mean(p["marks"] for p in posts if p["opus"] == e), 2),
            "em_dash_pct": round(100.0 * sum(1 for p in posts if p["opus"] == e and p["em"])
                                 / sum(1 for p in posts if p["opus"] == e), 1),
        } for e in eras},
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[ok] агрегаты -> {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
