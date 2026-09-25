"""MCP-сервер humanizer-ru: сканер и факт-замок по stdio.

Без зависимостей сверх самого пакета: JSON-RPC 2.0 построчно через stdin и
stdout, как требует транспорт stdio в MCP. Два инструмента:

  scan_text      балл чистоты, штрафы, запреты и маркеры с позициями
  compare_texts  «было и стало» плюс факт-замок между исходником и правкой

Запуск: ru-humanizer-mcp (точка входа пакета ru-humanizer) или
python -m humanizer_metrics.mcp_server. Логи только в stderr: stdout занят
протоколом.
"""

from __future__ import annotations

import json
import sys
from importlib import metadata

from . import analyze, cleanliness_score, diff_facts, facts_verdict
from .markers import (GENRE_MUTED_BANS, GENRE_MUTED_CATEGORIES, GENRES,
                      effective_hard_bans, mute_by_genre)

PROTOCOL_VERSION = "2025-06-18"
SERVER_NAME = "humanizer-ru"

GENRE_SCHEMA = {
    "type": ["string", "null"],
    "enum": [*GENRES, None],
    "description": "Жанр текста. По умолчанию marketing (строгий режим). "
                   "academic, legal, fiction и news снимают маркеры, законные для регистра.",
}

TOOLS = [
    {
        "name": "scan_text",
        "title": "Проверить русский текст на следы нейросети",
        "description": (
            "Балл чистоты 0-100 (85 и выше чисто, 60-84 точечная правка, ниже 60 рерайт), "
            "штрафы с причинами, жёсткие запреты и мягкие маркеры с позициями в тексте, "
            "ритм предложений, морфология и структура. Не детектор авторства: показывает, "
            "что править."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Русский текст для проверки"},
                "genre": GENRE_SCHEMA,
            },
            "required": ["text"],
        },
    },
    {
        "name": "compare_texts",
        "title": "Сравнить исходник и правку",
        "description": (
            "Балл «было и стало» с дельтой и факт-замок: числа, даты, имена, ссылки и код "
            "исходника должны дожить до правки, а новых появиться не должно. Отдельно "
            "кванторы («впервые», «единственный», «в России»), возникшие без источника."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "before": {"type": "string", "description": "Текст до правки"},
                "after": {"type": "string", "description": "Текст после правки"},
                "genre": GENRE_SCHEMA,
            },
            "required": ["before", "after"],
        },
    },
]


def _version() -> str:
    try:
        return metadata.version("ru-humanizer")
    except metadata.PackageNotFoundError:
        return "dev"


def _hits(hits) -> list[dict]:
    return [{"category": h.category, "name": h.marker, "count": h.count,
             "positions": list(h.positions)} for h in hits]


def scan(text: str, genre: str | None = None) -> dict:
    """Тот же расчёт, что в scan.py: балл по жанру, частотные баны и жанровый фильтр."""
    genre = genre or "marketing"
    if genre not in GENRES:
        raise ValueError(f"неизвестный жанр {genre!r}, допустимы: {', '.join(GENRES)}")
    rep = analyze(text)
    sc = cleanliness_score(rep, genre)
    bans = mute_by_genre(effective_hard_bans(rep.hard_bans, rep.rhythm.words),
                         genre, GENRE_MUTED_BANS)
    soft = mute_by_genre(rep.markers, genre, GENRE_MUTED_CATEGORIES)
    return {
        "score": sc.score,
        "band": sc.band,
        "penalties": [{"reason": r, "points": p} for r, p in sc.penalties],
        "notes": list(sc.notes),
        "genre": genre,
        "words": rep.rhythm.words,
        "hard_bans": _hits(bans),
        "hard_ban_count": sum(h.count for h in bans),
        "markers": _hits(soft),
        "marker_count": sum(h.count for h in soft),
        "rhythm": rep.rhythm.as_dict(),
        "morph": rep.morph.as_dict(),
        "structure": rep.structure.as_dict(),
        "lexical": rep.lexical.as_dict(),
        "repeats": rep.repeats.as_dict(),
    }


def _report(d: dict) -> str:
    lines = [f"ЧИСТОТА: {d['score']}/100  [{d['band']}]  ({d['words']} слов, жанр {d['genre']})",
             "  (≥85 чисто · 60-84 точечная правка · <60 рерайт)"]
    for p in d["penalties"]:
        lines.append(f"  {p['points']:+d}  {p['reason']}")
    if not d["penalties"]:
        lines.append("  без штрафов")
    for n in d["notes"]:
        lines.append(f"  ℹ  {n}")
    lines.append("")
    lines.append("HARD BANS:")
    if d["hard_bans"]:
        for h in d["hard_bans"]:
            lines.append(f"  ⛔ {h['name']} ×{h['count']}")
    else:
        lines.append("  ✓ чисто")
    lines.append("")
    lines.append(f"Маркеры: {d['marker_count']}")
    for h in sorted(d["markers"], key=lambda x: -x["count"])[:12]:
        lines.append(f"  • [{h['category']}] «{h['name']}» ×{h['count']}")
    return "\n".join(lines)


