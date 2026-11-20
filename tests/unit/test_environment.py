"""Smoke check that the unit tier runs in an interpreter the example supports.

Import Linter 2.16+ requires Python 3.11 or newer (pyproject.toml
``requires-python``). Running the unit suite from an older interpreter would
produce confusing failures later, so fail early and explicitly.
"""

import sys


def test_interpreter_meets_minimum_supported_version() -> None:
    assert sys.version_info[:2] >= (3, 11)
