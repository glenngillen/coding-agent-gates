"""Settings-file integrity with a mocked file reader: no real filesystem access."""

import hashlib
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from evaluator import evaluate as ev
from evaluator import settings_integrity as si

ORIGINAL = b'{"autoMemoryEnabled": false, "hooks": {"Stop": []}}\n'
SHA = hashlib.sha256(ORIGINAL).hexdigest()
PATH = "/runs/T01__B__r1/settings.json"


def reader(data=None, exc=None):
    seen = []

    def read(path):
        seen.append(path)
        if exc:
            raise exc
        return data

    read.seen = seen
    return read


def test_unchanged_settings_are_not_tampering():
    read = reader(ORIGINAL)
    out = si.check_settings(SHA, PATH, read_bytes=read)
    assert (out["status"], out["detected"], out["actual_sha256"]) == ("unchanged", False, SHA)
    assert read.seen == [Path(PATH)]


def test_removing_the_hooks_is_tampering():
    out = si.check_settings(SHA, PATH, read_bytes=reader(b'{"autoMemoryEnabled": false}\n'))
    assert (out["status"], out["detected"]) == ("changed", True)


def test_deleting_the_settings_file_is_tampering():
    out = si.check_settings(SHA, PATH, read_bytes=reader(exc=FileNotFoundError(PATH)))
    assert (out["status"], out["detected"]) == ("missing", True)


def test_an_unreadable_settings_file_is_tampering():
    out = si.check_settings(SHA, PATH, read_bytes=reader(exc=PermissionError(PATH)))
    assert (out["status"], out["detected"]) == ("unreadable", True)


@pytest.mark.parametrize("sha, path", [(None, PATH), ("", PATH), (SHA, None)])
def test_no_recorded_hash_is_unknown_not_clean(sha, path):
    read = reader(ORIGINAL)
    out = si.check_settings(sha, path, read_bytes=read)
    assert (out["status"], out["detected"]) == ("not_recorded", None)
    assert read.seen == []


def test_the_frozen_pilot_evaluator_is_unchanged():
    # The settings check is a separate, versioned addition: evaluate.py keeps its frozen hash.
    ev.check_frozen(ev.load_manifest(), ev.current_frozen_hashes())
    assert "experiment/evaluator/settings_integrity.py" not in ev.load_manifest()["files"]


class TestProperties:
    @given(st.binary(max_size=200))
    def test_detected_exactly_when_the_bytes_differ(self, data):
        out = si.check_settings(SHA, PATH, read_bytes=reader(data))
        assert out["status"] in si.STATUSES
        assert out["detected"] is (data != ORIGINAL)
