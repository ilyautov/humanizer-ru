#!/usr/bin/env python3
"""Оркестратор eval-харнеса humanizer-ru.

Что делает:
  1. Грузит стратифицированный корпус (eval/corpus/meta.json).
  2. Для каждого текста считает детерминированные метрики (humanizer_metrics.analyze).
  3. Если задан --humanized DIR — считает метрики очеловеченной версии по тому же
     id и выводит дельты (hard_ban_count, marker_count, cv_len, noun_verb_ratio, em_dash).
  4. Если --detectors и есть доступные детекторы — прогоняет score() до/после.
  5. Если --judge и судья доступен — оценивает «человечность» до/после.
  6. Считает контроль переусердствования: на is_human текстах маркеров/банов
     должно быть МАЛО (скилл не должен хотеть их сильно править).
  7. Пишет eval/out/results.json и человекочитаемый eval/RESULTS.md.

Regression-гейт:
  --save-baseline   записать текущие метрики как эталон (eval/out/baseline.json).
  --baseline FILE   сравнить «после»-метрики с эталоном; exit 1, если просели
                    (больше HARD BANS / маркеров или ниже cv_len).

Без --detectors/--judge харнес полностью детерминирован, не требует ключей и
сети — этот режим гоняется в CI. Запуск:
    python eval/run_eval.py
    python eval/run_eval.py --humanized eval/humanized --detectors --judge
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Доступ к humanizer_metrics: пакет живёт внутри скилла (едет с установкой).
EVAL_DIR = Path(__file__).resolve().parent
ROOT = EVAL_DIR.parent
sys.path.insert(0, str(ROOT / "skills" / "humanizer-ru" / "scripts"))

from humanizer_metrics import Report, analyze  # noqa: E402

# Детекторы, судья, faithfulness, Ollama-бэкенд — локальные опциональные модули.
sys.path.insert(0, str(EVAL_DIR))
import llm_backend  # noqa: E402
from detectors import available_detectors, perplexity_detectors  # noqa: E402
from faithfulness import faithfulness, faithfulness_available  # noqa: E402
from judge import judge_available, judge_backend, judge_text  # noqa: E402

DEFAULT_CORPUS = EVAL_DIR / "corpus"
DEFAULT_OUT = EVAL_DIR / "out"

# Порог «переусердствования»: на живом человеческом тексте скилл не должен
# находить много маркеров. Считаем тревожным, если банов > 0 или маркеров > 5.
HUMAN_HARD_BAN_LIMIT = 0
HUMAN_MARKER_LIMIT = 5

# Порог, при котором детектор «обвиняет» текст в машинном происхождении.
# Если детектор ставит заведомо человеческому тексту score ≥ этого — ложное
# срабатывание (false positive).
DETECTOR_AI_THRESHOLD = 0.5


# --- модели данных отчёта -------------------------------------------------


@dataclass
class ItemResult:
    id: str
    type: str
    source_model: str
    is_human: bool
    before: dict                       # analyze().as_dict() для raw
    after: dict | None = None          # для humanized, если есть
    deltas: dict | None = None         # before -> after по ключевым метрикам
    detectors_before: dict = field(default_factory=dict)  # name -> score|None
    detectors_after: dict = field(default_factory=dict)
    judge_before: dict | None = None
    judge_after: dict | None = None
    faithfulness: dict | None = None  # cosine + meaning + verdict для пары raw/after

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "source_model": self.source_model,
            "is_human": self.is_human,
            "before": self.before,
            "after": self.after,
            "deltas": self.deltas,
            "detectors_before": self.detectors_before,
            "detectors_after": self.detectors_after,
            "judge_before": self.judge_before,
            "judge_after": self.judge_after,
            "faithfulness": self.faithfulness,
        }


# --- утилиты --------------------------------------------------------------


def _load_meta(corpus_dir: Path) -> list[dict]:
    meta_path = corpus_dir / "meta.json"
    data = json.loads(meta_path.read_text(encoding="utf-8"))
    return data["items"]


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _compute_deltas(before: dict, after: dict) -> dict:
    """Ключевые дельты after - before. Для банов/маркеров/тире нужно снижение
    (отрицательная дельта = хорошо), для cv_len рост (положительная = хорошо)."""
    b_rhythm, a_rhythm = before["rhythm"], after["rhythm"]
    b_morph, a_morph = before["morph"], after["morph"]
    return {
        "hard_ban_count": after["hard_ban_count"] - before["hard_ban_count"],
        "marker_count": after["marker_count"] - before["marker_count"],
        "em_dash": a_rhythm["em_dash"] - b_rhythm["em_dash"],
        "cv_len": round(a_rhythm["cv_len"] - b_rhythm["cv_len"], 3),
        "noun_verb_ratio": round(
            a_morph["noun_verb_ratio"] - b_morph["noun_verb_ratio"], 2
        ),
    }


def _run_detectors(detectors, text: str) -> dict:
    """name -> score(0..1)|None для каждого доступного детектора."""
    out = {}
    for d in detectors:
        out[d.name] = d.score(text)
    return out


def _verdict_for(rep_dict: dict) -> str:
    """Короткий вердикт по детерминированным метрикам одного текста."""
    bans = rep_dict["hard_ban_count"]
    markers = rep_dict["marker_count"]
    cv = rep_dict["rhythm"]["cv_len"]
    nv = rep_dict["morph"]["noun_verb_ratio"]
    if bans == 0 and markers <= 2 and cv >= 0.45 and nv <= 2.5:
        return "чисто"
    if bans > 0 or markers >= 6:
        return "AI"
    return "подозрительно"


# --- основной прогон ------------------------------------------------------


def evaluate(
    corpus_dir: Path,
    humanized_dir: Path | None,
    use_detectors: bool,
    use_judge: bool,
    use_perplexity: bool = False,
    use_faithfulness: bool = False,
) -> tuple[list[ItemResult], dict]:
    items = _load_meta(corpus_dir)
    detectors = available_detectors() if use_detectors else []
    # perplexity-детектор дорогой и приближённый — отдельным флагом.
    if use_perplexity:
        detectors = detectors + perplexity_detectors()
    judge_on = use_judge and judge_available()
    faith_on = use_faithfulness and faithfulness_available()

    results: list[ItemResult] = []
    for it in items:
        raw_path = corpus_dir / it["file"]
        raw_text = _read_text(raw_path)
        before = analyze(raw_text).as_dict()

        res = ItemResult(
            id=it["id"],
            type=it["type"],
            source_model=it["source_model"],
            is_human=it["is_human"],
            before=before,
        )

        # humanized-версия по тому же id (любое расширение .txt).
        if humanized_dir is not None:
            cand = humanized_dir / f"{it['id']}.txt"
            if cand.exists():
                after_text = _read_text(cand)
                res.after = analyze(after_text).as_dict()
                res.deltas = _compute_deltas(res.before, res.after)

        if detectors:
            res.detectors_before = _run_detectors(detectors, raw_text)
            if res.after is not None:
                after_text = _read_text(humanized_dir / f"{it['id']}.txt")
                res.detectors_after = _run_detectors(detectors, after_text)

        if judge_on:
            jb = judge_text(raw_text)
            res.judge_before = jb.as_dict() if jb else None
            if res.after is not None:
                after_text = _read_text(humanized_dir / f"{it['id']}.txt")
                ja = judge_text(after_text)
                res.judge_after = ja.as_dict() if ja else None

        # faithfulness считаем только для пар raw/humanized (нужны обе версии).
        if faith_on and res.after is not None:
            after_text = _read_text(humanized_dir / f"{it['id']}.txt")
            res.faithfulness = faithfulness(raw_text, after_text)

        results.append(res)

    env = {
        "detectors_available": [d.name for d in detectors],
        "detectors_requested": use_detectors,
        "perplexity_requested": use_perplexity,
        "judge_available": judge_on,
        "judge_requested": use_judge,
        "judge_backend": judge_backend() if judge_on else None,
        "faithfulness_available": faith_on,
        "faithfulness_requested": use_faithfulness,
        "has_humanized": humanized_dir is not None,
        # Какой моделью Ollama получены LLM-секции (для атрибуции в отчёте).
        "ollama_available": llm_backend.available(),
        "ollama_model": llm_backend.default_model(),
        "ollama_embed": llm_backend.default_embed_model(),
        "ollama_ppl_model": None,
    }
    if use_perplexity:
        # Имя perplexity-модели — из того же env, что использует детектор.
        import os as _os

        env["ollama_ppl_model"] = _os.environ.get("OLLAMA_PPL_MODEL", "gemma3:1b")
    return results, env


# --- генерация RESULTS.md -------------------------------------------------


def _fmt_score(v: float | None) -> str:
    return f"{v:.2f}" if isinstance(v, (int, float)) else "—"


def _fmt_delta(v: float | int, good_when_negative: bool = True) -> str:
    """Форматирует дельту со стрелкой направления качества."""
    if v == 0:
        return "0"
    sign = "+" if v > 0 else ""
    improved = (v < 0) if good_when_negative else (v > 0)
    arrow = "✓" if improved else "✗"
    return f"{sign}{v} {arrow}"


def render_markdown(results: list[ItemResult], env: dict) -> str:
    lines: list[str] = []
    lines.append("# Результаты eval-харнеса humanizer-ru\n")
    lines.append(
        "Автогенерируемый отчёт (`eval/run_eval.py`). Детерминированные метрики "
        "считаются всегда; реальные детекторы и LLM-судья — опционально (см. футер).\n"
    )

    ai_items = [r for r in results if not r.is_human]
    human_items = [r for r in results if r.is_human]
    has_after = any(r.after is not None for r in results)
    has_detectors = bool(env["detectors_available"])
    has_judge = env["judge_available"]

    # --- Сводка ---
    lines.append("## Сводка\n")
    avg_bans = (
        sum(r.before["hard_ban_count"] for r in ai_items) / len(ai_items)
        if ai_items else 0
    )
    avg_markers = (
        sum(r.before["marker_count"] for r in ai_items) / len(ai_items)
        if ai_items else 0
    )
    avg_cv = (
        sum(r.before["rhythm"]["cv_len"] for r in ai_items) / len(ai_items)
        if ai_items else 0
    )
    lines.append(f"- AI-текстов в корпусе: **{len(ai_items)}**, человеческих: **{len(human_items)}**")
    lines.append(f"- Среднее по AI-текстам (raw): HARD BANS **{avg_bans:.1f}**, "
                 f"маркеров **{avg_markers:.1f}**, CV ритма **{avg_cv:.3f}**")
    if has_after:
        improved = sum(
            1 for r in ai_items
            if r.deltas and r.deltas["hard_ban_count"] <= 0 and r.deltas["marker_count"] < 0
        )
        lines.append(f"- Очеловечено (humanized) версий: есть; снизили маркеры/баны "
                     f"в **{improved}/{len(ai_items)}** AI-текстов")
    else:
        lines.append("- Очеловеченных версий нет: показан только baseline (raw).")
    lines.append("")

    # --- Таблица по AI-текстам ---
    lines.append("## AI-тексты (вход скилла)\n")
    header = "| id | тип | модель | HARD BANS | маркеры | CV | сущ/глаг | тире | вердикт |"
    sep = "|---|---|---|---|---|---|---|---|---|"
    if has_after:
        header = ("| id | тип | модель | баны (до→Δ) | маркеры (до→Δ) | "
                  "CV (до→Δ) | сущ/глаг (до→Δ) | тире (до→Δ) | вердикт после |")
        sep = "|---|---|---|---|---|---|---|---|---|"
    lines.append(header)
    lines.append(sep)
    for r in ai_items:
        b = r.before
        if has_after and r.after is not None:
            a, d = r.after, r.deltas
            lines.append(
                f"| `{r.id}` | {r.type} | {r.source_model} "
                f"| {b['hard_ban_count']}→{_fmt_delta(d['hard_ban_count'])} "
                f"| {b['marker_count']}→{_fmt_delta(d['marker_count'])} "
                f"| {b['rhythm']['cv_len']}→{_fmt_delta(d['cv_len'], good_when_negative=False)} "
                f"| {b['morph']['noun_verb_ratio']}→{_fmt_delta(d['noun_verb_ratio'])} "
                f"| {b['rhythm']['em_dash']}→{_fmt_delta(d['em_dash'])} "
                f"| {_verdict_for(a)} |"
            )
        else:
            lines.append(
                f"| `{r.id}` | {r.type} | {r.source_model} "
                f"| {b['hard_ban_count']} | {b['marker_count']} "
                f"| {b['rhythm']['cv_len']} | {b['morph']['noun_verb_ratio']} "
                f"| {b['rhythm']['em_dash']} | {_verdict_for(b)} |"
            )
    lines.append("")

    # --- Детекторы ---
    if has_detectors:
        lines.append("## Реальные детекторы (вероятность AI, 0..1)\n")
        det_names = env["detectors_available"]
        if "ollama_llm" in det_names or "ollama_ppl" in det_names:
            note = f"Ollama-детекторы получены моделью `{env.get('ollama_model')}`"
            if "ollama_ppl" in det_names and env.get("ollama_ppl_model"):
                note += (f"; perplexity (`ollama_ppl`) — приближённо по семплу, "
                         f"модель `{env['ollama_ppl_model']}`")
            lines.append(note + ".\n")
        head = "| id | " + " | ".join(det_names) + " |"
        if has_after:
            head = "| id | " + " | ".join(f"{n} (до→после)" for n in det_names) + " |"
        lines.append(head)
        lines.append("|---|" + "|".join(["---"] * len(det_names)) + "|")
        for r in ai_items:
            cells = []
            for n in det_names:
                bsc = _fmt_score(r.detectors_before.get(n))
                if has_after:
                    asc = _fmt_score(r.detectors_after.get(n))
                    cells.append(f"{bsc}→{asc}")
                else:
                    cells.append(bsc)
            lines.append(f"| `{r.id}` | " + " | ".join(cells) + " |")
        lines.append("")

        # --- FP-аудит: те же детекторы на ЗАВЕДОМО человеческих текстах ---
        if human_items:
            det_names = env["detectors_available"]
            lines.append("## FP-аудит детекторов (заведомо человеческие тексты)\n")
            lines.append(
                "Те же детекторы прогнаны по контролю «человек» (дословные отрывки "
                "статей Википедии, CC BY-SA — заведомо не AI). Если детектор ставит "
                f"score ≥ {DETECTOR_AI_THRESHOLD:.2f}, он **ложно обвиняет человека** "
                "(false positive).\n"
            )
            head = "| id | источник | " + " | ".join(det_names) + " | вердикт |"
            lines.append(head)
            lines.append("|---|---|" + "|".join(["---"] * len(det_names)) + "|---|")
            fp_total = 0
            fp_possible = 0
            for r in human_items:
                cells = []
                flagged_here = False
                for n in det_names:
                    sc = r.detectors_before.get(n)
                    cells.append(_fmt_score(sc))
                    if isinstance(sc, (int, float)):
                        fp_possible += 1
                        if sc >= DETECTOR_AI_THRESHOLD:
                            fp_total += 1
                            flagged_here = True
                verdict = "⚠ помечен как AI" if flagged_here else "✓ распознан как человек"
                lines.append(
                    f"| `{r.id}` | {r.source_model} | " + " | ".join(cells)
                    + f" | {verdict} |"
                )
            lines.append("")
            if fp_possible:
                rate = 100.0 * fp_total / fp_possible
                lines.append(
                    f"**False positive rate: {fp_total}/{fp_possible} "
                    f"({rate:.0f}%)** оценок детекторов на человеческом тексте — "
                    "ложное обвинение в машинной генерации. Это эмпирическая "
                    "иллюстрация того, почему бинарная «человек/AI» классификация на "
                    "русском ненадёжна: формальный человеческий текст детектор "
                    "штатно принимает за нейросеть."
                )
            lines.append("")

    # --- Судья ---
    if has_judge:
        lines.append("## LLM-судья «человечность» (0..100, выше = живее)\n")
        jb_backend = env.get("judge_backend")
        if jb_backend == "ollama":
            lines.append(f"Получено локальной Ollama, модель `{env.get('ollama_model')}`.\n")
        elif jb_backend == "anthropic":
            lines.append("Получено через Anthropic API.\n")
        lines.append("| id | до | после | оставшиеся паттерны (после) |")
        lines.append("|---|---|---|---|")
        for r in ai_items:
            jb = r.judge_before["human_score"] if r.judge_before else "—"
            ja = r.judge_after["human_score"] if r.judge_after else "—"
            patt = ""
            if r.judge_after and r.judge_after.get("remaining_patterns"):
                patt = ", ".join(r.judge_after["remaining_patterns"][:4])
            lines.append(f"| `{r.id}` | {jb} | {ja} | {patt} |")
        lines.append("")

    # --- Faithfulness (защита смысла) ---
    has_faith = env.get("faithfulness_available") and any(
        r.faithfulness for r in ai_items
    )
    if has_faith:
        lines.append("## Faithfulness — защита смысла (raw → humanized)\n")
        lines.append(
            f"Косинус эмбеддингов (`{env.get('ollama_embed')}`) и LLM-проверка "
            f"сохранности фактов (`{env.get('ollama_model')}`). "
            f"Вердикт «ок», если cosine ≥ 0.75 и meaning ≥ 70.\n"
        )
        lines.append("| id | cosine | meaning (0-100) | вердикт | потеряно/искажено |")
        lines.append("|---|---|---|---|---|")
        for r in ai_items:
            f = r.faithfulness
            if not f:
                continue
            cos = _fmt_score(f.get("cosine"))
            meaning = f.get("meaning")
            mscore = meaning["meaning_score"] if meaning else "—"
            lost = ""
            if meaning and meaning.get("lost_or_distorted"):
                lost = "; ".join(meaning["lost_or_distorted"][:3])
            lines.append(
                f"| `{r.id}` | {cos} | {mscore} | {f.get('verdict', '—')} | {lost} |"
            )
        lines.append("")

    # --- Контроль переусердствования ---
    lines.append("## Контроль переусердствования (человеческие тексты)\n")
    lines.append(
        "Живой человеческий текст скилл НЕ должен хотеть сильно править. "
        f"Тревога, если HARD BANS > {HUMAN_HARD_BAN_LIMIT} или маркеров > {HUMAN_MARKER_LIMIT}.\n"
    )
    lines.append("| id | тип | HARD BANS | маркеры | CV | сущ/глаг | тире | статус |")
    lines.append("|---|---|---|---|---|---|---|---|")
    overzealous = 0
    for r in human_items:
        b = r.before
        bans = b["hard_ban_count"]
        markers = b["marker_count"]
        flagged = bans > HUMAN_HARD_BAN_LIMIT or markers > HUMAN_MARKER_LIMIT
        if flagged:
            overzealous += 1
        status = "⚠ ложная тревога" if flagged else "✓ ок"
        lines.append(
            f"| `{r.id}` | {r.type} | {bans} | {markers} "
            f"| {b['rhythm']['cv_len']} | {b['morph']['noun_verb_ratio']} "
            f"| {b['rhythm']['em_dash']} | {status} |"
        )
    lines.append("")
    if human_items:
        lines.append(
            f"Итог контроля: **{len(human_items) - overzealous}/{len(human_items)}** "
            f"человеческих текстов прошли чисто."
        )
        if overzealous:
            lines.append("")
            lines.append(
                "> **Как это читать.** Контроль — дословные отрывки статей "
                "Википедии (заведомо человеческий, но **формальный** регистр). "
                "Срабатывания здесь не баг, а та же ловушка, в которую попадают "
                "AI-детекторы (см. FP-аудит выше): формальный человеческий текст "
                "трудно отличить от машинного по поверхностным признакам. Конкретно "
                "тревогу дают (1) длинные тире «—» — Википедия использует их "
                "штатно, а скилл банит как маркер по строгой политике; (2) высокое "
                "сущ/глаг — это энциклопедический стиль, а не нейросеть. Вывод "
                "честный и в обе стороны: ни детектор, ни простые эвристики не "
                "выносят надёжный вердикт «человек/AI» на формальном тексте. Скилл "
                "поэтому и не детектирует, а **переписывает** — и нацелен на живой, "
                "а не на энциклопедический регистр."
            )
    lines.append("")

    # --- Футер о доступности ---
    lines.append("---\n")
    lines.append("### Доступность инструментов в этом прогоне\n")
    det = env["detectors_available"]
    ollama_state = "жива" if env.get("ollama_available") else "недоступна"
    lines.append(f"- Локальная Ollama: {ollama_state} "
                 f"(чат-модель `{env.get('ollama_model')}`, embed `{env.get('ollama_embed')}`)")
    lines.append(f"- Детекторы запрошены: {'да' if env['detectors_requested'] else 'нет'}; "
                 f"доступны: {', '.join(det) if det else '— (нет ключей/пакетов/Ollama)'}")
    if env.get("perplexity_requested"):
        ppl_on = "ollama_ppl" in det
        lines.append(f"  - perplexity (`--perplexity`): "
                     f"{'включён, модель `' + str(env.get('ollama_ppl_model')) + '` (приближённо по семплу)' if ppl_on else 'недоступен (нет Ollama/razdel)'}")
    jb_backend = env.get("judge_backend")
    jb_desc = {
        "ollama": f"Ollama (`{env.get('ollama_model')}`)",
        "anthropic": "Anthropic API",
    }.get(jb_backend, "— (нет Ollama и нет ANTHROPIC_API_KEY)")
    lines.append(f"- LLM-судья запрошен: {'да' if env['judge_requested'] else 'нет'}; "
                 f"бэкенд: {jb_desc}")
    if env.get("faithfulness_requested"):
        f_on = env.get("faithfulness_available")
        lines.append(f"- Faithfulness (`--faithfulness`): "
                     f"{'доступна (embed `' + str(env.get('ollama_embed')) + '` + meaning `' + str(env.get('ollama_model')) + '`)' if f_on else 'недоступна (нет Ollama)'}")
    lines.append(f"- Очеловеченные версии: {'есть' if env['has_humanized'] else 'нет (baseline-режим)'}")
    lines.append("\nДетерминированные метрики (HARD BANS, маркеры, CV ритма, сущ/глаг) "
                 "считаются всегда и не зависят от ключей, Ollama или сети. "
                 "LLM-слой (детекторы Ollama, судья, faithfulness) работает на ЛОКАЛЬНОЙ "
                 "Ollama — ключ Anthropic не требуется.")
    return "\n".join(lines) + "\n"


# --- regression-гейт ------------------------------------------------------


def _metric_snapshot(results: list[ItemResult]) -> dict:
    """Снимок ключевых «после»-метрик (или raw, если humanized нет) по id."""
    snap = {}
    for r in results:
        src = r.after if r.after is not None else r.before
        snap[r.id] = {
            "hard_ban_count": src["hard_ban_count"],
            "marker_count": src["marker_count"],
            "cv_len": src["rhythm"]["cv_len"],
        }
    return snap


def check_regression(results: list[ItemResult], baseline_path: Path) -> list[str]:
    """Сравнивает текущий снимок с эталоном. Возвращает список регрессий."""
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    current = _metric_snapshot(results)
    regressions: list[str] = []
    for item_id, base in baseline.items():
        cur = current.get(item_id)
        if cur is None:
            continue  # текст исчез из корпуса — это не регрессия метрик
        if cur["hard_ban_count"] > base["hard_ban_count"]:
            regressions.append(
                f"{item_id}: HARD BANS {base['hard_ban_count']} → {cur['hard_ban_count']}"
            )
        if cur["marker_count"] > base["marker_count"]:
            regressions.append(
                f"{item_id}: маркеры {base['marker_count']} → {cur['marker_count']}"
            )
        if cur["cv_len"] < base["cv_len"]:
            regressions.append(
                f"{item_id}: CV ритма {base['cv_len']} → {cur['cv_len']} (ровнее)"
            )
    return regressions


# --- CLI ------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Eval-харнес humanizer-ru: метрики + опц. детекторы + опц. LLM-судья"
    )
    ap.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS,
                    help="каталог корпуса (с meta.json)")
    ap.add_argument("--humanized", type=Path, default=None,
                    help="каталог с очеловеченными версиями <id>.txt (before/after)")
    ap.add_argument("--detectors", action="store_true",
                    help="включить реальные детекторы (ollama_llm на локальной Ollama; "
                         "облачные при наличии ключей)")
    ap.add_argument("--perplexity", action="store_true",
                    help="добавить приближённый perplexity-детектор ollama_ppl "
                         "(дорогой, по семплу; нужны Ollama + razdel)")
    ap.add_argument("--judge", action="store_true",
                    help="включить LLM-судью «человечность» (по умолчанию локальная Ollama; "
                         "Anthropic опционально при ANTHROPIC_API_KEY)")
    ap.add_argument("--faithfulness", action="store_true",
                    help="проверка сохранности смысла raw→humanized (cosine + meaning, "
                         "локальная Ollama + nomic-embed-text)")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT,
                    help="каталог для results.json (по умолчанию eval/out)")
    ap.add_argument("--baseline", type=Path, default=None,
                    help="эталон для regression-гейта: exit 1 при просадке метрик")
    ap.add_argument("--save-baseline", action="store_true",
                    help="записать текущий снимок метрик как эталон baseline.json")
    args = ap.parse_args()

    if not (args.corpus / "meta.json").exists():
        print(f"[ошибка] не найден {args.corpus / 'meta.json'}", file=sys.stderr)
        return 2

    results, env = evaluate(
        args.corpus,
        args.humanized,
        args.detectors,
        args.judge,
        use_perplexity=args.perplexity,
        use_faithfulness=args.faithfulness,
    )

    # Сохраняем результаты.
    args.out.mkdir(parents=True, exist_ok=True)
    results_json = {
        "env": env,
        "items": [r.as_dict() for r in results],
    }
    (args.out / "results.json").write_text(
        json.dumps(results_json, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # RESULTS.md — публичный артефакт в корне eval/.
    md = render_markdown(results, env)
    (EVAL_DIR / "RESULTS.md").write_text(md, encoding="utf-8")

    # baseline.
    baseline_path = args.out / "baseline.json"
    if args.save_baseline:
        snap = _metric_snapshot(results)
        baseline_path.write_text(
            json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"[baseline] эталон записан в {baseline_path}")

    print(f"[ok] results.json -> {args.out / 'results.json'}")
    print(f"[ok] RESULTS.md   -> {EVAL_DIR / 'RESULTS.md'}")
    det = env["detectors_available"]
    print(f"[инфо] ollama: {'жива' if env.get('ollama_available') else 'нет'} "
          f"({env.get('ollama_model')}); детекторы: {', '.join(det) if det else 'нет'}; "
          f"судья: {env.get('judge_backend') or 'нет'}; "
          f"faithfulness: {'да' if env.get('faithfulness_available') else 'нет'}; "
          f"humanized: {'да' if env['has_humanized'] else 'нет'}")

    # regression-гейт.
    if args.baseline is not None:
        if not args.baseline.exists():
            print(f"[ошибка] эталон {args.baseline} не найден", file=sys.stderr)
            return 2
        regressions = check_regression(results, args.baseline)
        if regressions:
            print("\n[РЕГРЕССИЯ] метрики просели относительно эталона:", file=sys.stderr)
            for r in regressions:
                print(f"  ✗ {r}", file=sys.stderr)
            return 1
        print("[regression] ✓ метрики не хуже эталона")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
