#!/usr/bin/env python3
"""Ловит ли сканер современный слоп и не цепляет ли людей.

Вопрос, на который отвечает: какую ПОЛОСУ («чисто» / «правка» / «рерайт»)
пользователь увидит на тексте свежей модели и на живом тексте. Сырые счётчики
тут вторичны, человек читает вердикт.

Источники:
  слоп     eval/out/modern-slop*.jsonl (gen_modern_slop.py: обычные задания
           пользователя, Claude/Gemma/Qwen) и машинная часть LLMTrace от
           генераторов 2024-2025 (GPT-4o, GigaChat-Max, YandexGPT-5, ...)
  люди     человеческая часть LLMTrace, посты Пикабу (eval/out/pikabu-human.jsonl)

Числа печатаются и пишутся в eval/out/modern-slop-eval.json; сами тексты не
коммитятся.

    .venv/bin/python eval/modern_slop_eval.py
    .venv/bin/python eval/modern_slop_eval.py --misses 10   # показать пропуски
"""

from __future__ import annotations

import argparse
import json
import random
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "eval"))
sys.path.insert(0, str(ROOT / "skills" / "humanizer-ru" / "scripts"))

from humanizer_metrics import analyze, cleanliness_score  # noqa: E402

OUT = ROOT / "eval" / "out" / "modern-slop-eval.json"
# Генераторы LLMTrace, которые ещё в ходу; старьё (gpt-3.5, ruGPT, llama-7b) не берём.
LLMTRACE_MODERN = {
    "gpt-4o", "o3-2025-04-16", "GigaChat-Max", "yandex/YandexGPT-5-Lite-8B-instruct",
    "Qwen/Qwen2.5-72B-Instruct", "Qwen/QwQ-32B", "deepseek-ai/DeepSeek-R1-Distill-Qwen-32B",
    "unsloth/Llama-3.3-70B-Instruct", "google/gemma-2-27b-it",
}
MIN_WORDS, MAX_WORDS = 60, 600
PER_SOURCE = 300

# Обвязка ответа чата, которую пользователь при копировании не берёт.
PREAMBLE = re.compile(r"^\s*(?:вот|конечно|отлично|ниже)[^\n]{0,80}:\s*\n", re.I)
TAIL = re.compile(r"\n\s*(?:---+\s*\n)?\s*\*?(?:объём|объем|примерно|~)[^\n]*$", re.I)


def clean_chat(text: str) -> str:
    text = PREAMBLE.sub("", text, count=1)
    text = TAIL.sub("", text.rstrip())
    return re.sub(r"^\s*---+\s*$", "", text, flags=re.M).strip()


def load_slop() -> dict[str, list[str]]:
    groups: dict[str, list[str]] = defaultdict(list)
    for path in sorted((ROOT / "eval" / "out").glob("modern-slop*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            # Отложенная выборка (modern_slop_holdout.json) идёт отдельной строкой:
            # правила на её текстах не подбирались.
            prefix = "holdout:" if ".holdout." in path.name else "gen:"
            groups[prefix + row["model"]].append(clean_chat(row["text"]))
    return groups


def load_llmtrace() -> tuple[dict[str, list[str]], list[str]]:
    import llmtrace_calibration as lt
    from m4_calibration import is_russian

    ai: dict[str, list[str]] = defaultdict(list)
    human: list[str] = []
    for r in lt.load(None):
        if r.get("lang") != "ru" or r.get("data_type") == "poetry" or not is_russian(r["text"]):
            continue
        if r["label"] == "human":
            human.append(r["text"])
        elif r["model"] in LLMTRACE_MODERN:
            ai["llmtrace:" + r["model"].split("/")[-1]].append(r["text"])
    return ai, human


def fits(text: str) -> bool:
    return MIN_WORDS <= len(text.split()) <= MAX_WORDS


def sample(texts: list[str], n: int, rng: random.Random) -> list[str]:
    texts = [t for t in texts if fits(t)]
    return texts if len(texts) <= n else rng.sample(texts, n)


def verdicts(texts: list[str]) -> list[tuple[int, str, str]]:
    out = []
    for t in texts:
        s = cleanliness_score(analyze(t))
        out.append((s.score, s.band, t))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--misses", type=int, default=0, help="показать N слоп-текстов с полосой «чисто»")
    ap.add_argument("--no-llmtrace", action="store_true")
    args = ap.parse_args()
    rng = random.Random(42)

    slop = load_slop()
    human: dict[str, list[str]] = {}
    if not args.no_llmtrace:
        lt_ai, lt_human = load_llmtrace()
        slop.update(lt_ai)
        human["llmtrace:human"] = lt_human
    pik = ROOT / "eval" / "out" / "pikabu-human.jsonl"
    if pik.exists():
        human["pikabu"] = [json.loads(s)["text"] for s in pik.read_text(encoding="utf-8").splitlines() if s]

    table = {}
    misses = []
    print(f"{'источник':<42}{'n':>5}{'чисто':>8}{'правка':>8}{'рерайт':>8}{'медиана':>9}")
    for kind, groups in (("AI", slop), ("человек", human)):
        print(f"--- {kind}")
        for name, texts in sorted(groups.items()):
            vs = verdicts(sample(texts, PER_SOURCE, rng))
            if not vs:
                continue
            n = len(vs)
            share = {b: round(100 * sum(1 for _, band, _ in vs if band == b) / n, 1)
                     for b in ("чисто", "правка", "рерайт")}
            med = statistics.median(s for s, _, _ in vs)
            table[name] = {"kind": kind, "n": n, **share, "median": med}
            print(f"{name:<42}{n:>5}{share['чисто']:>7}%{share['правка']:>7}%{share['рерайт']:>7}%{med:>9}")
            if kind == "AI":
                misses += [(name, s, t) for s, band, t in vs if band == "чисто"]

    OUT.write_text(json.dumps(table, ensure_ascii=False, indent=2), encoding="utf-8")
    for name, s, t in rng.sample(misses, min(args.misses, len(misses))):
        print(f"\n=== {name} {s}\n{t[:900]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
