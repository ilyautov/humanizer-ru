#!/usr/bin/env python3
"""Сборка Chrome-расширения из extension/ и браузерного сканера сайта.

Расширение не держит своей копии правил: движок docs/scan.js и правила
docs/scan-rules.js (экспорт из Python, гейт export_web_rules.py --check)
копируются в extension/vendor/. Копии закоммичены, чтобы папку можно было
загрузить в Chrome как есть, а этот скрипт с --check следит, что они не
отстали от docs/: третий расходящийся сканер нам не нужен.

Запуск:
  python scripts/build_extension.py            # обновить vendor/, проверить манифест
  python scripts/build_extension.py --check    # только сравнить, ничего не писать (CI)
  python scripts/build_extension.py --zip dist/humanizer-ru-extension.zip
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXT = ROOT / "extension"
VENDOR = EXT / "vendor"
SOURCES = {"scan.js": ROOT / "docs" / "scan.js", "scan-rules.js": ROOT / "docs" / "scan-rules.js"}
PACKAGE = ROOT / "package.json"
MANIFEST = EXT / "manifest.json"
# Что едет в архив для Web Store: всё из extension/, кроме служебного.
SKIP = {"README.md", ".DS_Store"}


def check_manifest() -> list[str]:
    errors: list[str] = []
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    pkg_version = json.loads(PACKAGE.read_text(encoding="utf-8"))["version"]
    if m.get("version") != pkg_version:
        errors.append(f"manifest.json version {m.get('version')} != package.json {pkg_version}")
    if m.get("manifest_version") != 3:
        errors.append("manifest_version должен быть 3")
    if "default_locale" in m and not (EXT / "_locales").exists():
        errors.append("default_locale задан, а _locales/ нет: Chrome откажется грузить")
    for size, rel in (m.get("icons") or {}).items():
        p = EXT / rel
        if not p.exists():
            errors.append(f"иконка {rel} не найдена")
        elif p.read_bytes()[:8] != b"\x89PNG\r\n\x1a\n":
            errors.append(f"иконка {rel} не PNG (Chrome не принимает SVG в манифесте)")
    for perm in m.get("permissions", []):
        if perm not in {"contextMenus", "storage"}:
            errors.append(f"лишнее разрешение {perm}: расширение обещает не ходить в сеть и не читать страницы")
    if m.get("host_permissions"):
        errors.append("host_permissions не пустой: расширению не нужен доступ к сайтам")
    desc = m.get("description", "")
    if len(desc) > 132:
        errors.append(f"description {len(desc)} символов, Web Store принимает до 132")
    if "—" in desc or "—" in m.get("name", ""):
        errors.append("длинное тире в манифесте")
    return errors


def sync(check_only: bool) -> tuple[list[str], list[str]]:
    stale: list[str] = []
    written: list[str] = []
    VENDOR.mkdir(exist_ok=True)
    for name, src in SOURCES.items():
        dst = VENDOR / name
        fresh = src.read_text(encoding="utf-8")
        current = dst.read_text(encoding="utf-8") if dst.exists() else ""
        if fresh == current:
            continue
        if check_only:
            stale.append(f"extension/vendor/{name} отстаёт от docs/{name}")
        else:
            dst.write_text(fresh, encoding="utf-8")
            written.append(f"extension/vendor/{name}")
    return stale, written


def build_zip(out: Path) -> int:
    out.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(EXT.rglob("*")):
            if p.is_dir() or p.name in SKIP or "__pycache__" in p.parts:
                continue
            z.write(p, p.relative_to(EXT).as_posix())
            n += 1
    return n


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="не писать, только проверить (CI)")
    ap.add_argument("--zip", type=Path, help="собрать архив для Web Store по этому пути")
    args = ap.parse_args()

    stale, written = sync(args.check)
    errors = check_manifest() + stale
    for w in written:
        print(f"[extension] обновлён {w}")
    for e in errors:
        print(f"[extension] ✗ {e}")
    if errors:
        print("[extension] исправьте и запустите python scripts/build_extension.py")
        return 1
    if args.zip:
        n = build_zip(args.zip)
        print(f"[extension] ✓ {args.zip.relative_to(ROOT) if args.zip.is_absolute() else args.zip}: {n} файлов")
    print("[extension] ✓ vendor/ совпадает с docs/, манифест в порядке")
    return 0


if __name__ == "__main__":
    sys.exit(main())
