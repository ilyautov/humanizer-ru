"""Реестр детекторов AI-текста.

Все детекторы локальные и опциональны: деградируют до available=False, если нет
пакета, модели или живого демона Ollama. available_detectors() инстанцирует все
известные адаптеры и возвращает только те, что реально могут работать сейчас.

ollama_ppl (perplexity по семплу) намеренно НЕ входит в дефолтный набор — он
дорогой и приближённый, включается отдельно через perplexity_detectors() (флаг
--perplexity в run_eval).
"""

from __future__ import annotations

from .base import Detector
from .ollama_llm import OllamaLLMDetector
from .ollama_ppl import OllamaPPLDetector
from .ru_roberta import RuRobertaDetector

__all__ = [
    "Detector",
    "OllamaLLMDetector",
    "OllamaPPLDetector",
    "RuRobertaDetector",
    "all_detectors",
    "available_detectors",
    "perplexity_detectors",
]


def all_detectors() -> list[Detector]:
    """Все «обычные» детекторы независимо от доступности (для диагностики).

    ollama_ppl сюда НЕ входит — он дорогой и подключается отдельным флагом.
    """
    return [
        RuRobertaDetector(),
        OllamaLLMDetector(),
    ]


def available_detectors() -> list[Detector]:
    """Только те детекторы, что реально доступны в текущем окружении.

    ollama_llm подхватывается автоматически, когда демон Ollama жив.
    """
    return [d for d in all_detectors() if d.available]


def perplexity_detectors() -> list[Detector]:
    """Дорогой приближённый perplexity-детектор (флаг --perplexity).

    Возвращает [OllamaPPLDetector], если он доступен (Ollama + razdel), иначе [].
    """
    ppl = OllamaPPLDetector()
    return [ppl] if ppl.available else []
