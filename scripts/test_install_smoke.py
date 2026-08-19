#!/usr/bin/env python3
"""Регресс-тест install-smoke."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
BUILD_ZIP = ROOT / "scripts" / "build_release_zip.py"
SMOKE = ROOT / "scripts" / "install_smoke.py"


with tempfile.TemporaryDirectory(prefix="humanizer-ru-test-install-smoke.") as tmp:
    zip_path = Path(tmp) / "humanizer-ru.zip"

    build = subprocess.run(
        [sys.executable, str(BUILD_ZIP), "--output", str(zip_path), str(ROOT)],
        text=True,
        capture_output=True,
    )
    assert build.returncode == 0, build.stdout + build.stderr
    assert "RESULT: PASS build-release-zip" in build.stdout, build.stdout

    release_smoke = subprocess.run(
        [sys.executable, str(SMOKE), str(ROOT), "--zip", str(zip_path)],
        text=True,
        capture_output=True,
    )
    assert release_smoke.returncode == 0, release_smoke.stdout + release_smoke.stderr
    assert "RESULT: PASS install-smoke" in release_smoke.stdout, release_smoke.stdout

source_smoke = subprocess.run(
    [sys.executable, str(SMOKE), str(ROOT)],
    text=True,
    capture_output=True,
)

assert source_smoke.returncode == 0, source_smoke.stdout + source_smoke.stderr
assert "RESULT: PASS install-smoke" in source_smoke.stdout, source_smoke.stdout

print("OK - install-smoke passed.")
