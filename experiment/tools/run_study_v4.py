#!/usr/bin/env python3
"""Plan, freeze and run the version 4 study (experiment/protocol-v4.md).

    .venv/bin/python experiment/tools/run_study_v4.py freeze --write|--check
    .venv/bin/python experiment/tools/run_study_v4.py plan --study NAME
    .venv/bin/python experiment/tools/run_study_v4.py run --study NAME

Version 4 is version 3's runner with a different study file: the guidance
levels are a lean one-line instruction file and a large generated handbook
(``experiment/v4/study.json``). Nothing else changes. This module points the
frozen version 3 module at the version 4 study and manifest, and checks all
three manifests (versions 2, 3 and 4) before any session.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOLS = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "experiment"), str(TOOLS)]

import run_study_v3 as v3  # noqa: E402
from evaluator import evaluate as ev  # noqa: E402

V4 = ROOT / "experiment" / "v4"
STUDY_PATH = V4 / "study.json"
MANIFEST = V4 / "frozen-manifest.json"
FROZEN_PATTERNS = (
    "experiment/protocol-v4.md",
    "experiment/v4/study.json",
    "experiment/v4/instructions/*.md",
    "experiment/tools/run_study_v4.py",
)
V3_MANIFEST = v3.MANIFEST
V3_PATTERNS = v3.FROZEN_PATTERNS


def check_frozen() -> None:
    """Versions 2 and 3 (the machinery this study reuses) and version 4's own inputs."""
    ev.check_frozen(ev.load_manifest(v3.ev2.MANIFEST), v3.ev2.current_frozen_hashes())
    ev.check_frozen(ev.load_manifest(V3_MANIFEST), ev.file_hashes(ROOT, V3_PATTERNS))
    ev.check_frozen(ev.load_manifest(MANIFEST), ev.file_hashes(ROOT, FROZEN_PATTERNS))


def configure() -> None:
    """Point the version 3 module at the version 4 study, manifest and frozen patterns."""
    v3.STUDY_PATH = STUDY_PATH
    v3.MANIFEST = MANIFEST
    v3.FROZEN_PATTERNS = FROZEN_PATTERNS
    v3.check_frozen = check_frozen
    v3.load_study.__defaults__ = (STUDY_PATH,)


def main() -> int:
    configure()
    if len(sys.argv) > 2 and sys.argv[1] == "freeze" and "--write" in sys.argv and not V3_MANIFEST.exists():
        print("NOT FROZEN: version 3's manifest is missing")
        return 1
    return v3.main()


if __name__ == "__main__":
    sys.exit(main())
