"""ПРИБЛИЖЁННЫЙ perplexity-детектор через teacher-forcing на Ollama.

Идея: AI-текст обычно предсказуемее человеческого, поэтому у языковой модели
на нём ниже перплексия. Мы оцениваем перплексию teacher-forcing'ом:
  - идём по тексту по словам-токенам (razdel);
  - на каждой выбранной позиции шлём префикс (всё, что до токена), просим
    сгенерировать 1 токен с top_logprobs=K;
  - ищем фактический следующий токен среди top_logprobs, берём его logprob
    (если в топе нет — floor -15, т.е. «модель сильно удивлена»);
  - усредняем -(logprob) -> mean NLL -> perplexity = exp(mean NLL).

ДОРОГО: десятки HTTP-вызовов на текст (Ollama серийная). Поэтому:
  - семплируем максимум ~40 позиций на текст (равномерно по длине);
  - используем маленькую быструю модель (env OLLAMA_PPL_MODEL, по умолчанию
    gemma3:1b).
Это nice-to-have и ПРИБЛИЖЕНИЕ ПО СЕМПЛУ, а не честная перплексия по сабвордам:
токенизация razdel != токенизатор модели, top-K усечён. Поэтому детектор НЕ
включается в дефолтный --detectors, только по отдельному флагу --perplexity.

Env: OLLAMA_HOST, OLLAMA_PPL_MODEL (по умолчанию gemma3:1b).
"""

from __future__ import annotations

import math
import os
import sys
from pathlib import Path

from .base import Detector

_EVAL_DIR = Path(__file__).resolve().parent.parent
if str(_EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_EVAL_DIR))

import llm_backend  # noqa: E402

# razdel для разбиения на токены-слова. Опционален: без него детектор выключен.
try:
    from razdel import tokenize as _razdel_tokenize  # type: ignore

    _RAZDEL_AVAILABLE = True
except Exception:  # pragma: no cover
    _RAZDEL_AVAILABLE = False


def ppl_model() -> str:
    return os.environ.get("OLLAMA_PPL_MODEL", "gemma3:1b")


# Параметры семпла и нормализации.
MAX_POSITIONS = 40        # максимум позиций-вызовов на текст
TOP_LOGPROBS = 20         # сколько кандидатов запрашиваем
FLOOR_LOGPROB = -15.0     # штраф, если фактический токен не попал в top-K
MIN_TOKENS = 6            # короче — оценивать нечего

# Нормализация в «AI-вероятность» через mean NLL (= log perplexity), а не через
# сырую perplexity: exp() на наших приближённых NLL легко улетает в миллионы и
# схлопывает сигмоиду. Работаем в лог-домене — численно устойчиво.
# ai = sigmoid((NLL_CENTER - mean_nll) / NLL_SCALE): ниже NLL (предсказуемее,
# «AI-нее») => выше вероятность. Центр/масштаб эмпирические; токенизация razdel
# != сабворды модели, top-K усечён — это ПРИБЛИЖЕНИЕ, не честная perplexity.
NLL_CENTER = 6.0   # mean NLL ~6 (ppl ~400) => 0.5 на нашем семпле
NLL_SCALE = 2.5


def _tokens(text: str) -> list[str]:
    return [t.text for t in _razdel_tokenize(text)]


def _sample_indices(n: int) -> list[int]:
    """Индексы позиций (1..n-1) для оценки: равномерный семпл не более MAX."""
    positions = list(range(1, n))  # позиция 0 не имеет префикса
    if len(positions) <= MAX_POSITIONS:
        return positions
    step = len(positions) / MAX_POSITIONS
    return [positions[int(i * step)] for i in range(MAX_POSITIONS)]


class OllamaPPLDetector(Detector):
    name = "ollama_ppl"

    @property
    def available(self) -> bool:
        return _RAZDEL_AVAILABLE and llm_backend.available()

    def _mean_nll(self, text: str) -> float | None:
        """Средний negative log-likelihood по семплу позиций (= log perplexity).

        Это «сырьё» и для perplexity(), и для score(). None при недоступности
        или слишком коротком тексте.
        """
        if not self.available:
            return None
        toks = _tokens(text)
        if len(toks) < MIN_TOKENS:
            return None

        model = ppl_model()
        nlls: list[float] = []
        for idx in _sample_indices(len(toks)):
            prefix = " ".join(toks[:idx])  # префикс до целевого токена
            target = toks[idx]
            resp = llm_backend.generate_with_logprobs(
                prefix,
                num_predict=1,
                top_logprobs=TOP_LOGPROBS,
                temperature=0.0,
                model=model,
            )
            logprob = FLOOR_LOGPROB
            if resp:
                lps = resp.get("logprobs") or []
                if lps:
                    cands = lps[0].get("top_logprobs") or []
                    # Ищем фактический следующий токен среди кандидатов.
                    # Токенизатор модели (BPE-сабворды с ведущим пробелом) НЕ
                    # совпадает с razdel (целые слова), поэтому матчим мягко:
                    # точное совпадение, либо кандидат — непустой ПРЕФИКС
                    # целевого слова (типичный первый сабворд), без учёта
                    # ведущего пробела и регистра. Берём логпроб лучшего матча.
                    tgt = target.strip().lower()
                    for c in cands:
                        ctok = str(c.get("token", "")).strip().lower()
                        if not ctok:
                            continue
                        if ctok == tgt or tgt.startswith(ctok) or ctok.startswith(tgt):
                            logprob = float(c.get("logprob", FLOOR_LOGPROB))
                            break
            nlls.append(-logprob)

        if not nlls:
            return None
        return sum(nlls) / len(nlls)

    def perplexity(self, text: str) -> float | None:
        """Приближённая perplexity = exp(mean NLL). None при недоступности.

        Число может быть очень большим: razdel-токены не совпадают с сабвордами
        модели, многие позиции уходят в floor. Для нормализации score() работает
        в лог-домене (mean NLL), а не с этим сырым значением.
        """
        mean_nll = self._mean_nll(text)
        if mean_nll is None:
            return None
        return math.exp(min(mean_nll, 50.0))

    def score(self, text: str) -> float | None:
        """Нормализованная «AI-вероятность» 0..1 (ниже perplexity => выше).

        Нормализуем в лог-домене через mean NLL — устойчиво к раздутым exp.
        """
        mean_nll = self._mean_nll(text)
        if mean_nll is None:
            return None
        z = (NLL_CENTER - mean_nll) / NLL_SCALE
        z = max(-50.0, min(50.0, z))  # защита от переполнения exp
        ai = 1.0 / (1.0 + math.exp(-z))
        return max(0.0, min(1.0, ai))
