#!/usr/bin/env python3
"""Literary-guard: граница Брукса паттерна #53 на художественной прозе.

Паттерн #53 («Пустой образ, тест на обналичивание») велит переписывать образы
без референта — но ТОЛЬКО в утверждениях о механизме. Для художественного
текста, где образ и есть смысл, тест применять запрещено (граница в самом
паттерне). Эта граница семантическая: строковый детектор её не проверит
(см. test_score.py — он страхует только лексический слой на той же фикстуре).

Здесь LLM-слой: даём модели ровно текст паттерна #53 + художественную фикстуру
roshchin_pastiche.txt (стилизация под Толстого, см. corpus/ATTRIBUTION.md) и
спрашиваем, что она стала бы переписывать. Правильный ответ: ничего.

Известный пол (замер 2026-07-07, 4 итерации формулировок): gemma3:4b и
gemma3:27b стабильно хотят обналичить 1-4 самых ярких интроспективных образа
фикстуры, даже с регистром нулевым шагом правила и легитимизированным пустым
ответом. В проде скилл исполняет фронтир-модель с ПОЛНЫМ SKILL.md, где до #53
стоят классификация текста и ложные срабатывания: реальный кейс июня 2026 —
Claude отказался переписывать эту же фикстуру. Поэтому гейт по умолчанию
канарейка (предупреждение, exit 0), а не блокер.

Гейт (exit code):
  - Ollama недоступна / невалидный JSON       -> exit 0, graceful skip;
  - модель полезла «обналичивать» образы      -> предупреждение, exit 0;
                                                 с --strict -> exit 1.

Запуск:
    python eval/run_literary_guard.py            # канарейка
    python eval/run_literary_guard.py --strict   # протечка = провал
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
ROOT = EVAL_DIR.parent
SKILL_MD = ROOT / "skills" / "humanizer-ru" / "SKILL.md"
FIXTURE = EVAL_DIR / "corpus" / "literary" / "roshchin_pastiche.txt"
OUT = EVAL_DIR / "out" / "literary_guard.json"

if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))

import llm_backend  # noqa: E402

PROMPT_TEMPLATE = """\
Ты редактор, работающий по правилу #53 из руководства по AI-маркерам.
Вот правило дословно:

---
{pattern}
---

Вот текст (художественная проза, стилизация под русскую классику XIX века):

---
{fixture}
---

Следуя правилу #53 (включая шаг 0), реши, что в этом тексте подлежит
переписыванию. Если по правилу текст трогать не надо, верни пустой список и
вердикт "не_трогать": это полноценный ответ, а не отказ от работы. Цитируй
ТОЛЬКО фразы из текста выше, не примеры из правила. Верни СТРОГО JSON без
markdown-обёртки:
{{"rewrite_targets": [<цитаты образов, которые ты бы переписал по правилу>],
  "verdict": "<не_трогать | переписывать>",
  "reason": "<одно предложение почему>"}}
"""


def extract_pattern_53(skill_text: str) -> str | None:
    m = re.search(r"\*\*53\. .+?(?=\n\n)", skill_text, re.DOTALL)
    return m.group(0) if m else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--strict", action="store_true",
                    help="протечка границы = exit 1 (по умолчанию канарейка)")
    args = ap.parse_args()

    pattern = extract_pattern_53(SKILL_MD.read_text(encoding="utf-8"))
    if not pattern:
        print("[fail] паттерн #53 не найден в SKILL.md")
        return 1
    if not llm_backend.available():
        print("[skip] Ollama недоступна — literary-guard пропущен (см. docstring)")
        return 0

    fixture = FIXTURE.read_text(encoding="utf-8")
    prompt = PROMPT_TEMPLATE.format(pattern=pattern, fixture=fixture)
    parsed = llm_backend.generate_json(prompt, num_predict=512)
    if not parsed:
        print("[skip] модель не вернула валидный JSON — вердикта нет")
        return 0

    targets = parsed.get("rewrite_targets") or []
    if not isinstance(targets, list):
        targets = [str(targets)]
    # Галлюцинированные цели (цитата не из фикстуры, обычно примеры из самого
    # правила) — ошибка цитирования модели, не протечка границы. Отсекаем.
    targets = [t for t in targets
               if str(t).strip("«»\"' ") and str(t).strip("«»\"' ") in fixture]
    verdict = str(parsed.get("verdict", "")).strip().lower()
    ok = verdict.startswith("не") and len(targets) == 0

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(
            {"ok": ok, "verdict": verdict, "rewrite_targets": targets,
             "reason": parsed.get("reason", "")},
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )
    print(f"[ok] literary_guard.json -> {OUT}")
    if ok:
        print("[gate] ✓ граница #53 цела: художественные образы не тронуты")
        return 0
    print(f"[gate] ⚠ граница #53 протекла на локальной модели: "
          f"verdict={verdict!r}, целей {len(targets)}: {targets[:5]}")
    print("[gate] известный пол mid-tier моделей, см. docstring; "
          "в проде страхуют классификация текста и фронтир-исполнитель")
    return 1 if args.strict else 0


if __name__ == "__main__":
    sys.exit(main())
