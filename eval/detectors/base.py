"""Базовый контракт детектора AI-текста.

Детектор — это адаптер над локальной моделью (ru-roberta, Ollama). Все они
опциональны: если пакета или модели нет,
детектор сообщает available=False и score() возвращает None. Оркестратор
(run_eval.py) собирает только доступные детекторы через registry и спокойно
деградирует, если их нет вообще — метрики считаются всегда.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class Detector(ABC):
    """Абстрактный детектор. Возвращает вероятность того, что текст AI (0..1)."""

    #: короткое имя для отчёта (например "ru_roberta")
    name: str = "detector"

    @property
    @abstractmethod
    def available(self) -> bool:
        """True, если детектор реально может работать (есть ключ/пакет/модель)."""
        raise NotImplementedError

    @abstractmethod
    def score(self, text: str) -> float | None:
        """Вероятность AI-генерации 0..1. None, если детектор недоступен или упал."""
        raise NotImplementedError

    def __repr__(self) -> str:  # pragma: no cover — косметика
        state = "доступен" if self.available else "недоступен"
        return f"<Detector {self.name}: {state}>"
