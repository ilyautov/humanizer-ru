"""Клиент локальной Ollama для оценочного слоя eval-харнеса humanizer-ru.

Весь LLM-слой оценки: детекторы, судья, faithfulness ходят сюда, а не в облако.
Никаких ключей Anthropic/OpenAI не нужно — работает против локального демона
Ollama (`ollama serve`). Если демон недоступен, всё деградирует в None/False:
наружу исключения не пробрасываются, метрики-режим run_eval не страдает.

Контракт Ollama (проверен вживую):
  GET  /api/tags                        — список моделей (проверка живости).
  POST /api/generate {model,prompt,...} — {"response": str, "logprobs": [...]}.
  POST /api/embed   {model,input}       — {"embeddings": [[float,...]]}.

Env:
  OLLAMA_HOST   — база API (по умолчанию http://localhost:11434).
  OLLAMA_MODEL  — чат-модель по умолчанию (gemma3:4b — знает русский,
                  не генерит reasoning-теги).
  OLLAMA_EMBED  — embedding-модель (nomic-embed-text, нужна для faithfulness).

Замечания по моделям:
  - gemma3:* отвечают чисто, без <think>.
  - qwen3:* оборачивают рассуждения в <think>...</think> — мы их вырезаем,
    чтобы парсинг JSON/числа не ломался.
Ollama серийная и небыстрая — таймауты ставим щедрые (120-180с).
"""

from __future__ import annotations

import json
import os
import re

# requests — опциональная зависимость (eval/requirements-eval.txt). Без неё
# весь Ollama-слой просто выключен, как и любой другой внешний инструмент.
try:
    import requests  # type: ignore
except ImportError:  # pragma: no cover — окружение без requests
    requests = None  # type: ignore


def host() -> str:
    """База Ollama API без хвостового слэша."""
    return os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")


def default_model() -> str:
    return os.environ.get("OLLAMA_MODEL", "gemma3:4b")


def default_embed_model() -> str:
    return os.environ.get("OLLAMA_EMBED", "nomic-embed-text")


# Таймауты: tags — быстрый ping; generate/embed — Ollama серийная и медленная.
_TAGS_TIMEOUT_S = 5
_GEN_TIMEOUT_S = 180
_EMBED_TIMEOUT_S = 120

# Вырезание reasoning-тегов вида <think>...</think> (qwen3 и подобные).
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def _strip_think(text: str) -> str:
    """Убирает reasoning-теги и схлопывает лишние пробелы по краям."""
    return _THINK_RE.sub("", text).strip()


def available() -> bool:
    """True, если демон Ollama отвечает на /api/tags (и есть requests)."""
    if requests is None:
        return False
    try:
        resp = requests.get(f"{host()}/api/tags", timeout=_TAGS_TIMEOUT_S)
        return resp.status_code == 200
    except Exception:
        return False


def list_models() -> list[str]:
    """Имена доступных моделей. Пустой список, если Ollama недоступна."""
    if requests is None:
        return []
    try:
        resp = requests.get(f"{host()}/api/tags", timeout=_TAGS_TIMEOUT_S)
        resp.raise_for_status()
        data = resp.json()
        return [m.get("name", "") for m in data.get("models", [])]
    except Exception:
        return []


def generate(
    prompt: str,
    num_predict: int = 512,
    temperature: float = 0.0,
    model: str | None = None,
) -> str | None:
    """Сгенерировать текст. None при недоступной Ollama или ошибке.

    temperature=0 по умолчанию — нам нужна детерминированная оценка, а не
    творчество. Reasoning-теги вырезаются из ответа.
    """
    if requests is None:
        return None
    model = model or default_model()
    try:
        resp = requests.post(
            f"{host()}/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {"num_predict": num_predict, "temperature": temperature},
            },
            timeout=_GEN_TIMEOUT_S,
        )
        resp.raise_for_status()
        data = resp.json()
        return _strip_think(data.get("response", "") or "")
    except Exception:
        return None


def _extract_json(raw: str) -> dict | None:
    """Достаёт первый JSON-объект из ответа модели.

    Снимает ```json-ограду, вырезает think-теги, ищет первую сбалансированную
    {...}. None, если валидный объект найти не удалось.
    """
    if not raw:
        return None
    raw = _strip_think(raw).strip()

    # Снимаем markdown-ограду ```json ... ```.
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if fence:
        raw = fence.group(1)

    # Прямой разбор — самый частый случай.
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass

    # Иначе ищем первую сбалансированную {...} вручную (модель могла дописать
    # текст до/после JSON).
    start = raw.find("{")
    while start != -1:
        depth = 0
        for i in range(start, len(raw)):
            ch = raw[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    chunk = raw[start : i + 1]
                    try:
                        obj = json.loads(chunk)
                        if isinstance(obj, dict):
                            return obj
                    except json.JSONDecodeError:
                        break  # этот блок битый — ищем следующую {
        start = raw.find("{", start + 1)
    return None


def generate_json(
    prompt: str,
    num_predict: int = 512,
    model: str | None = None,
) -> dict | None:
    """Сгенерировать и распарсить JSON-объект. None при неудаче.

    К промпту добавляется жёсткая инструкция «только валидный JSON»; ответ
    робастно парсится (```json-ограда, think-теги, первая {...}).
    """
    full = (
        prompt.rstrip()
        + "\n\nОтветь ТОЛЬКО валидным JSON-объектом без markdown-обёртки, "
        "пояснений и текста до или после."
    )
    raw = generate(full, num_predict=num_predict, temperature=0.0, model=model)
    if raw is None:
        return None
    return _extract_json(raw)


def embed(text: str, model: str | None = None) -> list[float] | None:
    """Вектор эмбеддинга текста через /api/embed. None при недоступности."""
    if requests is None:
        return None
    model = model or default_embed_model()
    try:
        resp = requests.post(
            f"{host()}/api/embed",
            json={"model": model, "input": text},
            timeout=_EMBED_TIMEOUT_S,
        )
        resp.raise_for_status()
        data = resp.json()
        embs = data.get("embeddings") or []
        if embs and isinstance(embs[0], list):
            return [float(x) for x in embs[0]]
        return None
    except Exception:
        return None


def generate_with_logprobs(
    prompt: str,
    num_predict: int = 1,
    top_logprobs: int = 20,
    temperature: float = 0.0,
    model: str | None = None,
) -> dict | None:
    """Сырой ответ /api/generate с logprobs для сгенерированных токенов.

    Используется perplexity-детектором (teacher-forcing). Возвращает весь JSON
    ответа (нужны поля response, logprobs, eval_count). None при ошибке.

    ВАЖНО: logprobs приходят только для СГЕНЕРИРОВАННЫХ токенов (их число равно
    eval_count), а не для токенов промпта.
    """
    if requests is None:
        return None
    model = model or default_model()
    try:
        resp = requests.post(
            f"{host()}/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {"num_predict": num_predict, "temperature": temperature},
                "logprobs": True,
                "top_logprobs": top_logprobs,
            },
            timeout=_GEN_TIMEOUT_S,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None
