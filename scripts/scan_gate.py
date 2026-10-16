#!/usr/bin/env python3
"""Гейт чистоты для CI: балл сканера по списку файлов против порога.

Основа GitHub Action в корне репозитория (action.yml), годится и локально:

    python scripts/scan_gate.py --files "docs/**/*.md README.md" --min-score 60
    python scripts/scan_gate.py --files "*.md" --genre academic

Маски раскрываются относительно текущей папки, ** обходит подпапки, но не
заходит в служебные папки (EXCLUDED_DIRS: node_modules, .venv, vendor, dist и
т. п.). Файл с баллом ниже порога валит запуск (exit 1). Пустые файлы, файлы не
в UTF-8 и тексты не на русском (доля кириллицы ниже 0,3) пропускаются с
пометкой. Файл, который не удалось прочитать, даёт exit 2.
В GitHub Actions пишет минимальный балл в GITHUB_OUTPUT (score) и таблицу в
GITHUB_STEP_SUMMARY.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "skills" / "humanizer-ru" / "scripts"))

try:
    from humanizer_metrics import scan_report
    from humanizer_metrics.markers import GENRES
except ImportError as exc:
    print(f"[ошибка] не хватает зависимостей сканера ({exc.name}).\n"
          "Поставьте один раз: pip install -r requirements.txt", file=sys.stderr)
    raise SystemExit(2)

# Папки, куда маска не заходит: зависимости, окружения и сборка не текст автора.
# Файл, названный явно (не маской), проверяется всегда.
EXCLUDED_DIRS = frozenset({"node_modules", ".venv", "venv", "vendor", "dist", "build",
                           ".git", "__pycache__"})
SKIPPED_NON_RUSSIAN = "skipped: не русский текст"


def expand(masks: list[str]) -> list[Path]:
    files: list[Path] = []
    seen: set[Path] = set()
    for mask in masks:
        if Path(mask).is_file():
            found = [Path(mask)]
        else:
            found = [p for p in sorted(Path().glob(mask)) if not EXCLUDED_DIRS & set(p.parts)]
        for p in found:
            if p.is_file() and p.resolve() not in seen:
                seen.add(p.resolve())
                files.append(p)
    return files


def utf8_console() -> None:
    """Таблица с ✓ и ✗ в консоли Windows (cp1251) падала с UnicodeEncodeError."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def main() -> int:
    utf8_console()
    ap = argparse.ArgumentParser(description="Гейт чистоты humanizer-ru")
    ap.add_argument("--files", required=True,
                    help="файлы или glob-маски через пробел или перенос строки")
    ap.add_argument("--genre", choices=GENRES, default="marketing")
    ap.add_argument("--min-score", type=int, default=60, help="порог, ниже которого exit 1")
    args = ap.parse_args()

    files = expand(args.files.split())
    if not files:
        print(f"[гейт] по маскам {args.files!r} файлов не нашлось, проверять нечего")
        _output("score", "")
        return 0

    rows: list[tuple[int, str, int, Path]] = []
    unreadable = 0
    for p in files:
        try:
            text = p.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            print(f"[гейт] пропущен {p}: файл не в кодировке UTF-8")
            continue
        except OSError as exc:
            print(f"[гейт] ✗ не удалось прочитать {p}: {exc.strerror or exc}", file=sys.stderr)
            unreadable += 1
            continue
        if not text.strip():
            continue
        sr = scan_report(text, args.genre)
        if sr.non_russian:
            print(f"[гейт] {p}: {SKIPPED_NON_RUSSIAN}")
            continue
        rows.append((sr.score.score, sr.score.band, sr.report.rhythm.words, p))

    if unreadable:
        print(f"[гейт] ✗ не прочитано файлов: {unreadable}, балл не считается", file=sys.stderr)
        _output("score", "")
        return 2
    if not rows:
        print("[гейт] русских непустых файлов нет, проверять нечего")
        _output("score", "")
        return 0

    worst = min(r[0] for r in rows)
    print(f"[гейт] жанр {args.genre}, порог {args.min_score}, файлов {len(rows)}")
    for score, band, words, p in rows:
        mark = "✗" if score < args.min_score else "✓"
        print(f"  {mark} {score:3d}/100  {band:7}  {words:5d} слов  {p}")
    _output("score", str(worst))
    _summary(rows, args.genre, args.min_score, worst)
    if worst < args.min_score:
        print(f"[гейт] ✗ минимальный балл {worst} ниже порога {args.min_score}")
        return 1
    print(f"[гейт] ✓ минимальный балл {worst}, порог {args.min_score} выдержан")
    return 0


def _output(key: str, value: str) -> None:
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(f"{key}={value}\n")


def _summary(rows, genre: str, threshold: int, worst: int) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    verdict = "порог выдержан" if worst >= threshold else "ниже порога"
    lines = [f"## humanizer-ru: минимальный балл {worst}/100, {verdict}",
             f"Жанр `{genre}`, порог {threshold}. Балл это плотность оборотов машинной манеры, "
             "не вердикт об авторстве.", "",
             "| Балл | Полоса | Слов | Файл |", "|---:|---|---:|---|"]
    lines += [f"| {'**' if s < threshold else ''}{s}{'**' if s < threshold else ''} | {b} | {w} | `{p}` |"
              for s, b, w, p in rows]
    with open(path, "a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
