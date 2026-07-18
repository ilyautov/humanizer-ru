#!/usr/bin/env python3
"""Trigger-eval харнес humanizer-ru: проверяет границу активации скилла.

В отличие от run_eval.py (он меряет КАЧЕСТВО очеловечивания), этот харнес следит
за тем, чтобы «pushy» описание скилла не размывало границу активации: на каких
запросах humanizer-ru должен срабатывать (should-trigger) и на каких молчать
(near-miss: код, английский).

Лёгкий детерминированный слой — без LLM, ключей и сети, гоняется в CI:

  1. guard описания — scope-фразы («ТОЛЬКО русский», «НЕ используй для: код»,
     «Для английского — оригинальный humanizer») всё ещё в SKILL.md. Ловит
     рассинхрон: если кто-то ослабит границу в описании, CI упадёт.
  2. модальность запроса (ru / en / код) по поверхностным признакам ->
     предсказание trigger/no-trigger. Это honest-прокси той части решения о
     вызове, что видна на поверхности (язык и модальность).

Полное решение «вызвать ли скилл по смыслу запроса» в бою принимает сам Клод по
описанию — это не воспроизвести скриптом и здесь намеренно не воспроизводится.
Описание читается живьём из SKILL.md, чтобы тест проверял текущую границу.

Гейт (exit code):
  - guard описания провален                 -> exit 1 (scope-граница размыта);
  - false-activation > 0                     -> exit 1 (near-miss принят за триггер);
  - с --strict ещё и missed-trigger > 0      -> exit 1 (граница «протекает»).

Запуск:
    python eval/run_triggers.py            # этот режим гоняется в CI
    python eval/run_triggers.py --strict   # пропуск триггера тоже провал
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
ROOT = EVAL_DIR.parent
DEFAULT_CORPUS = EVAL_DIR / "triggers.json"
DEFAULT_OUT = EVAL_DIR / "out"
SKILL_MD = ROOT / "skills" / "humanizer-ru" / "SKILL.md"

# Scope-фраза описания: эти подстроки задают границу активации. Если из SKILL.md
# исчезла любая — описание размыло scope, и trigger-eval теряет смысл. Ловим
# это детерминированно, в CI, без LLM.
REQUIRED_DESCRIPTION_PHRASES = [
    "ТОЛЬКО",          # «Работает ТОЛЬКО с русским языком»
    "русск",           # привязка к русскому
    "англ",            # «Для английского используй оригинальный humanizer»
    "НЕ используй",     # явный блок исключений
    "код",             # «НЕ используй для: ... код»
]

# Признаки кода для детерминированной модальности (вне ```-ограды).
_CODE_SIGNALS = [
    r"\bdef\s+\w+\s*\(", r"\bfunction\b", r"\bimport\s+\w", r"\bconst\s+\w",
    r"\breturn\b", r"=>", r"\bSELECT\b", r"\bFROM\b", r";\s*$", r"\{\s*$",
]
_CYR_RE = re.compile(r"[а-яё]", re.IGNORECASE)
_LAT_RE = re.compile(r"[a-z]", re.IGNORECASE)


@dataclass
class CaseResult:
    id: str
    prompt: str
    lang: str
    category: str
    note: str
    expect_trigger: bool
    det_modality: str                 # ru | en | code
    det_trigger: bool                 # предсказание детерминированного гейта

    @property
    def correct(self) -> bool:
        return self.det_trigger == self.expect_trigger

    @property
    def false_activation(self) -> bool:
        return self.det_trigger and not self.expect_trigger

    @property
    def missed(self) -> bool:
        return (not self.det_trigger) and self.expect_trigger

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "lang": self.lang,
            "category": self.category,
            "expect_trigger": self.expect_trigger,
            "det_modality": self.det_modality,
            "det_trigger": self.det_trigger,
            "correct": self.correct,
            "note": self.note,
        }


# --- чтение живого описания скилла ----------------------------------------


def read_skill_description(skill_md: Path = SKILL_MD) -> str:
    """Достаёт поле description из YAML-фронтматтера SKILL.md (живьём).

    Тест должен проверять ТЕКУЩЕЕ описание, а не зашитую копию — иначе он не
    поймает рассинхрон. Поддерживает значение в кавычках и без.
    """
    text = skill_md.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise ValueError(f"{skill_md}: нет YAML-фронтматтера")
    end = text.find("\n---", 3)
    front = text[3:end] if end != -1 else text
    m = re.search(r'^description:\s*(.+?)\s*$', front, re.MULTILINE)
    if not m:
        raise ValueError(f"{skill_md}: не найдено поле description")
    val = m.group(1).strip()
    if len(val) >= 2 and val[0] in "\"'" and val[-1] == val[0]:
        val = val[1:-1]
    return val


def check_description_guard(description: str) -> list[str]:
    """Возвращает список отсутствующих scope-фраз (пусто = граница на месте)."""
    return [p for p in REQUIRED_DESCRIPTION_PHRASES if p not in description]


# --- детерминированный гейт -----------------------------------------------


def classify_modality(prompt: str) -> str:
    """ru | en | code по поверхностным признакам.

    Код важнее языка инструкции: «отрефактори ```python ...```» — это код, хотя
    инструкция по-русски. Поэтому код детектируем первым (ограда ``` или >=2
    кодовых сигнала), затем — по соотношению кириллицы и латиницы.
    """
    if "```" in prompt:
        return "code"
    hits = sum(1 for pat in _CODE_SIGNALS if re.search(pat, prompt, re.MULTILINE))
    if hits >= 2:
        return "code"
    cyr = len(_CYR_RE.findall(prompt))
    lat = len(_LAT_RE.findall(prompt))
    if cyr == 0 and lat == 0:
        return "ru"  # пустой/символьный — не near-miss, не караем
    return "ru" if cyr >= lat else "en"


def deterministic_trigger(prompt: str) -> tuple[str, bool]:
    """(модальность, предсказание trigger). Триггерим только русскую модальность."""
    modality = classify_modality(prompt)
    return modality, modality == "ru"


# --- основной прогон ------------------------------------------------------


def evaluate(corpus: Path, description: str) -> tuple[list[CaseResult], dict]:
    cases = json.loads(corpus.read_text(encoding="utf-8"))["cases"]
    results: list[CaseResult] = []
    for c in cases:
        modality, det_trig = deterministic_trigger(c["prompt"])
        results.append(CaseResult(
            id=c["id"],
            prompt=c["prompt"],
            lang=c.get("lang", modality),
            category=c.get("category", ""),
            note=c.get("note", ""),
            expect_trigger=c["expect"] == "trigger",
            det_modality=modality,
            det_trigger=det_trig,
        ))
    env = {
        "description_under_test": description,
        "description_guard_missing": check_description_guard(description),
    }
    return results, env


def stats(results: list[CaseResult]) -> dict:
    """Счётчики и precision/recall для класса «trigger»."""
    total = len(results)
    correct = sum(1 for r in results if r.correct)
    tp = sum(1 for r in results if r.expect_trigger and r.det_trigger)
    fp = sum(1 for r in results if r.false_activation)
    fn = sum(1 for r in results if r.missed)
    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    return {
        "total": total, "correct": correct,
        "accuracy": correct / total if total else 1.0,
        "false_activation": fp, "missed": fn,
        "precision": precision, "recall": recall,
    }


# --- генерация TRIGGERS.md ------------------------------------------------


def _yn(b: bool) -> str:
    return "✓" if b else "✗"


def render_markdown(results: list[CaseResult], env: dict) -> str:
    s = stats(results)
    L: list[str] = []
    L.append("# Trigger-eval humanizer-ru\n")
    L.append(
        "Автогенерируемый отчёт (`eval/run_triggers.py`). Проверяет НЕ качество "
        "очеловечивания (это `RESULTS.md`), а **границу активации**: должен ли "
        "скилл срабатывать на запросе. Лёгкий детерминированный слой без LLM — "
        "guard scope-фраз в описании из `SKILL.md` + модальность запроса "
        "(русский / английский / код). Полное решение «по смыслу» в бою "
        "принимает сам ассистент по описанию; здесь страхуем поверхностную "
        "границу.\n"
    )

    # --- guard описания ---
    missing = env["description_guard_missing"]
    L.append("## Guard описания (scope-граница)\n")
    if missing:
        L.append(
            "⚠ **В описании из SKILL.md пропали scope-фразы:** "
            + ", ".join(f"`{m}`" for m in missing)
            + ". Граница активации размыта — верните её в `description`.\n"
        )
    else:
        L.append(
            "✓ Scope-фразы на месте (`ТОЛЬКО русский`, `Для английского — "
            "оригинальный humanizer`, `НЕ используй для: код`). Граница "
            "активации в описании цела.\n"
        )

    # --- сводка ---
    n_trig = sum(1 for r in results if r.expect_trigger)
    n_no = len(results) - n_trig
    L.append("## Сводка\n")
    L.append(f"- Кейсов: **{len(results)}** (should-trigger **{n_trig}**, "
             f"near-miss **{n_no}**).")
    L.append(f"- Точность гейта: **{s['accuracy']*100:.0f}%** "
             f"({s['correct']}/{s['total']}); ложных срабатываний "
             f"**{s['false_activation']}**, пропусков триггера **{s['missed']}**.")
    L.append(
        "\n> **Ложное срабатывание** (near-miss принят за триггер) — опасное "
        "направление для «pushy» описания: скилл полез бы в код или английский. "
        "Это жёсткий гейт CI. Пропуск триггера — мягкое предупреждение (провал "
        "только с `--strict`).\n"
    )

    # --- таблица кейсов ---
    L.append("## Кейсы\n")
    L.append("| id | категория | ждём | модальность | вердикт |")
    L.append("|---|---|---|---|---|")
    for r in results:
        expect = "trigger" if r.expect_trigger else "no-trigger"
        got = ("trigger" if r.det_trigger else "no-trigger") + f" {_yn(r.correct)}"
        L.append(f"| `{r.id}` | {r.category} | {expect} | {r.det_modality} | {got} |")
    L.append("")

    # --- near-miss по категориям ---
    L.append("## Near-miss по категориям (скилл НЕ должен лезть)\n")
    L.append("| категория | кейсов | гейт держит |")
    L.append("|---|---|---|")
    cats: dict[str, list[CaseResult]] = {}
    for r in results:
        if not r.expect_trigger:
            cats.setdefault(r.category, []).append(r)
    for cat, rs in sorted(cats.items()):
        held = sum(1 for r in rs if not r.det_trigger)
        L.append(f"| {cat} | {len(rs)} | {held}/{len(rs)} |")
    L.append("")

    L.append("---\n")
    L.append(
        "Слой детерминированный: без ключей, сети и LLM — гоняется в CI. "
        "Проверяет ту часть решения о вызове, что видна на поверхности (язык и "
        "модальность), и что scope-граница в описании цела. Описание берётся "
        "живьём из `SKILL.md`."
    )
    return "\n".join(L) + "\n"


# --- CLI ------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Trigger-eval humanizer-ru: граница активации скилла "
                    "(детерминированный guard + модальность)"
    )
    ap.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS,
                    help="JSON-корпус кейсов (по умолчанию eval/triggers.json)")
    ap.add_argument("--strict", action="store_true",
                    help="считать провалом и пропуски триггера, не только "
                         "ложные срабатывания")
    ap.add_argument("--skill", type=Path, default=SKILL_MD,
                    help="путь к SKILL.md (источник живого description)")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT,
                    help="каталог для triggers.json (по умолчанию eval/out)")
    args = ap.parse_args()

    if not args.corpus.exists():
        print(f"[ошибка] не найден корпус {args.corpus}", file=sys.stderr)
        return 2
    try:
        description = read_skill_description(args.skill)
    except (OSError, ValueError) as e:
        print(f"[ошибка] не прочитать описание скилла: {e}", file=sys.stderr)
        return 2

    results, env = evaluate(args.corpus, description)
    s = stats(results)

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "triggers.json").write_text(
        json.dumps({"env": env, "stats": s,
                    "cases": [r.as_dict() for r in results]},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (EVAL_DIR / "TRIGGERS.md").write_text(
        render_markdown(results, env), encoding="utf-8"
    )
    print(f"[ok] triggers.json -> {args.out / 'triggers.json'}")
    print(f"[ok] TRIGGERS.md   -> {EVAL_DIR / 'TRIGGERS.md'}")
    print(f"[инфо] точность {s['accuracy']*100:.0f}% ({s['correct']}/{s['total']}), "
          f"ложных срабатываний {s['false_activation']}, пропусков {s['missed']}")

    # --- гейт ---
    failures: list[str] = []
    missing = env["description_guard_missing"]
    if missing:
        failures.append("guard описания: пропали scope-фразы " + ", ".join(missing))
    if s["false_activation"] > 0:
        bad = [r.id for r in results if r.false_activation]
        failures.append(f"ложные срабатывания на near-miss ({', '.join(bad)})")
    if args.strict and s["missed"] > 0:
        bad = [r.id for r in results if r.missed]
        failures.append(f"пропуски триггера, --strict ({', '.join(bad)})")

    if failures:
        print("\n[ПРОВАЛ] trigger-eval:", file=sys.stderr)
        for f in failures:
            print(f"  ✗ {f}", file=sys.stderr)
        return 1
    print("[gate] ✓ scope-граница цела, ложных срабатываний нет")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
