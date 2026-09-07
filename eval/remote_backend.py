#!/usr/bin/env python3
"""Удалённые генераторы для матрицы: бесплатные тарифы поверх одного протокола.

Зачем. Локальная Ollama закрывает четыре оси матрицы (размер, семейство,
поколение, дообучение), но все они внутри открытых весов 2024-2025 годов. Вопрос
«как пишет по-русски модель, которой человек реально пользуется» ей не
закрывается вовсе, а именно из общения со свежими закрытыми моделями родился
спор про длинное тире.

Почему это решается бесплатно. У Google AI Studio, Groq, Cerebras, Mistral,
GitHub Models и OpenRouter есть постоянные бесплатные тарифы без карты, и все
шестеро говорят на OpenAI-совместимом /chat/completions. Ячейке матрицы нужно
50 текстов примерно по 1200 токенов, то есть 60 тысяч токенов — это на порядок
меньше любого дневного лимита.

Чего тут сознательно нет: GigaChat и YandexGPT. Обе русские, обе для нас
интересны больше прочих, и обе ходят по своему протоколу с обменом секрета на
временный токен. Это отдельная работа, и делать её вслепую, не имея ключа на
руках, смысла нет.

Ключи берутся только из окружения и в репозиторий не попадают. Бесплатный тариф
почти везде оплачивается тем, что запросы уходят в обучение, поэтому гонять
через него можно ровно то, что и так лежит в открытом доступе: посты из дампа.

Настройка:
    export OPENROUTER_API_KEY=...      # openrouter, самый широкий каталог
    export GEMINI_API_KEY=...          # google, свежая закрытая модель
    export GROQ_API_KEY=...            # groq
    export CEREBRAS_API_KEY=...        # cerebras
    export MISTRAL_API_KEY=...         # mistral
    export GITHUB_TOKEN=...            # github, даёт доступ к моделям OpenAI

    python eval/remote_backend.py      # показать, какие провайдеры доступны
"""

from __future__ import annotations

import os
import sys
import threading
import time

try:
    import requests  # type: ignore
except ImportError:  # pragma: no cover — окружение без requests
    requests = None  # type: ignore

# провайдер -> (база OpenAI-совместимого API, переменная с ключом, запросов в минуту)
PROVIDERS: dict[str, tuple[str, str, int]] = {
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY", 20),
    "google": ("https://generativelanguage.googleapis.com/v1beta/openai", "GEMINI_API_KEY", 10),
    "groq": ("https://api.groq.com/openai/v1", "GROQ_API_KEY", 25),
    "cerebras": ("https://api.cerebras.ai/v1", "CEREBRAS_API_KEY", 25),
    "mistral": ("https://api.mistral.ai/v1", "MISTRAL_API_KEY", 25),
    "github": ("https://models.inference.ai.azure.com", "GITHUB_TOKEN", 10),
}

_TIMEOUT_S = 180
# Бесплатные тарифы режут по запросам в минуту, и 429 приходит молча. Держим
# минимальный интервал на провайдера: матрица ходит из четырёх потоков.
_gate: dict[str, tuple[threading.Lock, list[float]]] = {
    name: (threading.Lock(), [0.0]) for name in PROVIDERS
}


def parse_target(target: str) -> tuple[str | None, str]:
    """«groq|llama-3.3-70b» -> ('groq', 'llama-3.3-70b'); без префикса — Ollama."""
    if "|" in target:
        provider, model = target.split("|", 1)
        return provider, model
    return None, target


def key_for(provider: str) -> str | None:
    entry = PROVIDERS.get(provider)
    return os.environ.get(entry[1]) if entry else None


def available(provider: str) -> bool:
    return requests is not None and bool(key_for(provider))


def _wait_turn(provider: str) -> None:
    lock, last = _gate[provider]
    interval = 60.0 / PROVIDERS[provider][2]
    with lock:
        delay = last[0] + interval - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        last[0] = time.monotonic()


def generate(prompt: str, model: str, provider: str, num_predict: int = 1200,
             temperature: float = 0.7, retries: int = 3) -> str | None:
    """Один ответ модели. None при отсутствии ключа, отказе или исчерпании лимита."""
    if not available(provider):
        return None
    base, env, _ = PROVIDERS[provider]
    for attempt in range(retries):
        _wait_turn(provider)
        try:
            resp = requests.post(
                f"{base}/chat/completions",
                headers={"Authorization": f"Bearer {os.environ[env]}",
                         "Content-Type": "application/json"},
                json={"model": model,
                      "messages": [{"role": "user", "content": prompt}],
                      "max_tokens": num_predict, "temperature": temperature},
                timeout=_TIMEOUT_S,
            )
            if resp.status_code == 429:
                # Экспоненциальная пауза: на бесплатном тарифе 429 это норма,
                # а не ошибка, и падать из-за него всей ячейкой незачем.
                time.sleep(5 * 2 ** attempt)
                continue
            resp.raise_for_status()
            return (resp.json()["choices"][0]["message"]["content"] or "").strip()
        except Exception as exc:  # noqa: BLE001 — ячейка не должна ронять прогон
            if attempt == retries - 1:
                print(f"[{provider}/{model}] {type(exc).__name__}: {exc}", file=sys.stderr)
            time.sleep(2 * 2 ** attempt)
    return None


def main() -> int:
    print(f"{'провайдер':<14}{'ключ':<10}{'RPM':>5}  база")
    for name, (base, env, rpm) in PROVIDERS.items():
        print(f"{name:<14}{'есть' if key_for(name) else 'нет':<10}{rpm:>5}  {base}")
    live = [n for n in PROVIDERS if available(n)]
    print(f"\nдоступно провайдеров: {len(live)}" + (f" ({', '.join(live)})" if live else ""))
    if not live:
        print("подсказка: ключи бесплатных тарифов кладутся в окружение, см. docstring")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
