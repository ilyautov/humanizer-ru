#!/usr/bin/env python3
"""Сборка дерева плагина для каталога Claude (ветка directory).

Каталог проверяет весь отслеживаемый корень ветки: сайт, расширение, замеры и
CI попадают в разбор ревьюера, хотя пользователю не приезжают. Поэтому в ветку
directory идёт только то, что нужно плагину. Источник правды остаётся в main,
в directory руками не правят: её обновляет .github/workflows/directory.yml по
релизу.

Запуск:
  python scripts/build_directory.py ПАПКА     # собрать дерево в пустую папку
  python scripts/build_directory.py --check   # собрать во временную и проверить
"""
from __future__ import annotations

import argparse
import json
import posixpath
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BLOB = "https://github.com/ilyautov/humanizer-ru/blob/main/"
RAW = "https://raw.githubusercontent.com/ilyautov/humanizer-ru/main/"
PREFIXES = ("commands/", "skills/humanizer-ru/")
FILES = (".claude-plugin/plugin.json", "README.md", "README.en.md",
         "LICENSE", "TERMS.md", "PRIVACY_POLICY.md")
DOCS = ("README.md", "README.en.md", "TERMS.md", "PRIVACY_POLICY.md")
LINK_RE = re.compile(r"(\]\()([^)\s]+)(\))|(\bsrc=\")([^\"]+)(\")")
ICON_LIMIT = 1  # единственный двоичный файл дерева: иконка карточки


def listing() -> list[str]:
    tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, text=True, encoding="utf-8",
                             capture_output=True, check=True).stdout.splitlines()
    manifest = json.loads((ROOT / FILES[0]).read_text(encoding="utf-8"))
    icon = posixpath.normpath(manifest["icon"])
    return sorted(p for p in tracked if p in FILES or p == icon or p.startswith(PREFIXES))


def rewrite_links(text: str, files: set[str]) -> str:
    """Ссылка на файл вне дерева ведёт в main на GitHub, иначе она будет битой."""
    def fix(m: re.Match) -> str:
        before, target, after = (m.group(1), m.group(2), m.group(3)) if m.group(1) else (m.group(4), m.group(5), m.group(6))
        path = target.split("#")[0]
        if not path or re.match(r"[a-z][a-z0-9+.-]*:", target, re.I) or path in files:
            return m.group(0)
        return f"{before}{(RAW if before.startswith('src') else BLOB) + target}{after}"
    return LINK_RE.sub(fix, text)


def build(out: Path) -> list[str]:
    files = listing()
    known = set(files)
    for rel in files:
        dest = out / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if rel in DOCS:
            text = (ROOT / rel).read_text(encoding="utf-8")
            dest.write_text(rewrite_links(text, known), encoding="utf-8")
        else:
            dest.write_bytes((ROOT / rel).read_bytes())
    return files


def verify(out: Path, files: list[str]) -> list[str]:
    problems = [f"нет файла: {rel}" for rel in FILES if rel not in files]
    if not any(p.startswith("commands/") for p in files):
        problems.append("нет команд")
    if "skills/humanizer-ru/SKILL.md" not in files:
        problems.append("нет SKILL.md")
    binary = [p for p in files if b"\0" in (out / p).read_bytes()]
    if len(binary) > ICON_LIMIT:
        problems.append(f"лишние двоичные файлы: {', '.join(binary)}")
    for rel in DOCS:
        for m in LINK_RE.finditer((out / rel).read_text(encoding="utf-8")):
            target = (m.group(2) or m.group(5)).split("#")[0]
            if target and not re.match(r"[a-z][a-z0-9+.-]*:", target, re.I) and target not in files:
                problems.append(f"{rel}: битая ссылка {target}")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("out", nargs="?", type=Path, help="пустая папка для дерева")
    ap.add_argument("--check", action="store_true", help="собрать во временную папку и проверить")
    args = ap.parse_args()
    if args.check == bool(args.out):
        ap.error("укажите либо папку, либо --check")
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) if args.check else args.out
        if not args.check and out.exists() and any(out.iterdir()):
            ap.error(f"папка не пуста: {out}")
        files = build(out)
        problems = verify(out, files)
    for p in problems:
        print(f"[directory] ✗ {p}")
    if problems:
        return 1
    print(f"[directory] ✓ дерево плагина в порядке, файлов: {len(files)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
