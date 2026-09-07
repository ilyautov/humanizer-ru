#!/usr/bin/env python3
"""Есть ли у автора собственный почерк, отличимый от его же шума.

Зачем. Каталог целится в «человека вообще», и это работает, пока правишь один
текст. На корпусе так нельзя: универсальные правила, приложенные к сотне тысяч
документов, снимают отпечаток модели и ставят на его место свой, общий у всех,
кто пользуется тем же каталогом. Мишенью должен быть не средний человек, а
конкретный автор.

Прежде чем это строить, надо проверить посылку, а она не самоочевидна:
**различаются ли авторы сильнее, чем шумит один автор**. Если нет, персональная
калибровка это самообман и универсального каталога достаточно.

Три ловушки, из-за которых первая версия замера дала бессмысленную единицу.

1. `DELETED` это не автор. Под этим именем в дампе слиты все удалённые
   аккаунты, то есть десятки разных людей, и в топ по числу постов такой
   «автор» выходит первым. Отсеиваем по списку служебных имён.
2. Разные объёмы выборки. Между авторами считалось по полным корпусам, внутри
   автора по половинкам вдвое меньше. Шум оценки падает с объёмом, поэтому
   сравнивать так нельзя: обе величины считаются на выборках РОВНО одного
   размера, и обе усредняются по многим случайным разбиениям.
3. Не тот набор признаков. Частоты наших ИИ-маркеров это не почерк: на посте в
   175 слов почти все они нули. Почерк живёт в служебных словах, длине
   предложений и пунктуации, то есть в классической стилометрии.

Что считает. Для каждого автора вектор признаков (служебные слова, ритм,
морфология, пунктуация), затем три величины на выборках равного размера:

  ВНУТРИ (случайно)      два случайных куска одного автора — чистый шум оценки;
  ВНУТРИ (по времени)    ранние посты против поздних — шум ПЛЮС развитие автора;
  МЕЖДУ                  куски разных авторов — шум плюс разница почерков.

Отношение МЕЖДУ к ВНУТРИ (случайно) и есть ответ. Разница между двумя ВНУТРИ
это отдельный ответ: измеренный дрейф автора во времени.

Данные: дамп Пикабу (`username`, `timestamp`), корпус НЕ коммитится.

Запуск:
    python eval/author_profiles.py --mb 1000 --authors 20 --min-posts 40
    python eval/author_profiles.py --report
"""

from __future__ import annotations

import argparse
import json
import random
import re
import statistics
import sys
import tempfile
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "eval"))
sys.path.insert(0, str(ROOT / "skills" / "humanizer-ru" / "scripts"))

from m4_calibration import is_russian  # noqa: E402

from humanizer_metrics.burstiness import rhythm  # noqa: E402
from humanizer_metrics.morphology import morph_stats  # noqa: E402

DUMP = "https://huggingface.co/datasets/IlyaGusev/pikabu/resolve/main/00.jsonl.zst"
OUT = ROOT / "eval" / "out" / "authors"

# Служебные имена: под ними пишет не человек, а система или редакция.
NOT_AUTHORS = {"DELETED", "deleted", "moderator", "admin", "Pikabu"}

# Классика стилометрии: служебные слова частотны, от темы не зависят и автором
# не контролируются. Именно поэтому по ним и опознают авторство.
FUNCTION_WORDS = """и в не на я что он с как а то все она так его но да ты к у же вы за бы
по только ее мне было вот от меня еще нет о из ему теперь когда даже ну вдруг ли если уже или
ни быть был него до вас нибудь опять уж вам сказал ведь там потом себя ничего ей может они тут
где есть надо ней для мы тебя их чем была сам чтоб без будто человек чего раз тоже себе под
жизнь будет ж тогда кто этот того потому этого какой совсем ним здесь этом один почти мой тем
чтобы нее были куда зачем всех очень""".split()

_WORD_RE = re.compile(r"[а-яёА-ЯЁ]+")
PUNCT = {"запятая": ",", "тире": "-", "скобка": "(", "восклицание": "!",
         "вопрос": "?", "многоточие": "…", "двоеточие": ":", "кавычка": "«"}


