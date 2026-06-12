"""Детектор AI-текста на локальной Ollama (без облачных ключей).

Просит локальную LLM оценить вероятность 0..1, что русский текст
машинно-сгенерирован, по чётким признакам нейросетевого стиля. В отличие от
облачных детекторов (GPTZero, Originality) не требует ключей и сети наружу —
только живой демон Ollama.

Доступность = llm_backend.available(). Любая ошибка вызова -> score() = None.

Env (см. llm_backend): OLLAMA_HOST, OLLAMA_MODEL (по умолчанию gemma3:4b).
"""

from __future__ import annotations

import sys
from pathlib import Path

from .base import Detector

# llm_backend лежит в eval/ (на уровень выше detectors/). Подмешиваем в путь,
# чтобы детектор работал и при импорте пакета detectors напрямую.
_EVAL_DIR = Path(__file__).resolve().parent.parent
if str(_EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_EVAL_DIR))

import llm_backend  # noqa: E402

# Рубрика признаков AI-текста на русском. Просим строго число + причину в JSON.
_PROMPT = """\
Ты — эксперт по выявлению машинно-сгенерированного русского текста.
Оцени вероятность от 0.0 до 1.0, что приведённый ниже текст написан нейросетью
(а не живым человеком).

Признаки, повышающие вероятность AI (0.0 = явно человек, 1.0 = явно нейросеть):
- высокая предсказуемость, низкая «перплексия» (текст течёт слишком гладко);
- ровный ритм: предложения примерно одной длины, нет всплесков (низкая burstiness);
- канцелярит и отглагольные существительные («осуществление», «реализация»);
- кальки и штампы («является», «в современном мире», «стоит отметить»);
- длинные тире вместо естественной пунктуации;
- равномерная плотность мысли, отсутствие живых интонаций и шероховатостей;
- параллелизмы «не просто X, а Y», раздувание, ложные диапазоны «от X до Y».

Текст:
---
{text}
---

Верни JSON ровно такой структуры:
{{"ai_probability": <число 0.0..1.0>, "reason": "<кратко по-русски>"}}"""


class OllamaLLMDetector(Detector):
    name = "ollama_llm"

    @property
    def available(self) -> bool:
        return llm_backend.available()

    def score(self, text: str) -> float | None:
        if not self.available:
            return None
        parsed = llm_backend.generate_json(
            _PROMPT.format(text=text), num_predict=256
        )
        if not parsed:
            return None
        val = parsed.get("ai_probability")
        if val is None:
            # Иногда модель кладёт число под другим ключом — пробуем мягко.
            for alt in ("ai_prob", "probability", "score", "ai"):
                if alt in parsed:
                    val = parsed[alt]
                    break
        try:
            prob = float(val)
        except (TypeError, ValueError):
            return None
        # Модель могла вернуть 0..100 вместо 0..1 — нормализуем.
        if prob > 1.0:
            prob = prob / 100.0
        return max(0.0, min(1.0, prob))
