#!/usr/bin/env python3
"""Plan, freeze and run the version 5 study (experiment/protocol-v5.md).

    .venv/bin/python experiment/tools/run_study_v5.py freeze --write|--check
    .venv/bin/python experiment/tools/run_study_v5.py plan --study NAME
    .venv/bin/python experiment/tools/run_study_v5.py run --study NAME

Version 5 is version 3's runner with a different study file
(``experiment/v5/study.json``): an older agent model next to a current one, and
conditions that put pressure on a stated rule. Two things are added to what a
condition can change, both declared in the study file:

- ``request_suffix``: text appended to every step's request;
- ``extra_files``: files added to the workspace's last history commit.

Everything else is the frozen version 2 and version 3 machinery.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
TOOLS = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "experiment"), str(TOOLS)]

import run_study_v3 as v3  # noqa: E402
from evaluator import evaluate as ev  # noqa: E402

V5 = ROOT / "experiment" / "v5"
STUDY_PATH = V5 / "study.json"
MANIFEST = V5 / "frozen-manifest.json"
FROZEN_PATTERNS = (
    "experiment/protocol-v5.md",
    "experiment/v5/study.json",
    "experiment/v5/instructions/*.md",
    "experiment/v5/nested-controllers-CLAUDE.md",
    "experiment/tools/run_study_v5.py",
)
V3_MANIFEST = v3.MANIFEST
V3_PATTERNS = v3.FROZEN_PATTERNS
_v3_history_for = v3.history_for
_v3_run_session = v3.run_session


def check_frozen() -> None:
    """Versions 2 and 3 (the machinery this study reuses) and version 5's own inputs."""
    ev.check_frozen(ev.load_manifest(v3.ev2.MANIFEST), v3.ev2.current_frozen_hashes())
    ev.check_frozen(ev.load_manifest(V3_MANIFEST), ev.file_hashes(ROOT, V3_PATTERNS))
    ev.check_frozen(ev.load_manifest(MANIFEST), ev.file_hashes(ROOT, FROZEN_PATTERNS))


def extra_files_for(instruction_file: str, study: dict[str, Any]) -> dict[str, str]:
    """Each condition has its own instruction file path, so the path identifies the condition."""
    matches = [g for g in study["guidance"].values() if g["instruction_file"] == instruction_file]
    if len(matches) != 1:
        raise v3.pv.NotRunnable(f"{instruction_file} does not identify exactly one condition")
    return dict(matches[0].get("extra_files") or {})


def history_for(instruction_file: str, root: Path = ROOT) -> dict[str, Any]:
    history = _v3_history_for(instruction_file, root)
    for path, source in extra_files_for(instruction_file, v3.load_study(STUDY_PATH)).items():
        history["commits"][-1]["paths"].append({"path": path, "source": source})
    return history


def scenario_for(scenario: dict[str, Any], entry: dict[str, Any], study: dict[str, Any]) -> dict[str, Any]:
    """The scenario with the condition's request suffix (if any) appended to every step."""
    suffix = study["guidance"][entry["guidance"]].get("request_suffix") or ""
    out = copy.deepcopy(scenario)
    for step in out["steps"]:
        step["request"] += suffix
    return out


def run_session(scenario: dict, entry: dict, study: dict, study_name: str, ledger: Path, env: dict) -> dict[str, Any]:
    return _v3_run_session(scenario_for(scenario, entry, study), entry, study, study_name, ledger, env)


def configure() -> None:
    v3.STUDY_PATH = STUDY_PATH
    v3.MANIFEST = MANIFEST
    v3.FROZEN_PATTERNS = FROZEN_PATTERNS
    v3.check_frozen = check_frozen
    v3.load_study.__defaults__ = (STUDY_PATH,)
    v3.history_for = history_for
    v3.run_session = run_session


def main() -> int:
    configure()
    return v3.main()


if __name__ == "__main__":
    sys.exit(main())
