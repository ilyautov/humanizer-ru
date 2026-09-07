"""humanizer_metrics — детерминированные метрики живости текста.

Это грепабельная половина режима «Аудит» из SKILL.md: то, что считается
машиной, а не LLM. Используется и как локальный буст для Claude Code, и как
движок eval-харнеса (eval/run_eval.py), и как self-test самого скилла
(scripts/lint_skill.py).

Семантику (кальки, ирония, translationese, голос) тут не ловим — для этого
нужен сам скилл. Скрипты не работают в claude.ai web; скилл от них не зависит.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .burstiness import RhythmStats, rhythm, rhythm_verdict
from .markers import (
    MarkerHit,
    marker_verdict,
    scan_hard_bans,
    scan_markers,
)
from .morphology import MorphStats, morph_stats, morph_verdict
from .structure import StructureStats, structure_stats, structure_verdict
from .score import ScoreResult, cleanliness_score

__all__ = [
    "Report",
    "analyze",
    "RhythmStats",
    "MorphStats",
    "StructureStats",
    "MarkerHit",
    "ScoreResult",
    "cleanliness_score",
    "rhythm",
    "morph_stats",
    "structure_stats",
    "scan_hard_bans",
    "scan_markers",
]


@dataclass
class Report:
    hard_bans: list[MarkerHit]
    markers: list[MarkerHit]
    rhythm: RhythmStats
    morph: MorphStats
    structure: StructureStats

    @property
    def hard_ban_count(self) -> int:
        return sum(h.count for h in self.hard_bans)

    @property
    def marker_count(self) -> int:
        return sum(h.count for h in self.markers)

    def as_dict(self) -> dict:
        return {
            "hard_ban_count": self.hard_ban_count,
            "hard_bans": [(h.marker, h.count) for h in self.hard_bans],
            "marker_count": self.marker_count,
            "markers": [(h.category, h.marker, h.count) for h in self.markers],
            "rhythm": self.rhythm.as_dict(),
            "morph": self.morph.as_dict(),
            "structure": self.structure.as_dict(),
        }


# --- Код и цитаты не текст автора ------------------------------------------
# Сканер считал баны внутри блоков кода и внутри коротких цитат в ёлочках:
# статья про сам скилл с фразой «в современном мире» в кавычках получала
# «рерайт», а технический пост с примером кода терял баллы за чужой листинг.
# Код вырезается целиком (тройные и одиночные обратные кавычки). Цитата
# вырезается, только если она короткая: так цитируют слово или оборот. Длинная
# цитата в ёлочках это прямая речь или пересказ, её маркеры на совести автора,
# и в художественном тексте диалоги остаются под сканером.
#
# Замена сохраняет длину и переводы строк, чтобы номера строк в отчёте
# совпадали с файлом; заглушка не буква, поэтому фразовые регексы через неё
# не склеиваются («От «В современном мире…» до клише» не станет «От до»).
GAP = "·"
QUOTE_MAX_WORDS = 12
_FENCED = re.compile(r"(?s)```.*?```")
_INLINE_CODE = re.compile(r"`[^`\n]*`")
_QUOTE = re.compile(r"«[^«»]*»")


def _blank(match: re.Match[str]) -> str:
    return re.sub(r"[^\n]", GAP, match.group(0))


def _blank_short_quote(match: re.Match[str]) -> str:
    inner = match.group(0)[1:-1]
    if len(inner.split()) <= QUOTE_MAX_WORDS:
        return _blank(match)
    return match.group(0)


def mask_code_and_quotes(text: str) -> str:
    """Текст для лексического сканера: код и короткие цитаты заглушены,
    смещения и номера строк сохранены."""
    text = _FENCED.sub(_blank, text)
    text = _INLINE_CODE.sub(_blank, text)
    return _QUOTE.sub(_blank_short_quote, text)


def strip_code(text: str) -> str:
    """Текст для ритма и морфологии: код удалён, проза оставлена как есть."""
    text = _FENCED.sub("", text)
    return _INLINE_CODE.sub("", text)


def analyze(text: str) -> Report:
    """Полный детерминированный прогон текста."""
    lexical = mask_code_and_quotes(text)
    prose = strip_code(text)
    return Report(
        hard_bans=scan_hard_bans(lexical),
        markers=scan_markers(lexical),
        rhythm=rhythm(prose),
        morph=morph_stats(prose),
        structure=structure_stats(prose),
    )
