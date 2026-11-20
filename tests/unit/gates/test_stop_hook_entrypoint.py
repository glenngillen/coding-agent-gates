"""The Claude Code hook entrypoint must never fail in a way Claude Code would retry.

Exit code 2 is a *blocking* decision for a Stop hook, and a crash would fall to
the settings' ``onFailure`` policy. Either would happen outside the adapter's
repair budget. These tests drive ``main`` with injected streams, sensor and
adapter loader; nothing runs a subprocess or touches project files.
"""

import importlib.util
import io
import json
from pathlib import Path

import pytest

from gates.result import SensorResult, Status
from gates.stop_hook import FileStateStore

ROOT = Path(__file__).resolve().parents[3]
STOP = json.dumps({"session_id": "s1", "hook_event_name": "Stop", "stop_hook_active": False})


def load_entrypoint():
    spec = importlib.util.spec_from_file_location(
        "claude_stop_hook_under_test", ROOT / "integrations/claude_stop_hook.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def entry():
    return load_entrypoint()


def call(entry, argv, stdin=STOP, **kwargs):
    out, err = io.StringIO(), io.StringIO()
    code = entry.main(argv, stdin=io.StringIO(stdin), stdout=out, stderr=err, **kwargs)
    payload = json.loads(out.getvalue()) if out.getvalue().strip() else None
    return code, payload, err.getvalue()


def violating():
    return SensorResult(Status.VIOLATION, {}, (), None, "bb" * 32, "2.17", 1, "raw")


def test_module_import_does_not_import_the_adapter(entry):
    # Importing gates at module level would turn an import failure into a crash
    # that the entrypoint could not translate.
    assert not hasattr(entry, "handle_event")


def test_invalid_arguments_report_unresolved_instead_of_exit_2(entry):
    code, payload, _ = call(entry, ["--max-repairs", "0"])

    assert code == 0
    assert "decision" not in payload
    assert "UNRESOLVED" in payload["systemMessage"]


def test_adapter_import_failure_reports_unresolved(entry):
    def broken_loader():
        raise ImportError("No module named 'gates'")

    code, payload, _ = call(entry, [], load_adapter=broken_loader)

    assert code == 0
    assert "decision" not in payload
    assert "UNRESOLVED" in payload["systemMessage"]
    assert "No module named" in payload["systemMessage"]


def test_unexpected_adapter_crash_reports_unresolved(entry):
    def loader():
        def handle_event(*_args, **_kwargs):
            raise RuntimeError("kaboom")
        return handle_event, FileStateStore, 3, lambda root: violating()

    code, payload, _ = call(entry, [], load_adapter=loader)

    assert (code, "decision" in payload) == (0, False)
    assert "UNRESOLVED" in payload["systemMessage"] and "kaboom" in payload["systemMessage"]


def test_unwritable_state_directory_never_blocks(entry, tmp_path):
    blocker = tmp_path / "state"
    blocker.write_text("occupied by a file")

    for _ in range(5):
        code, payload, _ = call(entry, ["--max-repairs", "3"], state_dir=blocker,
                                sensor=lambda root: violating())
        assert code == 0
        assert "decision" not in payload
        assert "UNRESOLVED" in payload["systemMessage"]


def test_normal_violation_still_blocks(entry, tmp_path):
    code, payload, _ = call(entry, [], state_dir=tmp_path / "state",
                            sensor=lambda root: violating())

    assert code == 0
    assert payload["decision"] == "block"


def test_reset_failure_exits_nonzero_for_the_human_running_it(entry, tmp_path):
    blocker = tmp_path / "state"
    blocker.mkdir()
    # reset_all on a path that is a directory works; make iterdir fail instead.
    class Store(FileStateStore):
        def reset_all(self):
            raise PermissionError(13, "Permission denied")

    def loader():
        from gates.stop_hook import DEFAULT_MAX_REPAIRS, handle_event
        return handle_event, Store, DEFAULT_MAX_REPAIRS, lambda root: violating()

    code, _, err = call(entry, ["--reset"], state_dir=blocker, load_adapter=loader)

    assert code == 1
    assert "Permission denied" in err
