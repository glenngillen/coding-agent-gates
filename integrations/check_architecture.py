#!/usr/bin/env python3
"""Canonical architecture sensor command. Every gate placement runs this file.

    .venv/bin/python integrations/check_architecture.py [--json] [--cache-dir DIR]

Exit status: 0 pass, 1 violation, 3 checker error (the rules were NOT checked).
Run it with the example's virtual environment so the pinned lint-imports is used.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gates.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
