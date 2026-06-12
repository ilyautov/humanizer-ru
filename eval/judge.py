"""LLM-судья: оценивает «человечность» русского текста.

Это семантический слой eval-харнеса — то, что детерминированные метрики поймать
не могут (кальки, ирония, translationese, живость голоса). Судья ставит оценку
0..100 «насколько это похоже на живой человеческий русский текст» и перечисляет
оставшиеся AI-паттерны.

Бэкенд по умолчанию — ЛОКАЛЬНАЯ Ollama (без облачных ключей). Если задан
ANTHROPIC_API_KEY и установлен пакет anthropic — можно использовать Anthropic
(опция). Ключ Anthropic БОЛЬШЕ НЕ ОБЯЗАТЕЛЕН.

Всё опционально: если ни Ollama, ни Anthropic недоступны, judge_text()
возвращает None (graceful skip), и оркестратор просто не показывает секцию судьи.

Env:
    OLLAMA_MODEL      — модель Ollama для судьи (по умолчанию gemma3:4b).
    JUDGE_BACKEND     — "ollama" | "anthropic" | "auto" (по умолчанию auto:
                        Anthropic, только если есть ключ И пакет; иначе Ollama).
    ANTHROPIC_API_KEY — ключ, ТОЛЬКО если хочешь Anthropic-бэкенд.
    JUDGE_MODEL       — модель Anthropic (по умолчанию claude-sonnet-4-6).
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

# llm_backend (локальная Ollama) — основной бэкенд судьи.
_EVAL_DIR = Path(__file__).resolve().parent
if str(_EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_EVAL_DIR))

import llm_backend  # noqa: E402

DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 1024

# anthropic опционален — нужен только если явно выбран этот бэкенд.
try:
    import anthropic  # type: ignore

    _ANTHROPIC_AVAILABLE = True
except ImportError:  # pragma: no cover — окружение без anthropic
    _ANTHROPIC_AVAILABLE = False


# Жёсткая рубрика. Просим строго JSON, чтобы парсинг был детерминированным.
RUBRIC = """\
Ты — строгий редактор русского языка и эксперт по выявлению AI-текста.
Оцени присланный текст по шкале 0..100: насколько он похож на ЖИВОЙ
ЧЕЛОВЕЧЕСКИЙ русский текст (100 = неотличим от написанного живым носителем,
0 = очевидная нейросетевая генерация с канцеляритом и штампами).

Критерии снижения оценки:
- канцелярит и отглагольные существительные («осуществление», «реализация»);
- штампы и кальки («является», «в современном мире», «стоит отметить»);
- ровный ритм (все предложения одной длины), отсутствие живых интонаций;
- длинные тире вместо естественной пунктуации;
- параллелизмы «не просто X, а Y», «не только X, но и Y»;
- мотивационные клише, раздувание, ложные диапазоны «от X до Y».

Верни СТРОГО JSON без markdown-обёртки, ровно такой структуры:
{"human_score": <int 0..100>, "remaining_patterns": [<строки>], "comment": "<кратко по-русски>"}
"""


@dataclass
class JudgeResult:
    human_score: int            # 0..100, выше = живее
    remaining_patterns: list[str]
    comment: str

    def as_dict(self) -> dict:
        return {
            "human_score": self.human_score,
            "remaining_patterns": self.remaining_patterns,
            "comment": self.comment,
        }


def _anthropic_ready() -> bool:
    return _ANTHROPIC_AVAILABLE and bool(
        os.environ.get("ANTHROPIC_API_KEY", "").strip()
    )


def judge_backend() -> str | None:
    """Какой бэкенд реально доступен: "anthropic", "ollama" или None.

    JUDGE_BACKEND форсирует выбор: "anthropic" / "ollama" / "auto" (по
    умолчанию). В auto Anthropic берётся только при наличии ключа И пакета,
    иначе — Ollama.
    """
    forced = os.environ.get("JUDGE_BACKEND", "auto").strip().lower()
    if forced == "anthropic":
        return "anthropic" if _anthropic_ready() else None
    if forced == "ollama":
        return "ollama" if llm_backend.available() else None
    # auto: предпочитаем Anthropic, если он явно настроен, иначе Ollama.
    if _anthropic_ready():
        return "anthropic"
    if llm_backend.available():
        return "ollama"
    return None


def judge_available() -> bool:
    """True, если судья реально может работать (Ollama ИЛИ Anthropic)."""
    return judge_backend() is not None


def _parse_json(raw: str) -> dict | None:
    """Достаёт JSON из ответа модели, даже если он завёрнут в текст/```json."""
    raw = raw.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if fence:
        raw = fence.group(1)
    else:
        brace = re.search(r"\{.*\}", raw, re.DOTALL)
        if brace:
            raw = brace.group(0)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _judge_anthropic(text: str, model: str | None) -> dict | None:
    model = model or os.environ.get("JUDGE_MODEL", DEFAULT_ANTHROPIC_MODEL)
    try:
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        resp = client.messages.create(
            model=model,
            max_tokens=MAX_TOKENS,
            system=RUBRIC,
            messages=[{"role": "user", "content": text}],
        )
        raw = "".join(
            block.text for block in resp.content
            if getattr(block, "type", "") == "text"
        )
    except Exception:
        return None
    return _parse_json(raw)


def _judge_ollama(text: str, model: str | None) -> dict | None:
    prompt = RUBRIC + "\n\nТекст для оценки:\n---\n" + text + "\n---"
    return llm_backend.generate_json(prompt, num_predict=512, model=model)


def judge_text(text: str, model: str | None = None) -> JudgeResult | None:
    """Оценивает текст судьёй. None, если судья недоступен или вызов упал.

    Бэкенд выбирается judge_backend() (Ollama по умолчанию, Anthropic — опция).
    """
    backend = judge_backend()
    if backend is None:
        return None

    if backend == "anthropic":
        parsed = _judge_anthropic(text, model)
    else:
        parsed = _judge_ollama(text, model)

    if not parsed:
        return None

    try:
        score = int(parsed.get("human_score", 0))
    except (TypeError, ValueError):
        score = 0
    score = max(0, min(100, score))
    patterns = parsed.get("remaining_patterns") or []
    if not isinstance(patterns, list):
        patterns = [str(patterns)]
    return JudgeResult(
        human_score=score,
        remaining_patterns=[str(p) for p in patterns],
        comment=str(parsed.get("comment", "")),
    )
