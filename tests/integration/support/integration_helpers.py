"""Integration tier (CI only): runs the real sensor, lint-imports, pytest, Git and
pre-commit against disposable copies of this example.

Never run as part of the unit pass (pyproject testpaths excludes this
directory). Run with:

    .venv/bin/python -m pytest tests/integration -m integration

Copies live under pytest's temporary directory; hooks are only ever installed
into those copies' own ``.git``, never into the repository that holds this
example.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

EXAMPLE = Path(__file__).resolve().parents[3]
VENV = EXAMPLE / ".venv"
PYTHON = Path(sys.executable)
SKIP_NAMES = {".venv", ".tmp", "__pycache__", ".hypothesis", ".pytest_cache", ".git", ".claude"}

(EXAMPLE / ".tmp").mkdir(exist_ok=True)


def scenarios() -> list[dict]:
    return json.loads((EXAMPLE / "fixtures" / "scenarios.json").read_text())["scenarios"]


def apply_overlay(root: Path, overlay: str | None) -> None:
    if overlay:
        shutil.copytree(EXAMPLE / overlay, root, dirs_exist_ok=True)


def make_copy(tmp_path: Path, overlay: str | None = None) -> Path:
    root = tmp_path / "example"
    shutil.copytree(EXAMPLE, root, ignore=lambda _d, names: [n for n in names if n in SKIP_NAMES])
    (root / ".venv").symlink_to(VENV, target_is_directory=True)
    apply_overlay(root, overlay)
    return root


def run(argv, cwd: Path, *, input: str | None = None, env: dict | None = None):
    return subprocess.run(
        [str(a) for a in argv], cwd=cwd, input=input, capture_output=True, text=True,
        env={**os.environ, **(env or {})}, timeout=300, check=False,
    )


def sensor_json(root: Path) -> tuple[int, dict]:
    proc = run([PYTHON, root / "integrations" / "check_architecture.py", "--json"], root)
    return proc.returncode, json.loads(proc.stdout)


