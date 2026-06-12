"""Защита смысла: не геймить метрики ценой содержания.

Очеловечивание не должно искажать факты ради красивых метрик. Этот модуль
сравнивает исходный (raw) и очеловеченный (humanized) текст по двум осям:

  - cosine: косинусная близость эмбеддингов (nomic-embed-text через Ollama);
    грубый сигнал «о том же ли это вообще».
  - meaning: LLM-проверка (Ollama) — сохранены ли факты, цифры, ключевые
    утверждения; оценка 0..100 + список потерянного/искажённого.

verdict сводит оба сигнала: cosine>=0.75 И meaning>=70 => "ок", иначе
"⚠ смысл пострадал".

Всё graceful: без Ollama/embed соответствующее поле = None, verdict учитывает
только то, что посчиталось. Никаких ключей наружу не нужно.

Env (см. llm_backend): OLLAMA_HOST, OLLAMA_MODEL, OLLAMA_EMBED.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

_EVAL_DIR = Path(__file__).resolve().parent
if str(_EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_EVAL_DIR))

import llm_backend  # noqa: E402

# Пороги вердикта.
COSINE_OK = 0.75
MEANING_OK = 70


def _cosine(a: list[float], b: list[float]) -> float | None:
    """Косинус двух векторов. None, если размерности не совпали или нулевые."""
    if not a or not b or len(a) != len(b):
        return None
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return None
    return dot / (na * nb)


def cosine_similarity(raw: str, humanized: str) -> float | None:
    """Косинус эмбеддингов raw/humanized через nomic-embed-text. None graceful."""
    ea = llm_backend.embed(raw)
    eb = llm_backend.embed(humanized)
    if ea is None or eb is None:
        return None
    cos = _cosine(ea, eb)
    return round(cos, 4) if cos is not None else None


_MEANING_PROMPT = """\
Ты — придирчивый редактор-факт-чекер. Тебе дан ИСХОДНЫЙ текст и его
ПЕРЕПИСАННАЯ (очеловеченная) версия. Задача переписывания — изменить стиль, НЕ
исказив смысл.

Проверь, сохранены ли в переписанной версии: факты, числа, имена, ключевые
утверждения и логика исходного текста. Оцени сохранность смысла от 0 до 100
(100 = всё сохранено точно, 0 = смысл искажён/потерян). Перечисли, что
потеряно или искажено (если ничего — пустой список).

ИСХОДНЫЙ текст:
---
{raw}
---

ПЕРЕПИСАННАЯ версия:
---
{humanized}
---

Верни JSON ровно такой структуры:
{{"meaning_score": <int 0..100>, "lost_or_distorted": [<строки>], "comment": "<кратко по-русски>"}}"""


def meaning_check(raw: str, humanized: str) -> dict | None:
    """LLM-проверка сохранности смысла. None, если Ollama недоступна/упала.

    Возвращает {"meaning_score": int, "lost_or_distorted": [str], "comment": str}.
    """
    if not llm_backend.available():
        return None
    parsed = llm_backend.generate_json(
        _MEANING_PROMPT.format(raw=raw, humanized=humanized), num_predict=512
    )
    if not parsed:
        return None
    try:
        score = int(parsed.get("meaning_score", 0))
    except (TypeError, ValueError):
        score = 0
    score = max(0, min(100, score))
    lost = parsed.get("lost_or_distorted") or []
    if not isinstance(lost, list):
        lost = [str(lost)]
    return {
        "meaning_score": score,
        "lost_or_distorted": [str(x) for x in lost],
        "comment": str(parsed.get("comment", "")),
    }


def faithfulness(raw: str, humanized: str) -> dict:
    """Полная проверка сохранности смысла пары raw/humanized.

    Возвращает dict:
      {"cosine": float|None, "meaning": dict|None, "verdict": str}

    verdict:
      - "ок" — cosine>=0.75 и meaning>=70 (или один из сигналов недоступен,
        но доступный в норме);
      - "⚠ смысл пострадал" — доступный сигнал ниже порога;
      - "— нет данных" — ни cosine, ни meaning посчитать не удалось.
    """
    cos = cosine_similarity(raw, humanized)
    meaning = meaning_check(raw, humanized)

    meaning_score = meaning["meaning_score"] if meaning else None

    cos_ok = cos is None or cos >= COSINE_OK
    meaning_ok = meaning_score is None or meaning_score >= MEANING_OK

    if cos is None and meaning_score is None:
        verdict = "— нет данных"
    elif cos_ok and meaning_ok:
        verdict = "ок"
    else:
        verdict = "⚠ смысл пострадал"

    return {"cosine": cos, "meaning": meaning, "verdict": verdict}


def faithfulness_available() -> bool:
    """True, если хоть один сигнал (embed или meaning) сможет посчитаться."""
    return llm_backend.available()
