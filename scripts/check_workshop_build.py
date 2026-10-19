#!/usr/bin/env python3
"""Паритет docs/workshop.ts и docs/workshop.js.

Главная страница грузит docs/workshop.js, а правят docs/workshop.ts. Если
поправить исходник и забыть пересобрать, на сайт уедет старое поведение, и
никто этого не заметит. Скрипт компилирует workshop.ts тем же tsc и тем же
docs/tsconfig.json во временную папку и сравнивает результат с закоммиченным
workshop.js байт в байт.

Нужен Node и TypeScript из docs/package.json (`npm ci` в docs/). Без
node_modules скрипт сам запускает `npm ci` во временной копии.

Запуск:
  python scripts/check_workshop_build.py           # проверить (CI)
  python scripts/check_workshop_build.py --write   # пересобрать docs/workshop.js
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
SRC = DOCS / "workshop.ts"
OUT = DOCS / "workshop.js"


def compile_to(tmp: Path) -> Path:
    """Собирает workshop.ts во временной копии docs-конфига, возвращает путь к js."""
    for name in ("workshop.ts", "tsconfig.json", "package.json", "package-lock.json"):
        shutil.copy2(DOCS / name, tmp / name)
    local_modules = DOCS / "node_modules"
    if (local_modules / "typescript").exists():
        (tmp / "node_modules").symlink_to(local_modules, target_is_directory=True)
    else:
        subprocess.run(["npm", "ci", "--no-audit", "--no-fund", "--silent"], cwd=tmp, check=True)
    tsc = tmp / "node_modules" / ".bin" / "tsc"
    subprocess.run([str(tsc), "-p", "tsconfig.json"], cwd=tmp, check=True)
    out_name = json.loads((DOCS / "tsconfig.json").read_text(encoding="utf-8"))["compilerOptions"]["outFile"]
    return tmp / out_name


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write", action="store_true", help="перезаписать docs/workshop.js свежей сборкой")
    args = ap.parse_args()
    with tempfile.TemporaryDirectory() as d:
        try:
            built = compile_to(Path(d)).read_text(encoding="utf-8")
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print(f"[workshop] ✗ tsc не собрал workshop.ts: {e}")
            return 1
    if args.write:
        OUT.write_text(built, encoding="utf-8")
        print("[workshop] ✓ docs/workshop.js пересобран из workshop.ts")
        return 0
    if built != OUT.read_text(encoding="utf-8"):
        print("[workshop] ✗ docs/workshop.js не совпадает со сборкой docs/workshop.ts.")
        print("[workshop]   пересоберите: python scripts/check_workshop_build.py --write")
        return 1
    print("[workshop] ✓ docs/workshop.js совпадает со сборкой workshop.ts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
