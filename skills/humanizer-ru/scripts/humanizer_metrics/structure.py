"""Структурные метрики уровня документа: burstiness абзацев и listicle-сигнатура.

Дополняет burstiness.py (там ритм ПРЕДЛОЖЕНИЙ) тем, что детекторы оценивают на
УРОВНЕ ДОКУМЕНТА: одинаковая длина абзацев и засилье однотипных списков выдают
шаблонную генерацию, даже когда каждое предложение по отдельности вычищено.

Эти сигналы целят в многосекционный/листикл-текст (посты, гайды). На прозе
одним блоком они инертны (мало абзацев, нет списков) и в score не вносят штраф,
поэтому не задевают калибровку основного корпуса.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass

from razdel import sentenize

# Строка-пункт списка: маркер «- * •» или «1. / 1)» в начале строки.
_LIST_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+\S")


@dataclass
class StructureStats:
    paragraphs: int          # число непустых абзацев (разделитель — пустая строка)
    para_mean_sent: float    # средняя длина абзаца в предложениях
    para_cv: float           # коэффициент вариации длин абзацев (burstiness абзацев)
    list_items: int          # строк-пунктов списка
    listicle_share: float    # доля строк-пунктов среди непустых строк

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def structure_stats(text: str) -> StructureStats:
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    sent_lens = [len(list(sentenize(p))) for p in paras]
    sent_lens = [n for n in sent_lens if n > 0]
    n = len(sent_lens)

    mean = statistics.mean(sent_lens) if sent_lens else 0.0
    stdev = statistics.pstdev(sent_lens) if n > 1 else 0.0
    cv = (stdev / mean) if mean else 0.0

    lines = [ln for ln in text.splitlines() if ln.strip()]
    list_items = sum(1 for ln in lines if _LIST_RE.match(ln))
    share = (list_items / len(lines)) if lines else 0.0

    return StructureStats(
        paragraphs=n,
        para_mean_sent=round(mean, 1),
        para_cv=round(cv, 3),
        list_items=list_items,
        listicle_share=round(share, 3),
    )


# Пороги (эвристика, согласована с логикой burstiness.py для предложений).
# Срабатывают только на достаточно длинном/структурированном тексте, чтобы не
# штрафовать короткую прозу одним-двумя абзацами.
PARA_CV_AI = 0.35          # ниже = слишком ровные по длине абзацы
PARA_MIN_COUNT = 6         # по нескольким коротким абзацам cv ненадёжен (малая
                           # выборка), судим о ритме абзацев только на длинном тексте
LISTICLE_SHARE_AI = 0.30   # доля строк-пунктов выше — текст «листиклом»
LISTICLE_MIN_ITEMS = 6     # и не меньше стольких пунктов (порог шаблонности)


def structure_verdict(s: StructureStats) -> str:
    parts = []
    if s.paragraphs >= PARA_MIN_COUNT and s.para_cv < PARA_CV_AI:
        parts.append(f"⚠ ровные абзацы (CV={s.para_cv}, цель ≥{PARA_CV_AI})")
    else:
        parts.append(f"✓ абзацы: {s.paragraphs}, CV={s.para_cv}")
    if s.list_items >= LISTICLE_MIN_ITEMS and s.listicle_share > LISTICLE_SHARE_AI:
        parts.append(f"⚠ листикл ({s.list_items} пунктов, {int(s.listicle_share*100)}% строк)")
    elif s.list_items:
        parts.append(f"пунктов списка: {s.list_items}")
    return "; ".join(parts)
