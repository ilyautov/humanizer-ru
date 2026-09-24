#!/usr/bin/env python3
"""Скилл как в живой сессии: модель сама читает SKILL.md и запускает сканер.

`probe_installed_skill.py` вставляет SKILL.md в запрос и отключает инструменты,
поэтому шаг «сканер до и после» не измеряет. Здесь у модели есть Read и Bash
(только `python3`), скилл берётся из переданной папки (из рабочей ветки, не из
~/.claude), остальная обвязка Claude Code выключена через --safe-mode. `python3`
в PATH указывает на интерпретатор, которым запущен этот скрипт: в нём должны
стоять razdel и pymorphy3, как у пользователя с рабочим сканером.

Формат выхода тот же, что у probe_installed_skill.py (manifest.json, raw/,
blind/), поэтому считать метрики можно теми же скриптами; условие одно: skill.

    .venv/bin/python eval/probe_agentic_skill.py --skill skills/humanizer-ru \\
      --cases-only cases.json --output eval/out/run-agentic --model sonnet \\
      --task "Очеловечь этот текст. Верни только итоговый текст, без комментариев."
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from probe_installed_skill import TASK, digest, write_json

# Отчёт скилла («Чистота: было N, стало M») и заметки о процессе («Файл не создался»,
# «97/100, hard bans clean») не часть текста. В режиме -p они попадают в последнее
# сообщение то в конец, то в начало, поэтому первый абзац снимается, если похож на
# служебную заметку, а хвост снимается от строки «Чистота:».
REPORT_TAIL = re.compile(r"\n+(?:-{3,}\s*\n+)?\**Чистота:[\s\S]*$")
META_HEAD = re.compile(r"\d+\s*/\s*100|Чистота|\b[Ss]core\b|\bclean\b|\b[Ff]inal\b|[Фф]айл\w* не|"
                       r"итоговый текст|итоговую версию|финальную версию|сканер|временных файлов|"
                       r"лишних файлов|Пользователь просил")


def strip_report(text: str) -> str:
    text = REPORT_TAIL.sub("", text.strip()).strip()
    head, sep, rest = text.partition("\n\n")
    if sep and META_HEAD.search(head):
        text = rest.strip()
    return text


def run(job: dict, text: str, skill: Path, task: str, out: Path, model: str,
        timeout: int) -> dict:
    prompt = (f"Скилл humanizer-ru лежит в папке {skill}: прочитай {skill}/SKILL.md "
              f"и выполни по нему просьбу ниже.\n\n{task}{text}")
    command = ["claude", "-p", "--safe-mode", "--strict-mcp-config", "--no-session-persistence",
               "--tools", "Read,Bash", "--allowedTools", "Read", "Bash(python3:*)",
               "--add-dir", str(skill), "--output-format", "stream-json", "--verbose",
               "--model", model]
    env = {**os.environ, "PATH": f"{Path(sys.executable).parent}:{os.environ['PATH']}"}
    record = {**job, "prompt_sha256": digest(prompt), "command": command}
    try:
        with tempfile.TemporaryDirectory() as cwd:
            proc = subprocess.run(command, input=prompt, text=True, capture_output=True,
                                  timeout=timeout, cwd=cwd, env=env)
        record.update(returncode=proc.returncode, stderr=proc.stderr, stdout=proc.stdout)
        events = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
        response = next(e for e in reversed(events) if e.get("type") == "result")
        record["response"] = response
        # Какие команды модель реально запускала: доказательство, что сканер работал.
        record["bash"] = [c["input"].get("command", "") for e in events
                          if e.get("type") == "assistant"
                          for c in e.get("message", {}).get("content", [])
                          if c.get("type") == "tool_use" and c.get("name") == "Bash"]
        record["scan_runs"] = sum("scan.py" in b for b in record["bash"])
        result = response.get("result")
        record["ok"] = (proc.returncode == 0 and not response.get("is_error", True)
                        and isinstance(result, str) and bool(result.strip()))
        if record["ok"]:
            record["result_raw"] = result
            response["result"] = strip_report(result)
            write_json(out / "blind" / f"{job['id']}.json",
                       {"id": job["id"], "case": job["case"], "source": text,
                        "output": response["result"]})
    except subprocess.TimeoutExpired as exc:
        record.update(ok=False, error=f"TimeoutExpired: {exc}", timed_out=True)
    except (OSError, ValueError, TypeError, StopIteration) as exc:
        record.update(ok=False, error=f"{type(exc).__name__}: {exc}")
    write_json(out / "raw" / f"{job['id']}.json", record)
    return {"id": job["id"], "case": job["case"], "ok": record["ok"]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--skill", type=Path, required=True)
    ap.add_argument("--cases-only", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--model", default="sonnet")
    ap.add_argument("--task")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--timeout", type=int, default=900)
    args = ap.parse_args()
    skill = args.skill.resolve()
    task = args.task.rstrip() + "\n\n" if args.task else TASK
    inputs = json.loads(args.cases_only.read_text(encoding="utf-8"))
    jobs = [{"id": f"agentic-{i:03d}", "case": c, "arm": "skill", "repeat": 1}
            for i, c in enumerate(inputs, 1)]
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "raw").mkdir()
    (args.output / "blind").mkdir()
    write_json(args.output / "manifest.json", {
        "skill_path": str(skill), "model_requested": args.model, "task": task,
        "cli_version": subprocess.check_output(["claude", "--version"], text=True).strip(),
        "file_sha256": {n: digest((skill / n).read_text(encoding="utf-8"))
                        for n in ("SKILL.md", "edit-log.md", "references/catalog.md")},
        "inputs": inputs, "jobs": jobs})
    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(run, j, inputs[j["case"]]["text"], skill, task, args.output,
                               args.model, args.timeout) for j in jobs]
        for f in as_completed(futures):
            results.append(f.result())
            print(json.dumps({"done": len(results), "total": len(jobs), **results[-1]},
                             ensure_ascii=False), flush=True)
    write_json(args.output / "status.json", results)
    return 0 if all(r["ok"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
