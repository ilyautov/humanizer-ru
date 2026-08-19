#!/usr/bin/env python3
"""Install-smoke для humanizer-ru.

Проверяет не исходную папку в репозитории, а установочную поверхность:
чистую копию skill-пакета, ZIP-архив релизного вида и запуск сканера из
установленной копии.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from build_release_zip import build_release_zip


SKILL_REL = Path("skills") / "humanizer-ru"
REQUIRED_FILES = (
    "SKILL.md",
    "agents/openai.yaml",
    "references/catalog.md",
    "scripts/scan.py",
    "scripts/humanizer_metrics/__init__.py",
    "scripts/humanizer_metrics/markers.py",
    "scripts/humanizer_metrics/score.py",
    "scripts/humanizer_metrics/burstiness.py",
    "scripts/humanizer_metrics/structure.py",
    "scripts/humanizer_metrics/morphology.py",
)
BAD_NAMES = {".DS_Store", "__pycache__"}
BAD_SUFFIXES = {".pyc"}


def copytree_clean(source: Path, destination: Path) -> None:
    shutil.copytree(
        source,
        destination,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"),
    )


def generated_files(root: Path) -> list[str]:
    bad: list[str] = []
    for path in root.rglob("*"):
        if path.name in BAD_NAMES or path.suffix in BAD_SUFFIXES:
            bad.append(str(path.relative_to(root)))
    return bad


def validate_skill_surface(skill_root: Path) -> list[str]:
    errors: list[str] = []
    for rel in REQUIRED_FILES:
        if not (skill_root / rel).is_file():
            errors.append(f"missing installed skill file: {rel}")
    for rel in generated_files(skill_root):
        errors.append(f"generated file in installed skill: {rel}")
    for path in skill_root.rglob("*"):
        if not path.name.isascii():
            errors.append(f"non-ASCII path in installed skill: {path.relative_to(skill_root)}")
    return errors


def run(command: list[str], *, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, input=input_text, text=True, capture_output=True)


def validate_installed_scanner(installed_skill: Path) -> list[str]:
    scanner = installed_skill / "scripts" / "scan.py"
    errors: list[str] = []

    clean = run(
        [sys.executable, str(scanner), "-", "--json"],
        input_text="Я попробовал три раза. Не вышло. Потом понял: забыл про кэш.",
    )
    if clean.returncode != 0:
        errors.append(f"installed scanner clean-text exit {clean.returncode}: {clean.stderr or clean.stdout}")
    else:
        try:
            payload = json.loads(clean.stdout)
        except json.JSONDecodeError as exc:
            errors.append(f"installed scanner did not return JSON: {exc}")
        else:
            if "score" not in payload or "hard_ban_count" not in payload:
                errors.append("installed scanner JSON missing score or hard_ban_count")

    banned = run(
        [sys.executable, str(scanner), "-"],
        input_text="В современном мире данный подход является мощным инструментом.",
    )
    if banned.returncode != 1:
        errors.append(f"installed scanner hard-ban exit {banned.returncode}, expected 1")
    if "HARD" not in banned.stdout and "бан" not in banned.stdout.lower():
        errors.append("installed scanner hard-ban output does not mention the finding")

    return errors


def validate_zip(zip_path: Path) -> list[str]:
    errors: list[str] = []
    with zipfile.ZipFile(zip_path) as archive:
        names = archive.namelist()
    required = {f"humanizer-ru/{rel}" for rel in REQUIRED_FILES}
    missing = sorted(required - set(names))
    for rel in missing:
        errors.append(f"release zip missing file: {rel}")
    for name in names:
        parts = Path(name).parts
        if not parts or parts[0] != "humanizer-ru":
            errors.append(f"release zip has unexpected top-level path: {name}")
        if any(part in BAD_NAMES for part in parts) or Path(name).suffix in BAD_SUFFIXES:
            errors.append(f"release zip contains generated file: {name}")
        if any(not part.isascii() for part in parts):
            errors.append(f"release zip contains non-ASCII path: {name}")
    return errors


def install_smoke(repo_root: Path, keep_tmp: bool = False, zip_path: Path | None = None) -> int:
    skill_source = repo_root / SKILL_REL
    if not skill_source.is_dir():
        print(f"ERROR: missing skill source: {skill_source}")
        print("RESULT: FAIL install-smoke")
        return 2

    tmp_context = tempfile.TemporaryDirectory(prefix="humanizer-ru-install-smoke.")
    tmp_path = Path(tmp_context.name)
    try:
        install_root = tmp_path / "codex-skills"
        installed_skill = install_root / "humanizer-ru"
        install_root.mkdir(parents=True)
        copytree_clean(skill_source, installed_skill)

        if zip_path is None:
            zip_path = tmp_path / "humanizer-ru.zip"
            build_release_zip(repo_root, zip_path)
        elif not zip_path.is_file():
            print(f"ERROR: release ZIP is not a file: {zip_path}")
            print("RESULT: FAIL install-smoke")
            return 2

        errors = []
        errors.extend(validate_skill_surface(installed_skill))
        errors.extend(validate_installed_scanner(installed_skill))
        errors.extend(validate_zip(zip_path))

        if errors:
            for error in errors:
                print(f"ERROR: {error}")
            print("RESULT: FAIL install-smoke")
            return 1

        print(f"INSTALL_ROOT: {install_root}")
        print(f"RELEASE_ZIP: {zip_path}")
        print("RESULT: PASS install-smoke")
        return 0
    finally:
        if keep_tmp:
            print(f"KEPT_TMP: {tmp_path}")
        else:
            tmp_context.cleanup()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run install-smoke for humanizer-ru.")
    parser.add_argument("repo_root", nargs="?", default=".", help="Repository root to smoke-test.")
    parser.add_argument("--keep-tmp", action="store_true", help="Keep the temporary install directory.")
    parser.add_argument("--zip", help="Validate an existing release ZIP instead of building a temporary one.")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).expanduser().resolve()
    if not repo_root.is_dir():
        print(f"ERROR: repository root is not a directory: {repo_root}")
        print("RESULT: FAIL install-smoke")
        return 2
    zip_path = Path(args.zip).expanduser().resolve() if args.zip else None
    return install_smoke(repo_root, keep_tmp=args.keep_tmp, zip_path=zip_path)


if __name__ == "__main__":
    raise SystemExit(main())
