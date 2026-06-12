"""Адаптер GPTZero (https://gptzero.me).

Ключ берётся из переменной окружения GPTZERO_API_KEY. Если ключа нет или пакет
requests не установлен — детектор недоступен, score() возвращает None.
Сетевые/HTTP-ошибки тоже гасятся в None: eval не должен падать из-за внешнего
сервиса. requests — опциональная зависимость (eval/requirements-eval.txt).
"""

from __future__ import annotations

import os

from .base import Detector

# requests опционален: импортируем мягко, чтобы отсутствие пакета не ломало импорт.
try:
    import requests  # type: ignore
except ImportError:  # pragma: no cover — окружение без requests
    requests = None  # type: ignore

API_URL = "https://api.gptzero.me/v2/predict/text"
TIMEOUT_S = 30


class GPTZeroDetector(Detector):
    name = "gptzero"

    def __init__(self) -> None:
        self._key = os.environ.get("GPTZERO_API_KEY", "").strip()

    @property
    def available(self) -> bool:
        return bool(self._key) and requests is not None

    def score(self, text: str) -> float | None:
        if not self.available:
            return None
        try:
            resp = requests.post(
                API_URL,
                headers={"x-api-key": self._key, "Content-Type": "application/json"},
                json={"document": text},
                timeout=TIMEOUT_S,
            )
            resp.raise_for_status()
            data = resp.json()
            # У GPTZero вероятность «текст написан AI» лежит в
            # documents[0].class_probabilities.ai (или completely_generated_prob
            # в старых ответах). Берём максимально устойчиво.
            doc = (data.get("documents") or [{}])[0]
            probs = doc.get("class_probabilities") or {}
            if "ai" in probs:
                return float(probs["ai"])
            if "completely_generated_prob" in doc:
                return float(doc["completely_generated_prob"])
            return None
        except Exception:
            # Любая ошибка (сеть, лимит, формат) -> деградация в None.
            return None
