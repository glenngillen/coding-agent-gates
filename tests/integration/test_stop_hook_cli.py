"""The real Stop-hook entrypoint, fed the hook-protocol fixtures on stdin."""

import json

import pytest
from integration_helpers import EXAMPLE, PYTHON, make_copy, run

pytestmark = pytest.mark.integration

FIXTURES = EXAMPLE / "fixtures" / "hook-protocol"


def hook(root, fixture, *args):
    proc = run([PYTHON, root / "integrations" / "claude_stop_hook.py", *args], root,
               input=(FIXTURES / fixture).read_text())
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout) if proc.stdout.strip() else None


def test_violation_blocks_until_the_budget_runs_out_then_reports_unresolved(tmp_path):
    root = make_copy(tmp_path, "fixtures/direct_import")

    for attempt in (1, 2):
        payload = hook(root, "stop.json" if attempt == 1 else "stop-continuing.json",
                       "--max-repairs", "2")
        assert payload["decision"] == "block"
        assert "orders.controllers.orders -> orders.infrastructure.repository" in payload["reason"]
        assert f"repair request {attempt} of 2" in payload["reason"]

    final = hook(root, "stop-continuing.json", "--max-repairs", "2")
    assert "decision" not in final
    assert "UNRESOLVED" in final["systemMessage"]
    state = json.loads(next((root / ".claude" / "architecture-gate").glob("*.json")).read_text())
    assert state["outcome"] == "unresolved"


def test_new_prompt_resets_the_budget(tmp_path):
    root = make_copy(tmp_path, "fixtures/direct_import")
    for _ in range(3):
        hook(root, "stop.json", "--max-repairs", "2")

    assert hook(root, "user-prompt-submit.json") is None
    assert hook(root, "stop.json", "--max-repairs", "2")["decision"] == "block"


def test_baseline_allows_the_stop(tmp_path):
    payload = hook(make_copy(tmp_path), "stop.json")

    assert "decision" not in payload
    assert payload["systemMessage"].startswith("ARCHITECTURE CHECK PASSED")


def test_checker_error_blocks_rather_than_passing(tmp_path):
    payload = hook(make_copy(tmp_path, "fixtures/syntax_error"), "stop.json")

    assert payload["decision"] == "block"
    assert "ARCHITECTURE CHECK ERROR" in payload["reason"]


def test_reset_removes_session_state(tmp_path):
    root = make_copy(tmp_path, "fixtures/direct_import")
    hook(root, "stop.json")

    proc = run([PYTHON, root / "integrations" / "claude_stop_hook.py", "--reset"], root)

    assert "Removed 1 session state file" in proc.stdout
    assert list((root / ".claude" / "architecture-gate").glob("*.json")) == []
