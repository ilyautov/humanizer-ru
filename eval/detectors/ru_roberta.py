"""Локальный детектор AI-текста для русского на базе HuggingFace transformers.

Работает офлайн: грузит классификатор «human vs AI» через transformers + torch.
Это тяжёлые опциональные зависимости (eval/requirements-eval.txt) — в core их
нет, в CI они не ставятся. Если transformers/torch не установлены ИЛИ модель не
скачивается/не грузится — детектор недоступен, score() -> None.

Модель переопределяется через переменную окружения RU_DETECTOR_MODEL. По
умолчанию берём общедоступный детектор машинно-сгенерированного текста; ничего
не гарантируем по качеству — это лишь один сигнал из многих в отчёте.
"""

from __future__ import annotations

import os

from .base import Detector

DEFAULT_MODEL = os.environ.get(
    "RU_DETECTOR_MODEL",
    "RADAR-Vicuna-7B",  # плейсхолдер-имя; реально берётся из env при наличии
)

# transformers и torch опциональны. Любая проблема импорта -> детектор выключен.
try:
    import torch  # type: ignore  # noqa: F401
    from transformers import (  # type: ignore
        AutoModelForSequenceClassification,
        AutoTokenizer,
    )

    _HF_AVAILABLE = True
except Exception:  # pragma: no cover — окружение без torch/transformers
    _HF_AVAILABLE = False


class RuRobertaDetector(Detector):
    name = "ru_roberta"

    def __init__(self, model_name: str | None = None) -> None:
        self._model_name = model_name or DEFAULT_MODEL
        self._tokenizer = None
        self._model = None
        self._load_failed = False

    def _ensure_loaded(self) -> bool:
        """Ленивая загрузка модели. True, если модель готова к инференсу."""
        if not _HF_AVAILABLE or self._load_failed:
            return False
        if self._model is not None:
            return True
        try:
            self._tokenizer = AutoTokenizer.from_pretrained(self._model_name)
            self._model = AutoModelForSequenceClassification.from_pretrained(
                self._model_name
            )
            self._model.train(False)  # inference-режим
            return True
        except Exception:
            # Нет интернета, модель не существует, не хватает памяти и т.п.
            self._load_failed = True
            return False

    @property
    def available(self) -> bool:
        # Доступность проверяем только по наличию пакетов: реальную загрузку
        # модели откладываем до первого score(), чтобы не качать веса зря.
        return _HF_AVAILABLE and not self._load_failed

    def score(self, text: str) -> float | None:
        if not self.available or not self._ensure_loaded():
            return None
        try:
            inputs = self._tokenizer(
                text,
                return_tensors="pt",
                truncation=True,
                max_length=512,
            )
            with torch.no_grad():
                logits = self._model(**inputs).logits
            probs = torch.softmax(logits, dim=-1)[0]
            # Соглашение: индекс 1 — класс «AI/machine-generated». Если у модели
            # один логит, считаем его сигмоидой вероятности AI.
            if probs.shape[-1] >= 2:
                return float(probs[1].item())
            return float(torch.sigmoid(logits[0][0]).item())
        except Exception:
            return None
