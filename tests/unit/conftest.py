"""Shared unit-test setup.

pyproject.toml points pytest's ``--basetemp`` at ``.tmp/pytest`` (gitignored) so
temporary directories stay inside this example; pytest does not create the
parent, so do it here before any ``tmp_path`` is requested.
"""

from pathlib import Path

(Path(__file__).resolve().parents[2] / ".tmp").mkdir(exist_ok=True)
