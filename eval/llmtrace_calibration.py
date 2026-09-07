#!/usr/bin/env python3
"""Калибровка каталога на русской части LLMTrace: 30 генераторов и 8 доменов.

Зачем. AINL дал научные аннотации трёх моделей, M4 дал соцсети и Википедию с
gpt-3.5 и davinci-003. Ни там, ни там нет русских моделей: GigaChat и YandexGPT
мы до сих пор не измеряли, хотя именно их текст чаще всего вставляют в
документы. LLMTrace (Tolstykh et al., arXiv:2509.21269, Apache 2.0) закрывает
дыру: ~340K русских текстов, 8 доменов (статьи, новости, отзывы, ответы на
вопросы, истории, факты, короткая форма, поэзия), 30 генераторов от gpt-3.5 до
o3, GigaChat-Max, YandexGPT-5, Qwen2.5-72B, QwQ и дистиллята DeepSeek-R1.

Как устроен корпус. Каждая запись это один текст с полями label (human/ai),
model, data_type, prompt_type (create / expand / delete / update) и topic_id.
topic_id связывает человеческий исходник с машинными версиями по нему, то есть
часть корпуса парная, как M4: сравнение внутри темы честнее, чем сравнение
независимых выборок.

Что считаем: доля документов хотя бы с одним баном в строгом режиме и с
`--genre`, плотность маркеров на 100 слов, то же по генераторам, доменам и
типам промпта, частота каждого бана у людей против машин (ищем ложные
срабатывания: бан, который у людей чаще, чем у моделей, это не бан), парное
сравнение плотности внутри topic_id.

Оговорки. Человеческие тексты короче (медиана 90 слов против 133), поэтому
документная доля с баном у машин завышена длиной, смотрите на плотность.
Поэзия исключена по умолчанию: строгий режим для неё не предназначен.
Данные не коммитятся: скрипт качает первые 80 МБ test-сплита (весь файл 318 МБ)
во временную папку, в репозиторий едут только числа (eval/out/llmtrace.json).

Запуск:
    python eval/llmtrace_calibration.py
    python eval/llmtrace_calibration.py --limit 3000 --genre academic
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
sys.path.insert(0, str(ROOT / "eval"))

from humanizer_metrics.markers import (  # noqa: E402
    GENRE_MUTED_BANS,
    effective_hard_bans,
    mute_by_genre,
    scan_hard_bans,
    scan_markers,
)
from m4_calibration import is_russian  # noqa: E402

URL = "https://huggingface.co/datasets/iitolstykh/LLMTrace_classification/resolve/main/test.jsonl"
HEAD_BYTES = 80_000_000
OUT = ROOT / "eval" / "out" / "llmtrace.json"
MIN_DOCS = 100  # генераторы с меньшим числом документов в таблицу не идут


def load(limit: int | None) -> list[dict]:
    cache = Path(tempfile.gettempdir()) / "llmtrace_test_head.jsonl"
    if not cache.exists():
        req = urllib.request.Request(URL, headers={"Range": f"bytes=0-{HEAD_BYTES}"})
        print(f"[скачиваю] первые {HEAD_BYTES // 1_000_000} МБ {URL} -> {cache}", file=sys.stderr)
        with urllib.request.urlopen(req, timeout=120) as resp, cache.open("wb") as fh:  # noqa: S310
            fh.write(resp.read())
    rows = []
    with cache.open(encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # оборванная последняя строка
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
        "density": 100.0 * sum(h.count for h in marks) / max(1, words),
        "em_dash": "—" in text,
    }


def pct(part: int, total: int) -> float:
    return round(100.0 * part / total, 1) if total else 0.0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, help="взять только первые N строк файла")
    ap.add_argument("--genre", default="academic", help="жанровый профиль для второй колонки")
    ap.add_argument("--include-poetry", action="store_true", help="не выкидывать домен poetry")
    args = ap.parse_args()

    rows = [r for r in load(args.limit) if r.get("lang") == "ru"]
    if not args.include_poetry:
        rows = [r for r in rows if r.get("data_type") != "poetry"]
    rows = [r for r in rows if is_russian(r["text"])]
    print(f"[llmtrace] русских записей после фильтров: {len(rows)}", file=sys.stderr)

    class Agg:
        def __init__(self) -> None:
            self.docs = 0
            self.words: list[int] = []
            self.ban_docs = 0
            self.genre_docs = 0
            self.density: list[float] = []
            self.dash_docs = 0

        def add(self, m: dict) -> None:
            self.docs += 1
            self.words.append(m["words"])
            self.ban_docs += bool(m["bans"])
            self.genre_docs += bool(m["bans_genre"])
            self.density.append(m["density"])
            self.dash_docs += m["em_dash"]

        def row(self) -> dict:
            return {"docs": self.docs, "median_words": statistics.median(self.words) if self.words else 0,
                    "ban_pct": pct(self.ban_docs, self.docs), "genre_ban_pct": pct(self.genre_docs, self.docs),
                    "density": round(statistics.mean(self.density), 2) if self.density else 0.0,
                    "em_dash_pct": pct(self.dash_docs, self.docs)}

    by_class: dict[str, Agg] = defaultdict(Agg)      # human / ai
    by_model: dict[str, Agg] = defaultdict(Agg)
    by_domain: dict[tuple[str, str], Agg] = defaultdict(Agg)
    by_prompt: dict[str, Agg] = defaultdict(Agg)
    ban_docs: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    cat_docs: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    human_density_by_topic: dict[str, float] = {}
    ai_by_topic: dict[str, list[tuple[str, float]]] = defaultdict(list)

    for i, r in enumerate(rows):
        m = measure(r["text"], args.genre)
        label = r["label"]
        by_class[label].add(m)
        by_domain[(label, r["data_type"])].add(m)
        if label == "ai":
            by_model[r["model"] or "ai?"].add(m)
            by_prompt[r["prompt_type"] or "?"].add(m)
            ai_by_topic[r["topic_id"]].append((r["model"] or "ai?", m["density"]))
        else:
            human_density_by_topic[r["topic_id"]] = m["density"]
        for b in set(m["bans"]):
            ban_docs[b][label] += 1
        for c in set(m["marks"]):
            cat_docs[c][label] += 1
        if i and i % 3000 == 0:
            print(f"  …{i}/{len(rows)}", file=sys.stderr)

    n_h, n_ai = by_class["human"].docs, by_class["ai"].docs
    paired: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for topic, hd in human_density_by_topic.items():
        for model, md in ai_by_topic.get(topic, []):
            key = "машина плотнее" if md > hd else ("человек плотнее" if hd > md else "поровну")
            paired[model][key] += 1
            paired["все генераторы"][key] += 1

    def table(title: str, items: list[tuple[str, Agg]]) -> None:
        print(f"\n{title}")
        print(f"{'сторона':<42}{'док.':>6}{'слов':>7}{'бан':>8}{'--genre':>9}{'марк/100':>10}{'тире':>7}")
        for name, agg in items:
            r = agg.row()
            print(f"{name:<42}{r['docs']:>6}{r['median_words']:>7.0f}{r['ban_pct']:>7.1f}%"
                  f"{r['genre_ban_pct']:>8.1f}%{r['density']:>10.2f}{r['em_dash_pct']:>6.1f}%")

    table("=== классы", [(k, by_class[k]) for k in ("human", "ai")])
    models = sorted(((k, v) for k, v in by_model.items() if v.docs >= MIN_DOCS),
                    key=lambda kv: -kv[1].row()["density"])
    table(f"=== генераторы (≥{MIN_DOCS} документов), по плотности маркеров", models)
    domains = sorted(by_domain.items(), key=lambda kv: (kv[0][1], kv[0][0]))
    table("=== домены: человек против машин", [(f"{d} / {lab}", a) for (lab, d), a in domains])
    table("=== тип промпта у машин", sorted(by_prompt.items()))

    print("\n=== баны: доля документов, человек против машин (ловим ложные срабатывания)")
    print(f"{'бан':<44}{'человек':>9}{'машины':>9}{'отношение':>11}")
    ban_rows = []
    for b, d in ban_docs.items():
        h, a = pct(d["human"], n_h), pct(d["ai"], n_ai)
        ban_rows.append((b, h, a, round(a / h, 2) if h else None))
    for b, h, a, ratio in sorted(ban_rows, key=lambda x: -(x[2] + x[1])):
        print(f"{b[:44]:<44}{h:>8.2f}%{a:>8.2f}%{(str(ratio) if ratio is not None else '∞'):>11}")

    print("\n=== категории маркеров: доля документов")
    cat_rows = sorted(((c, pct(d["human"], n_h), pct(d["ai"], n_ai)) for c, d in cat_docs.items()),
                      key=lambda x: -(x[1] + x[2]))
    for c, h, a in cat_rows:
        print(f"{c[:44]:<44}{h:>8.2f}%{a:>8.2f}%")

    print("\n=== парное сравнение внутри topic_id (плотность маркеров)")
    for model, counts in sorted(paired.items(), key=lambda kv: -sum(kv[1].values())):
        total = sum(counts.values())
        if total < 30:
            continue
        print(f"{model[:40]:<40} n={total:<5} " + "  ".join(
            f"{k}: {pct(v, total):.1f}%" for k, v in sorted(counts.items())))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "source": URL, "head_bytes": HEAD_BYTES, "genre": args.genre, "poetry_included": args.include_poetry,
        "classes": {k: v.row() for k, v in by_class.items()},
        "models": {k: v.row() for k, v in by_model.items()},
        "domains": {f"{lab}/{d}": a.row() for (lab, d), a in by_domain.items()},
        "prompt_types": {k: v.row() for k, v in by_prompt.items()},
        "bans": {b: {"human_pct": h, "ai_pct": a, "ratio": r} for b, h, a, r in ban_rows},
        "categories": {c: {"human_pct": h, "ai_pct": a} for c, h, a in cat_rows},
        "paired": {m: dict(c) for m, c in paired.items()},
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n[llmtrace] агрегаты записаны в {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
