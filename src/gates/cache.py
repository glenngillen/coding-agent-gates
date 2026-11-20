"""Optional result cache keyed by the checked-input fingerprint.

The key is a SHA-256 over every input that can change the answer (package
source, contract configuration, tool version; see ``gates.sensor.fingerprint``),
so any edit invalidates the entry by construction. Only pass and violation
results are stored: a checker error is never cached, because its cause (a
missing tool, say) can change without the inputs changing. Corrupt or
mismatched entries are misses, never answers.
"""

from __future__ import annotations

import re
from pathlib import Path

from gates.result import SensorResult, Status

_KEY = re.compile(r"^[0-9a-f]{64}$")


class ResultCache:
    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)

    def _path(self, key: str) -> Path | None:
        return self.directory / f"{key}.json" if _KEY.match(key) else None

    def get(self, key: str) -> SensorResult | None:
        path = self._path(key)
        if path is None:
            return None
        try:
            result = SensorResult.from_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeDecodeError):
            return None
        if result.fingerprint != key or result.status is Status.CHECKER_ERROR:
            return None
        return result

    def put(self, result: SensorResult) -> None:
        if result.status is Status.CHECKER_ERROR or not result.fingerprint:
            return
        path = self._path(result.fingerprint)
        if path is None:
            return
        self.directory.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(result.to_json(), encoding="utf-8")
        tmp.replace(path)
