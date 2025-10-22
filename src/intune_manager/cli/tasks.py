from __future__ import annotations

import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _run(command: list[str]) -> None:
    """Execute a command and exit with its return code."""
    result = subprocess.run(command, cwd=PROJECT_ROOT, check=False)
    raise SystemExit(result.returncode)


def run_app() -> None:
    _run([sys.executable, "-m", "intune_manager"])


def lint() -> None:
    _run([sys.executable, "-m", "ruff", "check", "src"])


def fmt() -> None:
    _run([sys.executable, "-m", "ruff", "format", "src"])


def typecheck() -> None:
    _run([sys.executable, "-m", "mypy", "src"])


def tests() -> None:
    _run([sys.executable, "-m", "pytest"])
