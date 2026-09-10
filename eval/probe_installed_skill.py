#!/usr/bin/env python3
"""Paired, fresh-context Claude probes; saves raw evidence and blind review packets.

No skill edits or automatic authorship/quality verdicts. Requires authenticated
Claude CLI. Each output directory is new; failed calls are retained, not retried.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import random
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SYSTEM = "Ты редактор русскоязычного текста. Следуй заданию пользователя. Инструментов нет."
TASK = ("Отредактируй текст, убери нейросетевую манеру. Сохрани смысл, факты и "
        "авторский голос. Если правки не нужны, оставь текст без изменений. "
        "Верни только итоговый текст, без комментариев.\n\n")
VOICE = ("Пилот мы закрыли. Не потому, что модель тупая: из 12 сотрудников ей "
         "пользовались двое. Остальные продолжали писать в старый чат.\n\n"
         "За три недели мы не получили доказательств экономии времени. Это не "
         "значит, что экономии нет; мы её не измерили. 80 тысяч рублей за настройку "
         "уже заплатили, ещё 20 тысяч в месяц за поддержку платить не стали.\n\n"
         "Меня бесит не цена. Меня бесит, что до запуска никто не спросил этих "
         "десятерых, зачем им вообще новый интерфейс. Вернёмся к вопросу в ноябре. "
         "Пока я за то, чтобы оставить старый чат в покое.")


def digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_skill_files(skill: Path) -> dict:
    return {name: (skill / name).read_text(encoding="utf-8") for name in
            ("SKILL.md", "edit-log.md", "references/catalog.md")}


def build_inputs(skill: Path | None) -> tuple[dict, dict]:
    files = load_skill_files(skill) if skill is not None else {}
    cases = {
        "expert": "raw/expert_claude_03.txt",
        "business": "raw/business_claude_05.txt",
        "docs": "raw/docs_gpt_07.txt",
        "encyclopedia": "human/wiki_baikal.txt",
    }
    inputs = {key: {"text": (ROOT / "eval/corpus" / path).read_text(encoding="utf-8"),
                    "source": path} for key, path in cases.items()}
    inputs["voice"] = {"text": VOICE, "source": "synthetic fixture, not human-authorship evidence"}
    return files, inputs


def build_prompt(arm: str, files: dict, source: str, control_files: dict | None = None,
                 candidate_files: dict | None = None) -> str:
    arms = {"skill": files, "control": control_files}
    if candidate_files:
        arms["candidate"] = candidate_files
    if arm not in arms:
        raise ValueError(f"Unknown or unconfigured arm: {arm}")
    selected = arms[arm]
    prefix = ""
    if selected:
        prefix = "\n\n".join(f"Файл {name}:\n{body}" for name, body in selected.items()) + "\n\n"
    return prefix + TASK + source


def build_jobs(inputs: dict, repeats: int, seed: int, include_candidate: bool = False) -> list:
    arms = ("control", "skill", "candidate") if include_candidate else ("control", "skill")
    jobs = [{"case": case, "arm": arm, "repeat": rep}
            for case in inputs for arm in arms for rep in range(1, repeats + 1)]
    random.Random(seed).shuffle(jobs)
    for i, job in enumerate(jobs, 1):
        job["id"] = f"sample-{i:03d}"
    return jobs


def run_probe(job: dict, files: dict, inputs: dict, out: Path, model: str,
              control_files: dict | None = None, candidate_files: dict | None = None) -> dict:
    source = inputs[job["case"]]["text"]
    prompt = build_prompt(job["arm"], files, source, control_files, candidate_files)
    command = ["claude", "-p", "--safe-mode", "--tools", "", "--strict-mcp-config",
               "--no-session-persistence", "--output-format", "json", "--model", model,
               "--system-prompt", SYSTEM]
    record = {**job, "prompt_sha256": digest(prompt), "command": command}
    try:
        proc = subprocess.run(command, input=prompt, text=True, capture_output=True, timeout=180)
        record.update(returncode=proc.returncode, stderr=proc.stderr, stdout=proc.stdout)
        response = json.loads(proc.stdout)
        record["response"] = response
        record["ok"] = (proc.returncode == 0 and not response.get("is_error", True)
                        and response.get("subtype") == "success"
                        and response.get("stop_reason") == "end_turn"
                        and isinstance(response.get("result"), str)
                        and bool(response["result"].strip()))
        if record["ok"]:
            packet = {"id": job["id"], "case": job["case"], "source": source,
                      "output": response["result"]}
            write_json(out / "blind" / f"{job['id']}.json", packet)
    except subprocess.TimeoutExpired as exc:
        record.update(ok=False, error=f"TimeoutExpired: {exc}", timed_out=True,
                      stdout=(exc.stdout.decode("utf-8", errors="replace")
                              if isinstance(exc.stdout, bytes) else exc.stdout or ""),
                      stderr=(exc.stderr.decode("utf-8", errors="replace")
                              if isinstance(exc.stderr, bytes) else exc.stderr or ""))
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        record.update(ok=False, error=f"{type(exc).__name__}: {exc}")
    write_json(out / "raw" / f"{job['id']}.json", record)
    return {"id": job["id"], "case": job["case"], "ok": record["ok"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    primary = parser.add_mutually_exclusive_group(required=True)
    primary.add_argument("--skill", type=Path, help="Full three-file installed skill")
    primary.add_argument("--skill-prompt", type=Path, help="Self-contained primary instruction file")
    parser.add_argument("--control-skill", type=Path,
                        help="Compare against another full skill instead of no-skill control")
    parser.add_argument("--extra-cases", type=Path, help="JSON object of additional case text/source records")
    parser.add_argument("--cases-only", type=Path, help="Replace default cases with this JSON object")
    parser.add_argument("--candidate-prompt", type=Path,
                        help="Add a third arm with one self-contained instruction file (no implicit references)")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default="claude-opus-5")
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--seed", type=int, default=9102026)
    args = parser.parse_args()
    if args.repeats < 1 or args.workers < 1:
        parser.error("repeats and workers must be positive")
    if args.cases_only:
        files, inputs = (load_skill_files(args.skill) if args.skill else {}), {}
    else:
        files, inputs = build_inputs(args.skill)
    if args.skill_prompt:
        body = args.skill_prompt.read_text(encoding="utf-8")
        if not body.strip():
            parser.error("primary prompt must be nonempty and self-contained")
        files = {"SKILL.md": body}
    control_files = load_skill_files(args.control_skill) if args.control_skill else None
    candidate_files = None
    if args.candidate_prompt:
        body = args.candidate_prompt.read_text(encoding="utf-8")
        if not body.strip():
            parser.error("candidate prompt must be nonempty and self-contained")
        candidate_files = {"SKILL.md": body}
    for case_path in (args.cases_only, args.extra_cases):
        if not case_path:
            continue
        extra = json.loads(case_path.read_text(encoding="utf-8"))
        if (not isinstance(extra, dict) or not extra or set(extra) & set(inputs)
                or not all(isinstance(r, dict) and isinstance(r.get("text"), str)
                           and r["text"].strip() and isinstance(r.get("source"), str)
                           for r in extra.values())):
            parser.error("cases must be a nonempty object of distinct names with nonempty text and source")
        inputs.update(extra)
    jobs = build_jobs(inputs, args.repeats, args.seed, candidate_files is not None)
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "raw").mkdir()
    (args.output / "blind").mkdir()
    write_json(args.output / "manifest.json", {
        "skill_path": str(args.skill.resolve()) if args.skill else None,
        "skill_prompt_path": str(args.skill_prompt.resolve()) if args.skill_prompt else None,
        "model_requested": args.model,
        "cli_version": subprocess.check_output(["claude", "--version"], text=True).strip(),
        "system": SYSTEM, "task": TASK, "files": files,
        "file_sha256": {name: digest(body) for name, body in files.items()},
        "control_skill_path": str(args.control_skill.resolve()) if args.control_skill else None,
        "control_files": control_files,
        "control_file_sha256": {n: digest(b) for n, b in control_files.items()} if control_files else None,
        "candidate_prompt_path": str(args.candidate_prompt.resolve()) if args.candidate_prompt else None,
        "candidate_files": candidate_files,
        "candidate_file_sha256": {n: digest(b) for n, b in candidate_files.items()} if candidate_files else None,
        "inputs": inputs, "jobs": jobs, "repeats": args.repeats,
        "workers": args.workers, "seed": args.seed,
    })
    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(run_probe, job, files, inputs, args.output, args.model,
                               control_files, candidate_files)
                   for job in jobs]
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            print(json.dumps({"done": len(results), "total": len(jobs), **result}), flush=True)
    write_json(args.output / "status.json", results)
    return 0 if all(r["ok"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
