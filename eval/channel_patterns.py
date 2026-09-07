#!/usr/bin/env python3
"""Портрет одного гибридного автора: чем он отличается от человека и от машины.

Зачем. Универсальный каталог целится в «человека вообще». Для энтерпрайза
мишенью должен быть конкретный автор, и первый вопрос к этой идее простой: а что
вообще можно вытащить из корпуса одного человека. У канала на 178 постов около
тридцати тысяч слов. Для лемма-n-грамм это мало (шахте нужны тысячи документов
на класс), для частотного профиля более чем достаточно.

Поэтому здесь три замера, каждый по силам такому объёму:

  1. Стилометрический портрет. Где автор отклоняется от человеческой базы и от
     машинной, признак за признаком. Это и есть «профиль автора» в том виде, в
     каком его можно продать: не список запретов, а вектор частот.
  2. Личные тики. Обороты, частые у него и редкие в человеческой базе. Служебные
     и содержательные разведены: вторые это чаще тема, а не почерк, и путать их
     значит выдавать «он пишет про агентов» за «он так пишет».
  3. Форматирование. Telegram отдаёт разметку сущностями, а жирный, курсив и
     ссылки автор расставляет рукой. Это часть почерка, которую не видит ни один
     текстовый сканер, и заодно ось, где машина ведёт себя очень характерно.

Данные приватные, в `eval/out/` едут агрегаты.

Запуск:
    python eval/channel_patterns.py ~/Downloads/ChatExport/result.json
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "eval"))
sys.path.insert(0, str(ROOT / "skills" / "humanizer-ru" / "scripts"))

from author_profiles import FUNCTION_WORDS, features  # noqa: E402
from channel_profile import plain_text  # noqa: E402
from m4_calibration import is_russian  # noqa: E402
from mine_patterns import MAX_N, MIN_N, _deps, build_lemmatizer, doc_sentences  # noqa: E402

FUNC = set(FUNCTION_WORDS)


def doc_ngrams(texts: list[str], lemma, sentenize, tokenize) -> tuple[Counter, int]:
    docs: Counter[tuple[str, ...]] = Counter()
    for text in texts:
        seen = set()
        for lemmas, _ in doc_sentences(text, sentenize, tokenize, lemma):
            for n in range(MIN_N, MAX_N + 1):
                for k in range(len(lemmas) - n + 1):
                    seen.add(tuple(lemmas[k:k + n]))
        docs.update(seen)
    return docs, len(texts)


def load_channel(path: Path, min_words: int) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for m in data.get("messages", []):
        if m.get("type") != "message":
            continue
        text = plain_text(m).strip()
        if len(text.split()) < min_words or not is_russian(text):
            continue
        kinds = Counter(e.get("type") for e in (m.get("text_entities") or [])
                        if e.get("type") and e.get("type") != "plain")
        out.append({"text": text, "date": (m.get("date") or "")[:10], "entities": kinds})
    return out


def machine_texts() -> list[str]:
    """Машинная база: все посчитанные ячейки матрицы."""
    cells = ROOT / "eval" / "out" / "matrix"
    texts = []
    for p in sorted(cells.glob("*.jsonl")):
        for line in p.read_text(encoding="utf-8").splitlines():
            if line:
                texts.append(json.loads(line)["machine_text"])
    return texts


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("export", type=Path)
    ap.add_argument("--min-words", type=int, default=40)
    ap.add_argument("--top", type=int, default=14)
    ap.add_argument("--min-docs-pct", type=float, default=8.0,
                    help="минимум процентов постов автора, иначе это совпадение")
    args = ap.parse_args()

    posts = load_channel(args.export, args.min_words)
    mine = [p["text"] for p in posts]
    human = [json.loads(s)["text"] for s in
             (ROOT / "eval/out/pikabu-human.jsonl").read_text(encoding="utf-8").splitlines() if s]
    machine = machine_texts()
    print(f"[инфо] автор {len(mine)}, человек {len(human)}, машина {len(machine)}",
          file=sys.stderr)

    # --- 1. Стилометрический портрет -------------------------------------
    fa, fh = features(mine), features(human)
    fm = features(machine) if machine else {}
    keys = set(fa) | set(fh) | set(fm)
    rows = []
    for k in keys:
        a, h, m = fa.get(k, 0.0), fh.get(k, 0.0), fm.get(k, 0.0)
        # Отклонение в долях самой величины: иначе частые служебные слова
        # затопчут всё остальное просто масштабом.
        base = max(h, 0.05)
        rows.append((abs(a - h) / base, k, a, h, m))
    rows.sort(reverse=True)
    head = f"{'признак':<26}{'автор':>10}{'человек':>10}{'машина':>10}{'откл.':>9}"
    print("\nПОРТРЕТ: где автор дальше всего от человеческой базы")
    print(head)
    print("-" * len(head))
    for dev, k, a, h, m in rows[:args.top]:
        print(f"{k[:25]:<26}{a:>10.2f}{h:>10.2f}{m:>10.2f}{dev:>8.0%}")

    print("\nПОРТРЕТ: где автор ближе к машине, чем к человеку")
    near = []
    for _, k, a, h, m in rows:
        if not m:
            continue
        if abs(a - m) * 2 < abs(a - h) and abs(h - m) > 0.05:
            near.append((abs(a - h), k, a, h, m))
    near.sort(reverse=True)
    print(head)
    print("-" * len(head))
    for _, k, a, h, m in near[:args.top]:
        print(f"{k[:25]:<26}{a:>10.2f}{h:>10.2f}{m:>10.2f}{'':>9}")

    # --- 2. Личные тики ---------------------------------------------------
    morph, sentenize, tokenize = _deps()
    lemma = build_lemmatizer(morph)
    da, na = doc_ngrams(mine, lemma, sentenize, tokenize)
    dh, nh = doc_ngrams(human, lemma, sentenize, tokenize)
    tics = []
    for gram, c in da.items():
        share = 100.0 * c / na
        if share < args.min_docs_pct:
            continue
        base = 100.0 * dh[gram] / nh
        lift = share / base if base else None
        if lift is None or lift >= 2.0:
            tics.append((lift if lift else 999.0, share, base, gram))
    tics.sort(reverse=True)
    print(f"\nЛИЧНЫЕ ТИКИ: часто у автора, редко в человеческой базе "
          f"(опора от {args.min_docs_pct:.0f}% постов)")
    print(f"{'оборот':<34}{'у автора':>11}{'у людей':>10}{'лифт':>8}  тип")
    shown_f = shown_c = 0
    for lift, share, base, gram in tics:
        kind = "служебный" if all(w in FUNC for w in gram) else "содержательный"
        if kind == "служебный" and shown_f >= args.top:
            continue
        if kind == "содержательный" and shown_c >= args.top:
            continue
        shown_f += kind == "служебный"
        shown_c += kind == "содержательный"
        mark = "∞" if lift >= 999 else f"{lift:.1f}"
        print(f"{' '.join(gram)[:33]:<34}{share:>10.0f}%{base:>9.1f}%{mark:>8}  {kind}")

    # --- 3. Форматирование ------------------------------------------------
    ent = Counter()
    for p in posts:
        for kind, c in p["entities"].items():
            ent[kind] += c
    print("\nФОРМАТИРОВАНИЕ: разметка, которую автор ставит рукой")
    print(f"{'сущность':<22}{'всего':>9}{'на пост':>10}{'постов с ней':>15}")
    for kind, total in ent.most_common(10):
        with_it = sum(1 for p in posts if p["entities"].get(kind))
        print(f"{kind:<22}{total:>9}{total / len(posts):>10.2f}"
              f"{100.0 * with_it / len(posts):>14.0f}%")

    out = ROOT / "eval" / "out" / "channel-patterns.json"
    out.write_text(json.dumps({
        "posts": len(posts),
        "profile_deviation": [{"feature": k, "author": round(a, 3), "human": round(h, 3),
                               "machine": round(m, 3)} for _, k, a, h, m in rows[:40]],
        "tics": [{"ngram": " ".join(g), "author_pct": round(s, 1), "human_pct": round(b, 2),
                  "lift": None if lift >= 999 else round(lift, 1)}
                 for lift, s, b, g in tics[:60]],
        "entities": dict(ent),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[ok] -> {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
