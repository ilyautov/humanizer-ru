#!/usr/bin/env python3
"""Гейт чистоты для CI: балл сканера по списку файлов против порога.

Основа GitHub Action в корне репозитория (action.yml), годится и локально:

    python scripts/scan_gate.py --files "docs/**/*.md README.md" --min-score 60
    python scripts/scan_gate.py --files "*.md" --genre academic

Маски раскрываются относительно текущей папки, ** обходит подпапки. Файл с
баллом ниже порога валит запуск (exit 1); пустые файлы пропускаются.
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
    from humanizer_metrics import analyze, cleanliness_score
    from humanizer_metrics.markers import GENRES
except ImportError as exc:
    print(f"[ошибка] не хватает зависимостей сканера ({exc.name}).\n"
          "Поставьте один раз: pip install razdel pymorphy3", file=sys.stderr)
    raise SystemExit(2)


def expand(masks: list[str]) -> list[Path]:
    files: list[Path] = []
    seen: set[Path] = set()
    for mask in masks:
        found = [Path(mask)] if Path(mask).is_file() else sorted(Path().glob(mask))
        for p in found:
            if p.is_file() and p.resolve() not in seen and "__pycache__" not in p.parts:
                seen.add(p.resolve())
                files.append(p)
    return files


def main() -> int:
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
    for p in files:
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as exc:
            print(f"[гейт] пропущен {p}: {exc}")
            continue
        if not text.strip():
            continue
        rep = analyze(text)
        sc = cleanliness_score(rep, args.genre)
        rows.append((sc.score, sc.band, rep.rhythm.words, p))

    if not rows:
        print("[гейт] все файлы пустые, проверять нечего")
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
