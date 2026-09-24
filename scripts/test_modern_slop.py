#!/usr/bin/env python3
"""Гейт: сканер видит текст свежих моделей и не цепляет людей.

Зачем. Месяцами в гейтах стоял только карикатурный eval/corpus/raw (8-14
хард-банов на 100 слов). Такой текст ловится всегда, поэтому любая правка
каталога проходила зелёной, даже когда сканер ставил «чисто» посту Claude
Haiku. Здесь фикстура eval/corpus/modern: 30 ответов Haiku, Sonnet, GPT-5.6,
Gemma3 и Qwen2.5 на обычные задания пользователя (см. ATTRIBUTION.md). Если
сканер снова перестанет их видеть, гейт упадёт.

Пороги стоят ниже текущих значений с запасом, чтобы честная правка весов не
валила сборку, а откат к прежнему «слепому» состоянию валил. Замеры на этой
фикстуре (счёт строгий, без --genre, как у пользователя по умолчанию):

                          сканер до 8d34e3e    сейчас    порог
  доля не «чисто»         33% (10 из 30)       73% (22)  ≥ 60% (18 из 30)
  медиана score           91,5                 73        ≤ 80
  текстов с «Почерком»    0                    15        ≥ 10
  текстов с «Обвязкой»    0                    18        ≥ 12

Запас по доле 4 текста из 30: столько может уйти в «чисто» при подкрутке
весов у границы полосы 85. Прежний сканер не проходит ни по одному из
порогов. Контроль людей (Википедия, стилизация под Толстого) в своём жанре
обязан оставаться «чисто»: ловить слоп ценой живого текста нельзя.

Запуск:  python scripts/test_modern_slop.py
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "humanizer-ru" / "scripts"))

from humanizer_metrics import analyze, cleanliness_score  # noqa: E402
from humanizer_metrics.score import CHAT_WRAP_CATEGORY, SIGNATURE_CATEGORY  # noqa: E402

CORPUS = ROOT / "eval" / "corpus"
MIN_FLAGGED_SHARE = 0.60
MAX_MEDIAN_SCORE = 80
MIN_SIGNATURE_TEXTS = 10
MIN_CHAT_WRAP_TEXTS = 12
MIN_FIXTURE = 30
# Контроль ложных тревог: файл и жанры, в которых он обязан быть «чисто».
# Википедия проверяется в academic и news (как её читает eval и флаг --genre),
# литературная стилизация в fiction.
HUMAN_CONTROL = {
    "human/wiki_baikal.txt": ("academic", "news"),
    "human/wiki_chaikovsky.txt": ("academic", "news"),
    "human/wiki_programmirovanie.txt": ("academic", "news"),
    "literary/roshchin_pastiche.txt": ("fiction",),
}

failures: list[str] = []
passed = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global passed
    if ok:
        passed += 1
    else:
        failures.append(f"{name}{': ' + detail if detail else ''}")


# --- фикстура согласована с meta.json -------------------------------------
meta = json.loads((CORPUS / "meta.json").read_text(encoding="utf-8"))["modern_items"]
on_disk = {p.relative_to(CORPUS).as_posix() for p in (CORPUS / "modern").glob("*.txt")}
listed = {it["file"] for it in meta}
check("фикстура не меньше 30 текстов", len(meta) >= MIN_FIXTURE, str(len(meta)))
check("meta.json и файлы modern/ совпадают", on_disk == listed,
      f"без записи {sorted(on_disk - listed)}, без файла {sorted(listed - on_disk)}")
check("людей в фикстуре нет", not any(it["is_human"] for it in meta))
check("в фикстуре не меньше четырёх моделей",
      len({it["source_model"] for it in meta}) >= 4, str({it["source_model"] for it in meta}))

# --- сканер видит современный слоп ----------------------------------------
rows = []
for it in meta:
    path = CORPUS / it["file"]
    if not path.exists():
        continue
    rep = analyze(path.read_text(encoding="utf-8"))
    sc = cleanliness_score(rep)
    cats = {h.category for h in rep.markers}
    rows.append((it["id"], sc.score, sc.band, cats))

n = len(rows) or 1
flagged = [r for r in rows if r[2] != "чисто"]
share = len(flagged) / n
median = statistics.median(r[1] for r in rows) if rows else 100
missed = ", ".join(f"{i} {s}" for i, s, b, _ in rows if b == "чисто")
check(f"доля не «чисто» ≥ {MIN_FLAGGED_SHARE:.0%}", share >= MIN_FLAGGED_SHARE,
      f"{len(flagged)}/{n} = {share:.0%}; прошли «чисто»: {missed}")
check(f"медиана score ≤ {MAX_MEDIAN_SCORE}", median <= MAX_MEDIAN_SCORE, str(median))
sig = sum(SIGNATURE_CATEGORY in c for *_, c in rows)
wrap = sum(CHAT_WRAP_CATEGORY in c for *_, c in rows)
check(f"«{SIGNATURE_CATEGORY}» находится минимум в {MIN_SIGNATURE_TEXTS} текстах",
      sig >= MIN_SIGNATURE_TEXTS, str(sig))
check(f"«{CHAT_WRAP_CATEGORY}» находится минимум в {MIN_CHAT_WRAP_TEXTS} текстах",
      wrap >= MIN_CHAT_WRAP_TEXTS, str(wrap))

# --- люди остаются «чисто» в своём жанре ----------------------------------
for rel, genres in HUMAN_CONTROL.items():
    rep = analyze((CORPUS / rel).read_text(encoding="utf-8"))
    for genre in genres:
        sc = cleanliness_score(rep, genre)
        check(f"{rel} [{genre}] остаётся «чисто»", sc.band == "чисто",
              f"{sc.score} {sc.band}; {sc.penalties}")

print("=== test_modern_slop ===")
print(f"  фикстура: {len(rows)} текстов, не «чисто» {len(flagged)} ({share:.0%}), "
      f"медиана {median}; «{SIGNATURE_CATEGORY}» в {sig}, «{CHAT_WRAP_CATEGORY}» в {wrap}")
if failures:
    print(f"  прошло {passed}, упало {len(failures)}:")
    for f in failures:
        print("  ✗", f)
    raise SystemExit(1)
print(f"OK — {passed} проверок прошли.")
