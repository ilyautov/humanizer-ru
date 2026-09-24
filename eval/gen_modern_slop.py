#!/usr/bin/env python3
"""Корпус современного слопа: обычные задания пользователя, свежие модели.

Зачем. Сырой корпус eval/corpus/raw карикатурный: 10+ хард-банов на 100 слов.
Такой текст сканер ловит всегда, гейты зелёные, а то, что пишут модели 2026
года («Вот что помогает:», «не от дома, а от отсутствия границ»), получает
89-98 «чисто». Здесь те же задания, что пользователь даёт чату: пост в канал,
письмо клиенту, карточка товара, объяснение, и ответ модели без правок.

Бэкенды (подписки и локальные модели, ключи только из окружения/.env):
  claude:haiku, claude:sonnet   через `claude -p`, без скиллов и инструментов
  codex[:<model>]               через `codex exec` с пустым HOME: иначе Codex
                                читает ~/.agents/skills, а там наш же скилл, и
                                он молча чистит русский вывод агента
  ollama:<model>                локальный демон
  deepseek, gigachat, gemini    при наличии ключа (DEEPSEEK_API_KEY и т.п.)

Результат дописывается в gitignored eval/out/modern-slop.jsonl; готовые пары
(id, model) пропускаются, так что прогон можно прерывать и продолжать.

    python eval/gen_modern_slop.py claude:haiku ollama:gemma3:27b
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import urllib.request

ROOT = Path(__file__).resolve().parent.parent
PROMPTS = ROOT / "eval" / "modern_slop_prompts.json"
OUT = ROOT / "eval" / "out" / "modern-slop.jsonl"
# Параллельные прогоны (облако и ollama) пишут каждый в свой файл: modern-slop.<tag>.jsonl.


def load_env() -> None:
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"'))


def gen_claude(model: str, prompt: str) -> str:
    # Чистая папка и пустой набор инструментов: ни CLAUDE.md, ни скиллов
    # (в том числе нашего), модель отвечает как в обычном чате.
    with tempfile.TemporaryDirectory() as tmp:
        r = subprocess.run(
            ["claude", "-p", "--model", model, "--disable-slash-commands",
             "--system-prompt", "Ты полезный ассистент.", "--tools", ""],
            input=prompt, capture_output=True, text=True, cwd=tmp, timeout=300)
    if r.returncode:
        raise RuntimeError(r.stderr.strip()[:300])
    return r.stdout


def gen_codex(model: str, prompt: str) -> str:
    with tempfile.TemporaryDirectory() as home:
        codex_home = Path(home) / ".codex"
        codex_home.mkdir()
        (codex_home / "auth.json").write_bytes((Path.home() / ".codex" / "auth.json").read_bytes())
        out = Path(home) / "answer.txt"
        cmd = ["codex", "exec", "--skip-git-repo-check", "--ephemeral", "-s", "read-only", "-o", str(out)]
        if model:
            cmd += ["-m", model]
        env = {**os.environ, "HOME": home, "CODEX_HOME": str(codex_home)}
        r = subprocess.run(cmd + [prompt], capture_output=True, text=True, cwd=home, env=env, timeout=300,
                           stdin=subprocess.DEVNULL)
        if r.returncode or not out.exists():
            raise RuntimeError(r.stderr.strip()[-300:])
        return out.read_text(encoding="utf-8")


def post_json(url: str, body: dict, headers: dict | None = None, timeout: int = 300) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def gen_ollama(model: str, prompt: str) -> str:
    host = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
    r = post_json(f"{host}/api/generate", {"model": model, "prompt": prompt, "stream": False}, timeout=900)
    return re.sub(r"<think>.*?</think>", "", r["response"], flags=re.S)


def gen_openai_compat(base: str, key_env: str, model: str, prompt: str) -> str:
    key = os.environ.get(key_env)
    if not key:
        raise RuntimeError(f"нет {key_env}")
    r = post_json(f"{base}/chat/completions", {"model": model, "messages": [{"role": "user", "content": prompt}]},
                  headers={"Authorization": f"Bearer {key}"})
    return r["choices"][0]["message"]["content"]


def generate(backend: str, prompt: str) -> str:
    kind, _, model = backend.partition(":")
    if kind == "claude":
        return gen_claude(model, prompt)
    if kind == "codex":
        return gen_codex(model, prompt)
    if kind == "ollama":
        return gen_ollama(model, prompt)
    if kind == "deepseek":
        return gen_openai_compat("https://api.deepseek.com", "DEEPSEEK_API_KEY", model or "deepseek-chat", prompt)
    if kind == "gemini":
        return gen_openai_compat("https://generativelanguage.googleapis.com/v1beta/openai", "GEMINI_API_KEY",
                                 model or "gemini-2.5-flash", prompt)
    raise ValueError(f"неизвестный бэкенд {backend}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("backends", nargs="+")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--tag", default="", help="суффикс файла для параллельного прогона")
    ap.add_argument("--prompts", type=Path, default=PROMPTS, help="отложенная выборка: modern_slop_holdout.json")
    args = ap.parse_args()
    load_env()
    out = OUT.with_suffix(f".{args.tag}.jsonl") if args.tag else OUT
    prompts = json.loads(args.prompts.read_text())
    done = set()
    if out.exists():
        for line in out.read_text().splitlines():
            row = json.loads(line)
            done.add((row["id"], row["model"]))
    out.parent.mkdir(parents=True, exist_ok=True)
    lock = threading.Lock()

    for backend in args.backends:
        todo = [p for p in prompts if (p["id"], backend) not in done]
        # Ollama серийная: параллелить её незачем.
        workers = 1 if backend.startswith("ollama") else args.workers

        def run(p: dict) -> None:
            try:
                text = generate(backend, p["prompt"])
            except Exception as e:  # noqa: BLE001 — прогон продолжается, ошибка видна
                print(f"[{backend}] {p['id']}: {e}", file=sys.stderr)
                return
            with lock, out.open("a") as f:
                f.write(json.dumps({**p, "model": backend, "text": text}, ensure_ascii=False) + "\n")
            print(f"[{backend}] {p['id']} ok", flush=True)

        with ThreadPoolExecutor(workers) as ex:
            list(ex.map(run, todo))
    return 0


if __name__ == "__main__":
    sys.exit(main())