def compare(before: str, after: str, genre: str | None = None) -> dict:
    b, a = scan(before, genre), scan(after, genre)
    fd = diff_facts(before, after)
    return {
        "before": {"score": b["score"], "band": b["band"], "hard_ban_count": b["hard_ban_count"],
                   "marker_count": b["marker_count"]},
        "after": a,
        "delta": a["score"] - b["score"],
        "facts": fd.as_dict(),
        "facts_verdict": facts_verdict(fd),
    }


def _compare_report(d: dict) -> str:
    b, a = d["before"], d["after"]
    delta = d["delta"]
    lines = [f"ЧИСТОТА: было {b['score']}, стало {a['score']}/100  [{a['band']}]  ({delta:+d})",
             f"  запретов: {b['hard_ban_count']} → {a['hard_ban_count']}, "
             f"маркеров: {b['marker_count']} → {a['marker_count']}",
             "", "Факт-замок:", f"  {d['facts_verdict']}"]
    f = d["facts"]
    lines += [f"  ✗ новое: {x}" for x in f["added"]]
    lines += [f"  ⚠ потеряно: {x}" for x in f["lost"]]
    lines += [f"  ⚠ утверждение появилось: {x}" for x in f["claims_added"]]
    if f["soft_added"]:
        lines.append(f"  ℹ мелкие количества появились: {', '.join(f['soft_added'])}")
    return "\n".join(lines)


def call_tool(name: str, args: dict) -> dict:
    if name == "scan_text":
        text = args.get("text")
        if not isinstance(text, str):
            raise ValueError("нужен строковый аргумент text")
        if not text.strip():
            return {"content": [{"type": "text", "text": "Текст пуст, сканировать нечего."}],
                    "structuredContent": {"empty": True}, "isError": False}
        d = scan(text, args.get("genre"))
        return {"content": [{"type": "text", "text": _report(d)}],
                "structuredContent": d, "isError": False}
    if name == "compare_texts":
        before, after = args.get("before"), args.get("after")
        if not isinstance(before, str) or not isinstance(after, str):
            raise ValueError("нужны строковые аргументы before и after")
        d = compare(before, after, args.get("genre"))
        return {"content": [{"type": "text", "text": _compare_report(d)}],
                "structuredContent": d, "isError": False}
    raise KeyError(name)


def handle(req: dict) -> dict | None:
    """Ответ на один запрос; None для уведомлений (без id)."""
    method = req.get("method", "")
    rid = req.get("id")
    params = req.get("params") or {}
    is_notification = "id" not in req

    def ok(result):
        return None if is_notification else {"jsonrpc": "2.0", "id": rid, "result": result}

    def err(code, message):
        return None if is_notification else {"jsonrpc": "2.0", "id": rid,
                                             "error": {"code": code, "message": message}}

    if method == "initialize":
        return ok({
            "protocolVersion": params.get("protocolVersion") or PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": _version()},
            "instructions": ("Сканер следов нейросети для русского текста. scan_text даёт балл "
                             "и список того, что править; compare_texts сверяет правку с "
                             "исходником по баллу и фактам. Балл не вердикт об авторстве."),
        })
    if method == "ping":
        return ok({})
    if method == "tools/list":
        return ok({"tools": TOOLS})
    if method == "tools/call":
        name = params.get("name", "")
        try:
            return ok(call_tool(name, params.get("arguments") or {}))
        except KeyError:
            return err(-32602, f"неизвестный инструмент: {name}")
        except ValueError as exc:
            return ok({"content": [{"type": "text", "text": f"Ошибка: {exc}"}], "isError": True})
    if method.startswith("notifications/"):
        return None
    return err(-32601, f"метод не поддерживается: {method}")


def main() -> int:
    stdin = sys.stdin.buffer
    out = sys.stdout.buffer
    for raw in stdin:
        line = raw.decode("utf-8", errors="replace").strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            resp = {"jsonrpc": "2.0", "id": None,
                    "error": {"code": -32700, "message": "невалидный JSON"}}
        else:
            try:
                resp = handle(req) if isinstance(req, dict) else {
                    "jsonrpc": "2.0", "id": None,
                    "error": {"code": -32600, "message": "ожидался объект запроса"}}
            except Exception as exc:  # noqa: BLE001 (сервер не должен падать на одном запросе)
                print(f"[humanizer-ru mcp] {exc!r}", file=sys.stderr)
                resp = {"jsonrpc": "2.0", "id": req.get("id"),
                        "error": {"code": -32603, "message": str(exc)}}
        if resp is not None:
            out.write((json.dumps(resp, ensure_ascii=False) + "\n").encode("utf-8"))
            out.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
