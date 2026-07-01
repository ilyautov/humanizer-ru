"""Score чистоты: сворачивает детерминированные сигналы в одно число 0-100.

Выше = текст читается живее/человечнее. Это НЕ детектор и НЕ вероятность ИИ:
просто агрегат уже считаемых метрик (хард-баны, маркеры, ритм, морфология),
поданный как обратная связь «было/стало». Опирается на пороги, которые уже
откалиброваны в burstiness/morphology и задокументированы в eval/RESULTS.md.

Пороги штрафов подобраны на eval/corpus (human → высокий score, raw-AI →
низкий, humanized → между). Калибровочный прогон: см. eval/run_eval.py.
"""

from __future__ import annotations

from dataclasses import dataclass

from .burstiness import CV_HUMAN_TARGET
from .markers import effective_hard_bans
from .morphology import NV_TARGET
from .structure import (
    LISTICLE_MIN_ITEMS,
    LISTICLE_SHARE_AI,
    PARA_CV_AI,
    PARA_MIN_COUNT,
)

# Тире — отдельный случай: оно и хард-бан, и штатная русская пунктуация
# (Википедия, диапазоны, «это —»). Поэтому в score не рубим потолком, а
# штрафуем по плотности с допуском. Имя берём из HARD_BANS markers.py.
EM_DASH_NAME = "Длинное тире"
COPY_PASTE_CATEGORY = "Артефакты копипасты"

# Полосы. Совпадают с порогами вмешательства из SKILL.md.
BAND_CLEAN = 85   # ≥ — следы ИИ не мешают, не править
BAND_EDIT = 60    # ≥ — точечная правка; < — полный рерайт


@dataclass
class ScoreResult:
    score: int                       # 0-100, выше = чище
    band: str                        # "чисто" | "правка" | "рерайт"
    penalties: list[tuple[str, int]]  # (причина, -очки) — это и есть verbose-отчёт

    def as_dict(self) -> dict:
        return {
            "score": self.score,
            "band": self.band,
            "penalties": [{"reason": r, "points": p} for r, p in self.penalties],
        }


def _band(score: float) -> str:
    if score >= BAND_CLEAN:
        return "чисто"
    if score >= BAND_EDIT:
        return "правка"
    return "рерайт"


def _per100(count: int, words: int) -> float:
    return (count / words * 100) if words else 0.0


def cleanliness_score(report) -> ScoreResult:
    """Считает score 0-100 из готового Report (см. humanizer_metrics.analyze)."""
    words = report.rhythm.words or 1
    penalties: list[tuple[str, int]] = []
    score = 100.0

    # 1. Фразовые хард-баны (кроме тире). Однозначные AI-обороты: дорого.
    #    Частотные баны («Является») штрафуются только выше порога плотности.
    eff_bans = effective_hard_bans(report.hard_bans, report.rhythm.words)
    hard_phrase = sum(h.count for h in eff_bans if h.marker != EM_DASH_NAME)
    if hard_phrase:
        pen = min(45, 12 * hard_phrase)
        score -= pen
        penalties.append((f"хард-баны (фразы): {hard_phrase}", -pen))

    # 2. Артефакты копипасты из чат-бота: текст буквально вставлен из ответа ИИ.
    copy_paste = sum(h.count for h in report.markers if h.category == COPY_PASTE_CATEGORY)
    if copy_paste:
        pen = 60
        score -= pen
        penalties.append((f"артефакты копипасты: {copy_paste}", -pen))

    # 3. Мягкие маркеры (кроме копипасты) по плотности на 100 слов.
    soft = sum(h.count for h in report.markers if h.category != COPY_PASTE_CATEGORY)
    if soft:
        pen = min(30, round(2 * _per100(soft, words)))
        if pen:
            score -= pen
            penalties.append((f"маркеры: {soft} ({_per100(soft, words):.1f}/100 слов)", -pen))

    # 4. Длинное тире по плотности с допуском ~2 на 100 слов: «—» штатно
    #    используется в русском (Википедия, «это —», диапазоны). Слабый сигнал.
    dash_density = _per100(report.rhythm.em_dash, words)
    if dash_density > 2.0:
        pen = min(8, round(3 * (dash_density - 2.0)))
        if pen:
            score -= pen
            penalties.append((f"тире: {report.rhythm.em_dash} ({dash_density:.1f}/100 слов)", -pen))

    # 5. Ровный ритм: чем ниже CV относительно цели 0.45, тем больше штраф.
    cv = report.rhythm.cv_len
    if report.rhythm.sentences >= 4 and cv < CV_HUMAN_TARGET:
        pen = min(20, round((CV_HUMAN_TARGET - cv) / CV_HUMAN_TARGET * 30))
        if pen:
            score -= pen
            penalties.append((f"ровный ритм (CV={cv}, цель ≥{CV_HUMAN_TARGET})", -pen))

    # 6. Номинальность: сущ./глаг. выше цели 2.5 = канцелярит. Слабый сигнал и
    #    главный источник ложных срабатываний (энциклопедический/юр. регистр
    #    легитимно номинален), поэтому штраф мягкий и низко ограничен.
    nv = report.morph.noun_verb_ratio
    if nv > NV_TARGET:
        pen = min(8, round((nv - NV_TARGET) / 0.5 * 3))
        if pen:
            score -= pen
            penalties.append((f"номинальность (сущ./глаг.={nv}, цель ≤{NV_TARGET})", -pen))

    # 7. Document-level: ровные по длине абзацы (burstiness абзацев). Срабатывает
    #    только на достаточно многоабзацном тексте, иначе инертно (короткая проза).
    st = report.structure
    if st.paragraphs >= PARA_MIN_COUNT and st.para_cv < PARA_CV_AI:
        pen = min(10, round((PARA_CV_AI - st.para_cv) / PARA_CV_AI * 20))
        if pen:
            score -= pen
            penalties.append((f"ровные абзацы (CV={st.para_cv}, цель ≥{PARA_CV_AI})", -pen))

    # 8. Document-level: listicle-сигнатура (засилье однотипных пунктов). Инертно
    #    на прозе без списков, бьёт по шаблонным гайдам/постам.
    if st.list_items >= LISTICLE_MIN_ITEMS and st.listicle_share > LISTICLE_SHARE_AI:
        pen = min(12, round((st.listicle_share - LISTICLE_SHARE_AI) * 30))
        if pen:
            score -= pen
            penalties.append((f"листикл ({st.list_items} пунктов, {int(st.listicle_share*100)}% строк)", -pen))

    final = max(0, min(100, round(score)))
    return ScoreResult(score=final, band=_band(final), penalties=penalties)
