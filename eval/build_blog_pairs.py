#!/usr/bin/env python3
"""Сборка парного корпуса в целевом домене: живые посты и их переписывание LLM.

Зачем. Обе наши калибровки (AINL, M4) стоят на изданном и вычитанном тексте:
научные аннотации, национальный корпус, новости, оцифрованные дневники. А
умолчание сканера рассчитано на пост и лендинг, набранные руками. Там, где мы
меряли, длинное тире оказалось признаком человека, но в целевом домене его никто
не проверял: с телефона печатают дефис. Пока этот корпус не собран, спор про
главный бан не решается.

Что делает. Берёт человеческие посты из открытого дампа Пикабу (неформальный
русский, набранный руками) и просит локальные модели переписать каждый. На
выходе парный корпус в формате M4, который читает `m4_calibration.py --jsonl`.

Почему именно так. Пара «человек + его же текст глазами модели» повторяет
сценарий пользователя: он вставляет свой текст и просит переписать. И тема
внутри пары общая, поэтому сравнение не зависит от того, о чём пост.

Две модели, а не одна. В M4 было два генератора, и они разошлись по всем
метрикам вдвое. Одна модель меряет не «машинный русский», а свою манеру.

Человеческая половина кешируется в `eval/out/pikabu-human.jsonl`: она нужна и
сама по себе (перепись символов у человека не требует генерации вообще), и
чтобы повторный прогон не тянул дамп заново.

Корпус НЕ коммитится: у дампа нет файла лицензии, и чужие посты нам не
принадлежат. Пары пишутся в gitignored `eval/out/`, в репозиторий едут только
числа.

Запуск (модели локальные, ключей и сети наружу не нужно):
    python eval/build_blog_pairs.py --pairs 250 --models gemma3:27b,qwen2.5:7b
    python eval/build_blog_pairs.py --pairs 20 --models gemma3:4b   # проверка
    python eval/build_blog_pairs.py --human-only                    # только кеш
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import threading
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "eval"))

from llm_backend import available, default_model, generate  # noqa: E402
from m4_calibration import is_russian  # noqa: E402

DUMP = "https://huggingface.co/datasets/IlyaGusev/pikabu/resolve/main/00.jsonl.zst"
OUT = ROOT / "eval" / "out" / "blog-pairs.jsonl"
HUMAN_CACHE = ROOT / "eval" / "out" / "pikabu-human.jsonl"

# Промпт нарочно бытовой: так пишет пользователь, который пришёл к чат-боту.
# Никаких подсказок про маркеры, иначе мы измерим не модель, а свою инструкцию.
PROMPT = "Перепиши этот текст, чтобы он читался лучше. Верни только текст.\n\n{text}"


def fetch_posts(want: int, lo: int, hi: int) -> list[dict]:
    """Тянет начало дампа диапазонным запросом и распаковывает сколько успеет.

    Файл около гигабайта, целиком он не нужен: берём префикс потока, ловим
    обрыв распаковки и работаем с тем, что успело выйти.
    """
    import zstandard

    posts: list[dict] = []
    chunk = 8_000_000
    for attempt in range(1, 6):
        req = urllib.request.Request(DUMP, headers={"Range": f"bytes=0-{chunk * attempt}"})
        raw = urllib.request.urlopen(req).read()  # noqa: S310 (фиксированный https-адрес)
        buf = io.BytesIO()
        try:
            zstandard.ZstdDecompressor().copy_stream(io.BytesIO(raw), buf)
        except Exception:
            pass  # обрыв на границе куска — норма, дальше работаем с распакованным
        posts = []
        for line in buf.getvalue().decode("utf-8", "ignore").split("\n"):
            try:
                p = json.loads(line)
            except Exception:
                continue
            text = (p.get("text_markdown") or "").strip()
            words = len(text.split())
            if not (lo <= words <= hi) or not is_russian(text):
                continue
            # Ссылки и картинки в разметке ломают и сканер, и генерацию.
            if text.count("http") > 2 or text.count("![") > 0:
                continue
            posts.append({"id": p.get("id"), "text": text})
            if len(posts) >= want:
                return posts
        print(f"[инфо] префикс {chunk * attempt // 10**6} МБ дал {len(posts)} постов",
              file=sys.stderr)
    return posts


def human_half(want: int, lo: int, hi: int, refresh: bool) -> list[dict]:
    """Человеческая половина из кеша, иначе из дампа (и в кеш)."""
    if HUMAN_CACHE.exists() and not refresh:
        posts = [json.loads(s) for s in HUMAN_CACHE.read_text(encoding="utf-8").splitlines() if s]
        if len(posts) >= want:
            print(f"[инфо] кеш: {len(posts)} постов из {HUMAN_CACHE.name}", file=sys.stderr)
            return posts[:want]
    posts = fetch_posts(want, lo, hi)
    HUMAN_CACHE.parent.mkdir(parents=True, exist_ok=True)
    with HUMAN_CACHE.open("w", encoding="utf-8") as fh:
        for p in posts:
            fh.write(json.dumps(p, ensure_ascii=False) + "\n")
    return posts


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pairs", type=int, default=250, help="сколько постов взять на модель")
    ap.add_argument("--models", help="модели Ollama через запятую (по умолчанию OLLAMA_MODEL)")
    ap.add_argument("--workers", type=int, default=4,
                    help="параллельных запросов к Ollama; последовательно 27b даёт ~2 мин/пару")
    ap.add_argument("--human-only", action="store_true", help="только собрать кеш человека")
    ap.add_argument("--refresh", action="store_true", help="перекачать дамп мимо кеша")
    ap.add_argument("--min-words", type=int, default=80)
    ap.add_argument("--max-words", type=int, default=350)
    args = ap.parse_args()

    posts = human_half(args.pairs, args.min_words, args.max_words, args.refresh)
    print(f"[инфо] человеческих постов отобрано: {len(posts)}", file=sys.stderr)
    if args.human_only:
        print(f"[ok] человеческая половина -> {HUMAN_CACHE.relative_to(ROOT)}")
        return 0

    if not available():
        print("[ошибка] Ollama недоступна: нужна локальная модель для машинной половины",
              file=sys.stderr)
        return 2
    models = [m.strip() for m in (args.models or default_model()).split(",") if m.strip()]
    print(f"[инфо] модели: {', '.join(models)}, потоков {args.workers}", file=sys.stderr)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    lock, done = threading.Lock(), {"n": 0}

    def work(job: tuple[str, dict], fh) -> None:
        model, post = job
        # temperature=0.7: нам нужна типичная манера модели, а не её самый
        # вероятный ответ. На нуле текст выходит неестественно куцым.
        out = generate(PROMPT.format(text=post["text"]), num_predict=1200,
                       temperature=0.7, model=model, timeout=900)
        if not out or not is_russian(out):
            return
        line = json.dumps({
            "human_text": post["text"],
            "machine_text": out.strip(),
            "model": model,
            "source": "pikabu",
            "source_ID": post["id"],
        }, ensure_ascii=False)
        with lock:
            fh.write(line + "\n")
            fh.flush()  # прогон длинный, промежуточный результат должен читаться
            done["n"] += 1
            if done["n"] % 10 == 0:
                print(f"  …пар записано {done['n']}", file=sys.stderr)

    # Модели идут блоками, а не вперемешку: Ollama держит загруженной одну
    # модель, и чередование 17 ГБ с 4.7 ГБ означало бы перезагрузку весов на
    # каждом запросе.
    with OUT.open("w", encoding="utf-8") as fh:
        for model in models:
            print(f"[инфо] пошла модель {model}", file=sys.stderr)
            with ThreadPoolExecutor(max_workers=args.workers) as pool:
                list(pool.map(lambda p, m=model: work((m, p), fh), posts))

    print(f"\n[ok] пар: {done['n']} -> {OUT.relative_to(ROOT)}")
    print(f"     дальше: python eval/m4_calibration.py --jsonl {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
