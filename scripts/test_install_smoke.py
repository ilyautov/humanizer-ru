#!/usr/bin/env python3
"""Регресс-тест install-smoke."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SMOKE = ROOT / "scripts" / "install_smoke.py"


result = subprocess.run(
    [sys.executable, str(SMOKE), str(ROOT)],
    text=True,
    capture_output=True,
)

assert result.returncode == 0, result.stdout + result.stderr
assert "RESULT: PASS install-smoke" in result.stdout, result.stdout

print("OK — install-smoke прошёл.")
