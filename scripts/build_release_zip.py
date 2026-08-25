#!/usr/bin/env python3
"""Build the release ZIP for the humanizer-ru skill package."""

from __future__ import annotations

import argparse
import zipfile
from pathlib import Path


SKILL_REL = Path("skills") / "humanizer-ru"
BAD_NAMES = {".DS_Store", "__pycache__"}
BAD_SUFFIXES = {".pyc"}


def build_release_zip(repo_root: Path, output: Path) -> None:
    skill_source = repo_root / SKILL_REL
    if not skill_source.is_dir():
        raise FileNotFoundError(f"missing skill source: {skill_source}")

    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(skill_source.rglob("*")):
            if path.is_dir():
                continue
            rel = path.relative_to(skill_source.parent)
            if any(part in BAD_NAMES for part in rel.parts) or path.suffix in BAD_SUFFIXES:
                continue
            archive.write(path, rel.as_posix())


def main() -> int:
    parser = argparse.ArgumentParser(description="Build humanizer-ru.zip for a GitHub Release.")
    parser.add_argument(
        "--output",
        default="dist/humanizer-ru.zip",
        help="Output ZIP path. Default: dist/humanizer-ru.zip",
    )
    parser.add_argument("repo_root", nargs="?", default=".", help="Repository root.")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).expanduser().resolve()
    output = Path(args.output).expanduser()
    if not output.is_absolute():
        output = repo_root / output

    try:
        build_release_zip(repo_root, output)
    except OSError as exc:
        print(f"ERROR: {exc}")
        print("RESULT: FAIL build-release-zip")
        return 1

    print(f"RELEASE_ZIP: {output}")
    print("RESULT: PASS build-release-zip")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
