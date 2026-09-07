#!/usr/bin/env python3
"""Профиль одного живого канала: где стоит гибридный автор и куда он двигался.

Зачем. Все наши «человеческие» корпуса чужие: научные аннотации, национальный
корпус, посты с Пикабу. Ни один из них не описывает того, кого скилл реально
обслуживает, а именно человека, который пишет вместе с моделью и правит руками.
Это распределение («модель плюс автор плюс хуманайзер») мы полдня обсуждали
умозрительно, потому что взять его было негде.

Экспорт Telegram даёт его целиком, да ещё с датами. Отсюда три замера:

  1. Где автор стоит на шкале между человеческим корпусом и машинными ячейками.
  2. Как он двигался во времени, причём периоды раскладываются по версиям
     скилла: у канала и у репозитория общая шкала дат.
  3. Догфудинг: сколько собственных постов автора сканер зовёт машинными. Если
     инструмент ругается на того, кого обслуживает, это надо знать первым.

Данные приватные: экспорт лежит вне репозитория, агрегаты пишутся в gitignored
`eval/out/`. Ничего из этого не коммитится и никуда не уезжает.

Запуск:
    python eval/channel_profile.py ~/Downloads/ChatExport/result.json
    python eval/channel_profile.py result.json --min-words 60
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "eval"))
sys.path.insert(0, str(ROOT / "skills" / "humanizer-ru" / "scripts"))

from author_profiles import distance, features  # noqa: E402
from m4_calibration import DASHES, is_russian  # noqa: E402

from humanizer_metrics import analyze, cleanliness_score  # noqa: E402
from humanizer_metrics.markers import effective_hard_bans, scan_hard_bans, scan_markers  # noqa: E402


def plain_text(msg: dict) -> str:
    """Telegram отдаёт текст списком сущностей: ссылки, код, жирный отдельно."""
    ents = msg.get("text_entities") or []
    if ents:
        return "".join(e.get("text", "") for e in ents)
    raw = msg.get("text")
    if isinstance(raw, str):
        return raw
    return "".join(p if isinstance(p, str) else p.get("text", "") for p in (raw or []))


def release_eras() -> list[tuple[str, str]]:
    """(дата, версия) по тегам репозитория: общая шкала времени с каналом."""
    out = subprocess.run(["git", "tag", "--sort=creatordate",
                          "--format=%(creatordate:short)\t%(refname:short)"],
                         cwd=ROOT, capture_output=True, text=True)
    eras = []
    for line in out.stdout.splitlines():
        date, _, name = line.partition("\t")
        if name.startswith("v"):
            eras.append((date, name))
    return eras


def era_of(date: str, eras: list[tuple[str, str]]) -> str:
    """Какая версия скилла была актуальна на момент публикации поста."""
    current = "до скилла"
    for released, name in eras:
        if released <= date:
            current = name
        else:
            break
    return current


def measure(text: str) -> dict:
    rep = analyze(text)
    words = len(text.split())
    bans = effective_hard_bans(scan_hard_bans(text), words)
    return {
        "words": words,
        "score": cleanliness_score(rep).score,
        "bans": [h.marker for h in bans],
        "marks": 100.0 * sum(h.count for h in scan_markers(text)) / max(1, words),
        "cv": rep.rhythm.cv_len,
        "dashes": {n: text.count(ch) for n, ch in DASHES.items()},
    }


def baseline() -> dict | None:
    """Человеческая база: те же метрики на живых постах Пикабу."""
    path = ROOT / "eval" / "out" / "pikabu-human.jsonl"
    if not path.exists():
        return None
    texts = [json.loads(s)["text"] for s in path.read_text(encoding="utf-8").splitlines() if s]
    rows = [measure(t) for t in texts]
    return {
        "n": len(rows),
        "score": statistics.mean(r["score"] for r in rows),
        "ban_pct": 100.0 * sum(1 for r in rows if r["bans"]) / len(rows),
        "marks": statistics.mean(r["marks"] for r in rows),
        "cv": statistics.mean(r["cv"] for r in rows),
        "em": 100.0 * sum(1 for r in rows if r["dashes"]["U+2014 em dash"]) / len(rows),
        "texts": texts,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("export", type=Path, help="result.json из экспорта Telegram")
    ap.add_argument("--min-words", type=int, default=50)
    args = ap.parse_args()

    data = json.loads(args.export.read_text(encoding="utf-8"))
    eras = release_eras()
    posts = []
    for m in data.get("messages", []):
        if m.get("type") != "message":
            continue
        text = plain_text(m).strip()
        if len(text.split()) < args.min_words or not is_russian(text):
            continue
        posts.append({"text": text, "date": (m.get("date") or "")[:10],
                      "era": era_of((m.get("date") or "")[:10], eras)})
    print(f"[инфо] канал: {data.get('name')}, постов в работе: {len(posts)}", file=sys.stderr)
    if not posts:
        print("[пусто] подходящих постов нет, снизьте --min-words", file=sys.stderr)
        return 1

    for p in posts:
        p.update(measure(p["text"]))

    base = baseline()
    print(f"\n{'период':<16}{'постов':>8}{'слов(мед)':>11}{'score':>8}"
          f"{'бан%':>7}{'марк/100':>10}{'CV':>7}{'тире%':>8}")
    by_era: dict[str, list[dict]] = defaultdict(list)
    for p in posts:
        by_era[p["era"]].append(p)
    order = ["до скилла"] + [v for _, v in eras]
    for era in order:
        rows = by_era.get(era)
        if not rows:
            continue
        print(f"{era:<16}{len(rows):>8}"
              f"{statistics.median(r['words'] for r in rows):>11.0f}"
              f"{statistics.mean(r['score'] for r in rows):>8.1f}"
              f"{100.0 * sum(1 for r in rows if r['bans']) / len(rows):>6.1f}%"
              f"{statistics.mean(r['marks'] for r in rows):>10.2f}"
              f"{statistics.mean(r['cv'] for r in rows):>7.3f}"
              f"{100.0 * sum(1 for r in rows if r['dashes']['U+2014 em dash']) / len(rows):>7.1f}%")
    if base:
        print(f"{'ЧЕЛОВЕК (Пикабу)':<16}{base['n']:>8}{'':>11}{base['score']:>8.1f}"
              f"{base['ban_pct']:>6.1f}%{base['marks']:>10.2f}{base['cv']:>7.3f}"
              f"{base['em']:>7.1f}%")

    print("\nдогфудинг: как сканер судит собственного автора")
    bands = defaultdict(int)
    for p in posts:
        bands["чисто" if p["score"] >= 85 else
              ("правка" if p["score"] >= 60 else "рерайт")] += 1
    for band in ("чисто", "правка", "рерайт"):
        print(f"  {band:<10}{bands[band]:>5}  ({100.0 * bands[band] / len(posts):.1f}%)")
    worst = sorted(posts, key=lambda p: p["score"])[:5]
    print("  худшие посты:")
    for p in worst:
        names = ", ".join(sorted(set(p["bans"]))[:3]) or "без банов"
        print(f"    {p['date']}  score {p['score']:>3}  {names}")

    top_bans: defaultdict[str, int] = defaultdict(int)
    for p in posts:
        for b in set(p["bans"]):
            top_bans[b] += 1
    print("\nчаще всего срабатывает на этом авторе:")
    for name, c in sorted(top_bans.items(), key=lambda kv: -kv[1])[:8]:
        print(f"  {100.0 * c / len(posts):>5.1f}%  {name}")

    print("\nустойчивость почерка (стилометрия, половина против половины):")
    half = len(posts) // 2
    early, late = [p["text"] for p in posts[:half]], [p["text"] for p in posts[half:]]
    own = distance(features(early), features(late))
    print(f"  автор сам с собой, ранние против поздних:  {own:>7.3f}")
    if base:
        vs_human = distance(features([p["text"] for p in posts]), features(base["texts"]))
        print(f"  автор против человеческой базы Пикабу:     {vs_human:>7.3f}")
        print(f"  отношение:                                {vs_human / own if own else 0:>7.2f}")

    out = ROOT / "eval" / "out" / "channel.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "channel": data.get("name"), "posts": len(posts),
        "by_era": {era: {
            "posts": len(rows),
            "score": round(statistics.mean(r["score"] for r in rows), 1),
            "ban_pct": round(100.0 * sum(1 for r in rows if r["bans"]) / len(rows), 1),
            "marks_per_100": round(statistics.mean(r["marks"] for r in rows), 2),
            "cv": round(statistics.mean(r["cv"] for r in rows), 3),
        } for era, rows in by_era.items()},
        "bands": dict(bands),
        "top_bans": dict(sorted(top_bans.items(), key=lambda kv: -kv[1])[:12]),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[ok] агрегаты -> {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
