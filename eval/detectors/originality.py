"""Адаптер Originality.ai (https://originality.ai).

Ключ из переменной окружения ORIGINALITY_API_KEY. Без ключа или без пакета
requests детектор недоступен, score() -> None. Ошибки сети/HTTP гасятся в None.
requests — опциональная зависимость (eval/requirements-eval.txt).
"""

from __future__ import annotations

import os

from .base import Detector

try:
    import requests  # type: ignore
except ImportError:  # pragma: no cover
    requests = None  # type: ignore

API_URL = "https://api.originality.ai/api/v1/scan/ai"
TIMEOUT_S = 30


class OriginalityDetector(Detector):
    name = "originality"

    def __init__(self) -> None:
        self._key = os.environ.get("ORIGINALITY_API_KEY", "").strip()

    @property
    def available(self) -> bool:
        return bool(self._key) and requests is not None

    def score(self, text: str) -> float | None:
        if not self.available:
            return None
        try:
            resp = requests.post(
                API_URL,
                headers={"X-OAI-API-KEY": self._key, "Content-Type": "application/json"},
                json={"content": text},
                timeout=TIMEOUT_S,
            )
            resp.raise_for_status()
            data = resp.json()
            # Originality отдаёт score.ai в диапазоне 0..1 — вероятность AI.
            score = (data.get("score") or {}).get("ai")
            if score is None:
                return None
            return float(score)
        except Exception:
            return None
