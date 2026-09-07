#!/usr/bin/env python3
"""Матрица генераторов: что на самом деле двигает маркеры в машинном русском.

Зачем понадобилось. Прошлый прогон брал одну модель, один промпт и называл
результат «машинным русским». Так меряется манера одной ячейки. «Длинное тире
это признак ChatGPT» — ровно такое утверждение: оно родилось из английского
вывода одной модели и переехало в русский без проверки.

Идея. Человеческая половина фиксирована (одни и те же посты во всех ячейках,
пары сравниваются внутри записи), а варьируется по одной оси за раз:

  размер       gemma3 1b / 4b / 27b            — одна семья, одно поколение
  семейство    gemma3:4b / qwen3:4b / qwen3-vl:4b   — один размер
  дообучение   qwen3:4b против расцензуренного тюна того же базиса
  поколение    qwen2.5:7b против qwen3:4b
  промпт       один генератор, шесть запросов: три бытовых и три из статей
               жанра «промпты, чтобы ИИ писал как человек»

Ось промпта тут не для полноты. Во-первых, если профиль маркеров между промптами
одной модели гуляет сильнее, чем между моделями, то каталог откалиброван против
запроса, а не против «нейросети», и это надо знать про себя первым. Во-вторых,
антидетекторные промпты это прямой конкурент скилла, и вопрос «снижают ли они
измеренные маркеры» до сих пор никем не мерился, а ответ на него продаётся.

Фронтир-модели закрываются той же матрицей, когда появится ключ: ячейка описана
теми же тремя полями, источник генерации к схеме отношения не имеет.

Прогон резюмируемый: готовые ячейки пропускаются, так что 27B можно добирать
отдельным запуском. Корпус НЕ коммитится, в репозиторий едут только числа.

Запуск:
    python eval/matrix.py --list                    # что будет посчитано
    python eval/matrix.py --n 50                    # всё, что не готово
    python eval/matrix.py --only gemma3:4b          # одна модель, все промпты
    python eval/matrix.py --report                  # сводка по ячейкам
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "eval"))
sys.path.insert(0, str(ROOT / "skills" / "humanizer-ru" / "scripts"))

import remote_backend  # noqa: E402
from build_blog_pairs import human_half  # noqa: E402
from llm_backend import available, generate  # noqa: E402
from m4_calibration import DASHES, is_russian  # noqa: E402

from humanizer_metrics.markers import (  # noqa: E402
    effective_hard_bans,
    scan_hard_bans,
    scan_markers,
)

OUT = ROOT / "eval" / "out" / "matrix"

# Запросы, которыми пользователь реально приходит к чат-боту. P1-P3 бытовые,
# P4-P6 антидетекторные: их люди копируют из статей «промпты, чтобы ИИ писал как
# человек». Эти три тут не для полноты. Если «напиши как человек» не снижает наши
# измеренные маркеры, то весь жанр таких статей продаёт ощущение, а не результат,
# и сказать это мы имеем право только после замера.
#
# Тексты P4-P6 написаны нами по правилам, которые статьи перечисляют открытым
# списком (dtf.ru/id2164790, habr.com/companies/kemp_ai/articles/1039690,
# lynote.ai/blog/chatgpt-prompt-to-humanize-text). Чужие простыни на полторы
# тысячи знаков в репозиторий не копируем: нам нужен их состав правил, а не их
# текст. P5 исключение — там весь промпт это одно слово.
PROMPTS = {
    "P1-перепиши": "Перепиши этот текст, чтобы он читался лучше. Верни только текст.\n\n{text}",
    "P2-с-нуля": "Напиши пост для блога на эту тему. Верни только текст.\n\nТема: {topic}",
    "P3-профессионально": ("Отредактируй этот текст для блога, сделай его профессиональнее "
                           "и структурнее. Верни только текст.\n\n{text}"),
    # Свод правил, общий для русских статей жанра: роль, ритм, разговорность,
    # запрет на штампы, требование «нераспознаваемости».
    "P4-антидетектор": (
        "Ты опытный автор и редактор с двадцатилетним стажем. Перепиши текст так, "
        "чтобы его не распознали инструменты определения ИИ. Правила: неровный ритм, "
        "разная длина предложений и абзацев, разговорные обороты, субъективные "
        "наблюдения и живые примеры, естественная хаотичность вместо гладкости. "
        "Не используй обороты «в современном мире», «стоит отметить», «на сегодняшний "
        "день», «важно понимать», «не секрет, что», «революционный», «инновационный». "
        "Верни только текст.\n\n{text}"),
    # Самый копируемый минимальный вариант: одно слово и текст.
    "P5-humanize": "Humanize: {text}",
    # Пользователи копируют англоязычные промпты и суют в них русский текст.
    "P6-англ": (
        "Act as a careful writing editor. Rewrite the text below so it sounds natural, "
        "specific, and human. Preserve every fact. Vary sentence length, use active "
        "voice, avoid generic AI phrasing and em-dash overuse. Return only the text.\n\n"
        "{text}"),
}

# (модель, промпт, ось). Ось — только подпись для отчёта, на счёт не влияет.
CELLS = [
    ("gemma3:1b", "P1-перепиши", "размер"),
    ("gemma3:4b", "P1-перепиши", "размер/семейство/промпт"),
    ("gemma3:27b", "P1-перепиши", "размер"),
    ("qwen3:4b", "P1-перепиши", "семейство/дообучение"),
    ("qwen3-vl:4b", "P1-перепиши", "семейство"),
    ("svjack/Qwen3-4B-Instruct-2507-heretic:latest", "P1-перепиши", "дообучение"),
    ("qwen2.5:7b", "P1-перепиши", "поколение"),
    ("gpt-oss:20b", "P1-перепиши", "семейство"),
    ("qwen3-coder:30b", "P1-перепиши", "семейство"),
    ("gemma3:4b", "P2-с-нуля", "промпт"),
    ("gemma3:4b", "P3-профессионально", "промпт"),
    ("gemma3:4b", "P4-антидетектор", "промпт"),
    ("gemma3:4b", "P5-humanize", "промпт"),
    ("gemma3:4b", "P6-англ", "промпт"),
    # Тот же антидетекторный запрос на сильной модели: слабая может просто не
    # выполнить инструкцию, и тогда нулевой эффект скажет про неё, а не про приём.
    ("gemma3:27b", "P4-антидетектор", "промпт"),
    ("qwen3:4b", "P4-антидетектор", "промпт"),
]

# Удалённые ячейки: ось «поколение» до 2026 года и первые закрытые модели.
# Считаются только там, где в окружении есть ключ; остальные молча пропускаются,
# поэтому список можно держать длиннее, чем ключей на руках.
REMOTE_CELLS = [
    ("google|gemini-2.5-flash", "P1-перепиши", "поколение/закрытая"),
    ("google|gemini-2.5-flash", "P4-антидетектор", "промпт/закрытая"),
    ("groq|llama-3.3-70b-versatile", "P1-перепиши", "размер/семейство"),
    ("cerebras|llama-3.3-70b", "P1-перепиши", "провайдер"),
    ("mistral|mistral-large-latest", "P1-перепиши", "семейство"),
    ("github|gpt-4o", "P1-перепиши", "поколение/закрытая"),
    ("github|gpt-4o", "P4-антидетектор", "промпт/закрытая"),
    ("openrouter|deepseek/deepseek-chat", "P1-перепиши", "семейство/закрытая"),
]


def cell_path(model: str, prompt: str) -> Path:
    return OUT / f"{model.replace('/', '_').replace(':', '-')}__{prompt}.jsonl"


def run_cell(model: str, prompt: str, posts: list[dict], workers: int) -> int:
    path = cell_path(model, prompt)
    lock, done = threading.Lock(), {"n": 0}
    template = PROMPTS[prompt]

    def work(post: dict, fh) -> None:
        # Для генерации с нуля темой служит первое предложение поста: пара
        # перестаёт быть переписыванием, но тема у половин остаётся общей.
        topic = post["text"].split(".")[0][:200]
        text = template.format(text=post["text"], topic=topic)
        provider, name = remote_backend.parse_target(model)
        out = (remote_backend.generate(text, name, provider) if provider
               else generate(text, num_predict=1200, temperature=0.7,
                             model=name, timeout=900))
        if not out or not is_russian(out):
            return
        line = json.dumps({"human_text": post["text"], "machine_text": out.strip(),
                           "model": model, "prompt": prompt, "source": "pikabu",
                           "source_ID": post["id"]}, ensure_ascii=False)
        with lock:
            fh.write(line + "\n")
            fh.flush()
            done["n"] += 1

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            list(pool.map(lambda p: work(p, fh), posts))
    return done["n"]


def measure(text: str) -> dict:
    words = len(text.split())
    bans = {h.marker for h in effective_hard_bans(scan_hard_bans(text), words)}
    return {
        "words": words,
        "bans": bans,
        "marks_n": sum(h.count for h in scan_markers(text)),
        "cats": {h.category for h in scan_markers(text)},
        "dashes": {n: text.count(ch) for n, ch in DASHES.items()},
    }


def report(top: int) -> int:
    """Сводка: одна строка на ячейку плюс человеческая половина как база."""
    files = sorted(OUT.glob("*.jsonl")) if OUT.exists() else []
    if not files:
        print("[пусто] ячеек нет, сначала запустите без --report", file=sys.stderr)
        return 1

    human_seen: dict[str, dict] = {}
    rows, cat_by_cell = [], {}
    for path in files:
        recs = [json.loads(s) for s in path.read_text(encoding="utf-8").splitlines() if s]
        if not recs:
            continue
        ban_docs = em = en = 0
        dens, cats = [], defaultdict(int)
        for r in recs:
            human_seen.setdefault(r["source_ID"], measure(r["human_text"]))
            m = measure(r["machine_text"])
            if m["bans"]:
                ban_docs += 1
            em += bool(m["dashes"]["U+2014 em dash"])
            en += bool(m["dashes"]["U+2013 en dash"])
            dens.append(100.0 * m["marks_n"] / max(1, m["words"]))
            for c in m["cats"]:
                cats[c] += 1
        n = len(recs)
        cell = next((c for c in CELLS if cell_path(c[0], c[1]) == path), None)
        rows.append({"model": recs[0]["model"], "prompt": recs[0]["prompt"],
                     "axis": cell[2] if cell else "", "n": n,
                     "ban": 100.0 * ban_docs / n, "em": 100.0 * em / n,
                     "en": 100.0 * en / n, "dens": statistics.mean(dens)})
        cat_by_cell[(recs[0]["model"], recs[0]["prompt"])] = \
            sorted(((100.0 * v / n, k) for k, v in cats.items()), reverse=True)[:top]

    hs = list(human_seen.values())
    if hs:
        rows.append({"model": "ЧЕЛОВЕК", "prompt": "—", "axis": "база", "n": len(hs),
                     "ban": 100.0 * sum(1 for h in hs if h["bans"]) / len(hs),
                     "em": 100.0 * sum(1 for h in hs if h["dashes"]["U+2014 em dash"]) / len(hs),
                     "en": 100.0 * sum(1 for h in hs if h["dashes"]["U+2013 en dash"]) / len(hs),
                     "dens": statistics.mean(100.0 * h["marks_n"] / max(1, h["words"])
                                             for h in hs)})

    head = (f"{'модель':<34}{'промпт':<20}{'n':>5}{'бан%':>8}"
            f"{'тире—%':>9}{'тире–%':>9}{'марк/100':>10}")
    print(head)
    print("-" * len(head))
    for r in sorted(rows, key=lambda r: (r["model"] != "ЧЕЛОВЕК", r["model"], r["prompt"])):
        print(f"{r['model'][:33]:<34}{r['prompt']:<20}{r['n']:>5}{r['ban']:>8.1f}"
              f"{r['em']:>9.1f}{r['en']:>9.1f}{r['dens']:>10.2f}")

    print("\nразброс по осям (макс - мин доли документов с баном):")
    by_axis: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        if r["model"] == "ЧЕЛОВЕК":
            continue
        if r["prompt"] == "P1-перепиши":
            by_axis["модель (промпт P1)"].append(r["ban"])
        if r["model"] == "gemma3:4b":
            by_axis["промпт (модель gemma3:4b)"].append(r["ban"])
    for axis, vals in by_axis.items():
        if len(vals) > 1:
            print(f"  {axis:<28}{max(vals) - min(vals):>6.1f} п.п.  "
                  f"(от {min(vals):.1f} до {max(vals):.1f}, ячеек {len(vals)})")

    out = ROOT / "eval" / "out" / "matrix.json"
    out.write_text(json.dumps({"cells": rows,
                               "top_categories": {f"{m} | {p}": v
                                                  for (m, p), v in cat_by_cell.items()}},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[ok] -> {out.relative_to(ROOT)}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=50, help="постов на ячейку")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--only", help="считать только ячейки этой модели")
    ap.add_argument("--force", action="store_true", help="пересчитать готовые ячейки")
    ap.add_argument("--list", action="store_true", help="показать план и выйти")
    ap.add_argument("--report", action="store_true", help="сводка по посчитанным ячейкам")
    ap.add_argument("--top", type=int, default=5, help="категорий в сводке на ячейку")
    args = ap.parse_args()

    if args.report:
        return report(args.top)

    skipped = [c for c in REMOTE_CELLS
               if not remote_backend.available(remote_backend.parse_target(c[0])[0])]
    todo = [c for c in CELLS + REMOTE_CELLS if c not in skipped]
    todo = [c for c in todo if not args.only or c[0] == args.only]
    if not args.force:
        todo = [c for c in todo if not cell_path(c[0], c[1]).exists()]
    if args.list:
        for model, prompt, axis in todo:
            print(f"{model:<44}{prompt:<20}{axis}")
        print(f"ячеек к счёту: {len(todo)}")
        if skipped:
            need = sorted({remote_backend.parse_target(c[0])[0] for c in skipped})
            print(f"пропущено без ключа: {len(skipped)} (нужны: {', '.join(need)})")
        return 0
    if not todo:
        print("[инфо] все ячейки готовы, нечего считать")
        return 0
    if any(remote_backend.parse_target(c[0])[0] is None for c in todo) and not available():
        print("[ошибка] Ollama недоступна", file=sys.stderr)
        return 2
    if skipped:
        print(f"[инфо] без ключа пропущено удалённых ячеек: {len(skipped)}", file=sys.stderr)

    posts = human_half(args.n, 80, 350, refresh=False)[:args.n]
    print(f"[инфо] постов на ячейку: {len(posts)}, ячеек: {len(todo)}", file=sys.stderr)
    for i, (model, prompt, axis) in enumerate(todo, 1):
        print(f"[{i}/{len(todo)}] {model} | {prompt} | ось {axis}", file=sys.stderr)
        n = run_cell(model, prompt, posts, args.workers)
        print(f"    записано пар: {n}", file=sys.stderr)
    print("\n[ok] дальше: python eval/matrix.py --report")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