def prefix_file(mb: int) -> Path:
    """Кусок дампа на диске: по нему нужно два прохода, качать дважды глупо."""
    cache = Path(tempfile.gettempdir()) / f"pikabu-{mb}mb.jsonl.zst"
    if not cache.exists():
        print(f"[скачиваю] {mb} МБ дампа -> {cache}", file=sys.stderr)
        req = urllib.request.Request(DUMP, headers={"Range": f"bytes=0-{mb * 10**6}"})
        cache.write_bytes(urllib.request.urlopen(req).read())  # noqa: S310
    return cache


def stream_records(path: Path):
    """Построчно из zst-потока. Обрыв на границе куска это норма, а не ошибка."""
    import zstandard

    with path.open("rb") as fh:
        reader = zstandard.ZstdDecompressor().stream_reader(fh)
        tail = b""
        try:
            while True:
                chunk = reader.read(1 << 20)
                if not chunk:
                    break
                lines = (tail + chunk).split(b"\n")
                tail = lines.pop()
                for line in lines:
                    try:
                        yield json.loads(line)
                    except Exception:
                        continue
        except Exception:
            return


def usable(rec: dict, lo: int, hi: int) -> str | None:
    text = (rec.get("text_markdown") or "").strip()
    words = len(text.split())
    if not (lo <= words <= hi) or text.count("http") > 2 or "![" in text:
        return None
    return text if is_russian(text) else None


def collect(mb: int, authors: int, min_posts: int, lo: int, hi: int) -> int:
    path = prefix_file(mb)
    counts: Counter[str] = Counter()
    for rec in stream_records(path):
        name = rec.get("username")
        if name and name not in NOT_AUTHORS and usable(rec, lo, hi):
            counts[name] += 1
    eligible = [(n, c) for n, c in counts.most_common() if c >= min_posts]
    print(f"[инфо] авторов с {min_posts}+ постами: {len(eligible)}, берём "
          f"{min(authors, len(eligible))}", file=sys.stderr)
    if len(eligible) < 2:
        print("[мало] увеличьте --mb или снизьте --min-posts", file=sys.stderr)
        return 0

    wanted = {n for n, _ in eligible[:authors]}
    by_author: dict[str, list[dict]] = defaultdict(list)
    for rec in stream_records(path):
        name = rec.get("username")
        if name in wanted:
            text = usable(rec, lo, hi)
            if text:
                by_author[name].append({"text": text, "timestamp": rec.get("timestamp"),
                                        "id": rec.get("id")})

    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.jsonl"):
        old.unlink()
    for name, posts in by_author.items():
        posts.sort(key=lambda p: p["timestamp"] or 0)  # ось развития автора
        safe = "".join(c if c.isalnum() else "_" for c in name)[:40]
        (OUT / f"{safe}.jsonl").write_text(
            "".join(json.dumps({**p, "username": name}, ensure_ascii=False) + "\n"
                    for p in posts), encoding="utf-8")
        print(f"  {name}: {len(posts)} постов", file=sys.stderr)
    return len(by_author)


def features(texts: list[str]) -> dict[str, float]:
    """Стилометрический вектор куска корпуса: всё на 1000 слов или в долях."""
    joined = "\n\n".join(texts)
    words = _WORD_RE.findall(joined.lower())
    n = max(1, len(words))
    freq = Counter(words)
    vec = {f"сл:{w}": 1000.0 * freq[w] / n for w in FUNCTION_WORDS}
    for name, ch in PUNCT.items():
        vec[f"пункт:{name}"] = 1000.0 * joined.count(ch) / n
    r = rhythm(joined)
    vec["ритм:средняя длина"] = r.mean_len
    vec["ритм:cv"] = 100.0 * r.cv_len
    vec["ритм:коротких"] = 100.0 * r.short_share
    vec["ритм:длинных"] = 100.0 * r.long_share
    m = morph_stats(joined)
    vec["морф:сущ/глаг"] = 10.0 * m.noun_verb_ratio
    vec["слово:средняя длина"] = 10.0 * statistics.mean(len(w) for w in words) if words else 0.0
    return vec


