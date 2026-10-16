#!/usr/bin/env python3
"""Тесты MCP-сервера (humanizer_metrics/mcp_server.py).

Без pytest: прямой вызов обработчика и один настоящий обмен по stdio, запуск
`python scripts/test_mcp_server.py`. Фиксируют контракт сервера:
- initialize отвечает только поддерживаемой версией протокола;
- версия сервера берётся из файлов релиза, а не из случайно установленного пакета;
- scan_text отдаёт тот же отчёт, что scan.py --json, с позициями и
  предупреждением о нерусском тексте;
- BOM, пустой текст, неизвестный жанр и инструмент не роняют сервер.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "skills" / "humanizer-ru" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from humanizer_metrics import mcp_server as mcp  # noqa: E402

# Консоль Windows (cp1252, cp1251) не печатает кириллицу и ✓: тест пишет UTF-8.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

passed = 0


def check(cond: bool, msg: str) -> None:
    global passed
    assert cond, f"FAIL: {msg}"
    passed += 1


def call(method: str, params: dict | None = None, rid: int = 1) -> dict:
    return mcp.handle({"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}})


# --- initialize: версия протокола --------------------------------------------
for asked in mcp.SUPPORTED_PROTOCOL_VERSIONS:
    got = call("initialize", {"protocolVersion": asked})["result"]["protocolVersion"]
    check(got == asked, f"поддерживаемая версия {asked} возвращается как есть, получено {got}")
for asked in ("2099-01-01", "", None, 42):
    got = call("initialize", {"protocolVersion": asked})["result"]["protocolVersion"]
    check(got == mcp.SUPPORTED_PROTOCOL_VERSIONS[0],
          f"неподдерживаемая версия {asked!r}: отвечаем последней своей, получено {got}")

# --- версия сервера из файлов релиза -----------------------------------------
pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
release = re.search(r'^version = "([\d.]+)"', pyproject, re.MULTILINE).group(1)
info = call("initialize", {"protocolVersion": "2025-06-18"})["result"]["serverInfo"]
check(info["version"] == release, f"версия сервера {info['version']} совпадает с релизом {release}")

# --- tools/list и scan_text ---------------------------------------------------
names = [t["name"] for t in call("tools/list")["result"]["tools"]]
check(names == ["scan_text", "compare_texts"], f"инструменты: {names}")

res = call("tools/call", {"name": "scan_text",
                          "arguments": {"text": "Чистая строка. В современном мире всё сложно."}})["result"]
sc = res["structuredContent"]
check(not res["isError"] and sc["hard_ban_count"] == 1, "scan_text находит бан")
check(sc["hard_bans"][0]["positions"] == [15], f"позиции бана: {sc['hard_bans'][0]}")
check("warning" not in sc and "не похож" not in res["content"][0]["text"], "у русского текста нет предупреждения")

# Тот же отчёт, что у CLI: общий конвейер scan_report.
cli = subprocess.run([sys.executable, str(SCRIPTS / "scan.py"), "-", "--json"],
                     input="Чистая строка. В современном мире всё сложно.", capture_output=True, text=True, encoding="utf-8")
check(json.loads(cli.stdout) == sc, "scan.py --json и scan_text отдают один и тот же отчёт")

res = call("tools/call", {"name": "scan_text",
                          "arguments": {"text": "This is plain English text, nothing Russian here."}})["result"]
check(res["structuredContent"].get("warning") and "не похож на русский" in res["content"][0]["text"],
      "нерусский текст: предупреждение в structuredContent и в тексте ответа")

res = call("tools/call", {"name": "scan_text",
                          "arguments": {"text": "﻿Привет, как дела? Поедем завтра на дачу."}})["result"]
tech = [h for h in res["structuredContent"]["markers"] if h["category"] == "Технические маркеры"]
plain = mcp.scan("Привет, как дела? Поедем завтра на дачу.")["score"]
check(not tech and res["structuredContent"]["score"] == plain, f"BOM не невидимый символ: {tech}")

res = call("tools/call", {"name": "scan_text", "arguments": {"text": "﻿  "}})["result"]
check(res["structuredContent"] == {"empty": True}, "пустой текст с BOM: empty")

res = call("tools/call", {"name": "scan_text", "arguments": {"text": "Текст.", "genre": "poetry"}})["result"]
check(res["isError"] and "неизвестный жанр" in res["content"][0]["text"], "неизвестный жанр: isError")
check(call("tools/call", {"name": "nope"})["error"]["code"] == -32602, "неизвестный инструмент: -32602")
check(call("resources/list")["error"]["code"] == -32601, "неизвестный метод: -32601")
check(mcp.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None,
      "на уведомление ответа нет")

# --- compare_texts --------------------------------------------------------------
res = call("tools/call", {"name": "compare_texts", "arguments": {
    "before": "Мы внедрили удалёнку в 2023 году.",
    "after": "Стэнфорд мерил: на 13% продуктивнее, удалёнка с 2023 года."}})["result"]
added = res["structuredContent"]["facts"]["added"]
check("число:13" in added and "имя:стэнфорд" in added, f"compare_texts ловит выдуманные факты: {added}")

# --- настоящий обмен по stdio ---------------------------------------------------
lines = [
    {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05"}},
    {"jsonrpc": "2.0", "method": "notifications/initialized"},
    {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
     "params": {"name": "scan_text", "arguments": {"text": "Стоит отметить, что всё хорошо."}}},
]
proc = subprocess.run([sys.executable, "-m", "humanizer_metrics.mcp_server"], cwd=SCRIPTS,
                      input="\n".join(json.dumps(x, ensure_ascii=False) for x in lines) + "\nне json\n",
                      capture_output=True, text=True, encoding="utf-8")
replies = [json.loads(x) for x in proc.stdout.splitlines()]
check(proc.returncode == 0 and len(replies) == 3, f"stdio: три ответа на два запроса и мусор: {proc.stdout}")
check(replies[0]["result"]["protocolVersion"] == "2024-11-05", "stdio: версия протокола клиента")
check(replies[1]["result"]["structuredContent"]["hard_ban_count"] == 1, "stdio: scan_text работает")
check(replies[2]["error"]["code"] == -32700, "stdio: невалидный JSON даёт -32700")


if __name__ == "__main__":
    print(f"OK: {passed} проверок прошли.")