def distance(a: dict[str, float], b: dict[str, float]) -> float:
    """Средняя разница по объединению признаков, в единицах самих признаков."""
    keys = set(a) | set(b)
    return statistics.mean(abs(a.get(k, 0.0) - b.get(k, 0.0)) for k in keys) if keys else 0.0


def report(reps: int, seed: int) -> int:
    files = sorted(OUT.glob("*.jsonl")) if OUT.exists() else []
    corpora = {}
    for path in files:
        posts = [json.loads(s) for s in path.read_text(encoding="utf-8").splitlines() if s]
        if posts:
            corpora[posts[0]["username"]] = [p["text"] for p in posts]
    if len(corpora) < 2:
        print("[пусто] нужно минимум два автора, запустите без --report", file=sys.stderr)
        return 1

    names = sorted(corpora)
    # Кусок фиксированного размера везде один и тот же: иначе сравниваем не
    # почерки, а точность оценки на разных объёмах.
    k = min(len(v) for v in corpora.values()) // 2
    rng = random.Random(seed)
    print(f"[инфо] авторов: {len(names)}, кусок: {k} постов, повторов: {reps}",
          file=sys.stderr)

    within_rand: dict[str, list[float]] = defaultdict(list)
    between: list[float] = []
    for _ in range(reps):
        halves = {}
        for name in names:
            posts = corpora[name][:]
            rng.shuffle(posts)
            halves[name] = (features(posts[:k]), features(posts[k:2 * k]))
            within_rand[name].append(distance(*halves[name]))
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                between.append(distance(halves[a][0], halves[b][0]))

    within_time = {}
    for name in names:
        posts = corpora[name]
        within_time[name] = distance(features(posts[:k]), features(posts[-k:]))

    print(f"\n{'автор':<26}{'постов':>8}{'шум':>9}{'дрейф':>9}")
    for name in names:
        print(f"{name[:25]:<26}{len(corpora[name]):>8}"
              f"{statistics.mean(within_rand[name]):>9.3f}{within_time[name]:>9.3f}")

    noise = statistics.mean(statistics.mean(v) for v in within_rand.values())
    drift = statistics.mean(within_time.values())
    across = statistics.mean(between)
    print(f"\nВНУТРИ автора, случайное разбиение (шум):      {noise:>7.3f}")
    print(f"ВНУТРИ автора, ранние против поздних (дрейф):  {drift:>7.3f}")
    print(f"МЕЖДУ авторами:                                {across:>7.3f}")
    print(f"\nпочерк / шум:   {across / noise if noise else 0:>5.2f}")
    print(f"дрейф / шум:    {drift / noise if noise else 0:>5.2f}")
    print("\nПервое отношение около единицы означает, что авторы неотличимы и\n"
          "персональная калибровка не товар. Второе заметно выше единицы означает,\n"
          "что профиль обязан быть версионным: автор пятилетней давности это\n"
          "другой человек по признакам.")

    out = ROOT / "eval" / "out" / "authors.json"
    out.write_text(json.dumps({
        "authors": {n: len(corpora[n]) for n in names},
        "chunk_posts": k, "reps": reps,
        "within_noise": round(noise, 4), "within_drift": round(drift, 4),
        "between_authors": round(across, 4),
        "style_over_noise": round(across / noise, 2) if noise else None,
        "drift_over_noise": round(drift / noise, 2) if noise else None,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[ok] -> {out.relative_to(ROOT)}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mb", type=int, default=1000, help="сколько МБ дампа тянуть")
    ap.add_argument("--authors", type=int, default=20)
    ap.add_argument("--min-posts", type=int, default=40)
    ap.add_argument("--min-words", type=int, default=80)
    ap.add_argument("--max-words", type=int, default=350)
    ap.add_argument("--reps", type=int, default=20, help="случайных разбиений")
    ap.add_argument("--seed", type=int, default=17)
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args()

    if args.report:
        return report(args.reps, args.seed)
    if not collect(args.mb, args.authors, args.min_posts, args.min_words, args.max_words):
        return 1
    return report(args.reps, args.seed)


if __name__ == "__main__":
    raise SystemExit(main())
