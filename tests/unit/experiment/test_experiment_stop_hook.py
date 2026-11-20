"""Experiment Stop-hook wrapper. The sensor and judge are monkeypatched; logs go to tmp_path."""

import io
import json

import experiment_stop_hook as hook
import gates.semantic
import gates.sensor
from gates.linter_output import Edge
from gates.result import SensorResult, Status, Violation

RULE = "Controllers must not import infrastructure repositories directly"


def result(status):
    if status is Status.PASS:
        return SensorResult(status, {RULE: "KEPT"}, (), None, "a" * 64, "2.17", 0, "")
    edge = Edge("orders.controllers.orders", "orders.infrastructure.repository", (3,))
    return SensorResult(status, {RULE: "BROKEN"}, (Violation(RULE, edge),), None, "b" * 64, "2.17", 1, "")


def call(tmp_path, monkeypatch, status, extra=(), stdin=None):
    seen = {}

    def fake_sensor(root, config):
        seen["config"] = config
        return result(status)

    monkeypatch.setattr(gates.sensor, "run_sensor", fake_sensor)
    out = io.StringIO()
    raw = stdin if stdin is not None else json.dumps(
        {"session_id": "s", "hook_event_name": "Stop", "stop_hook_active": False})
    code = hook.main(["--workspace", str(tmp_path / "ws"), "--state-dir", str(tmp_path / "state"),
                      "--events", str(tmp_path / "events.jsonl"), "--run-id", "r1", *extra],
                     stdin=io.StringIO(raw), stdout=out, clock=iter(range(100)).__next__)
    events = [json.loads(line) for line in (tmp_path / "events.jsonl").read_text().splitlines()]
    return code, json.loads(out.getvalue()), events, seen


def test_violation_blocks_and_is_logged_with_the_development_contract(tmp_path, monkeypatch):
    code, payload, events, seen = call(tmp_path, monkeypatch, Status.VIOLATION)

    assert code == 0 and payload["decision"] == "block"
    assert seen["config"] == hook.DEVELOPMENT_CONTRACT
    assert events[0]["decision"] == "block"
    assert events[0]["sensor"]["status"] == "violation"
    assert events[0]["sensor"]["seconds"] == 1


def test_pass_allows_the_stop(tmp_path, monkeypatch):
    _, payload, events, _ = call(tmp_path, monkeypatch, Status.PASS)

    assert "decision" not in payload
    assert events[0]["decision"] == "allow" and "semantic" not in events[0]


def test_judge_failure_is_logged_as_provider_failed(tmp_path, monkeypatch):
    def failing_judge(structural, files, provider):
        return gates.semantic.JudgeOutcome("inconclusive", "provider unavailable: x", provider_failed=True)

    monkeypatch.setattr(gates.semantic, "judge", failing_judge)
    _, payload, events, _ = call(tmp_path, monkeypatch, Status.PASS,
                                 extra=("--semantic", "--ledger", str(tmp_path / "ledger.json")))

    assert "decision" not in payload
    assert events[0]["semantic"]["provider_failed"] is True


def test_bad_arguments_never_block(tmp_path):
    out = io.StringIO()

    assert hook.main(["--bogus"], stdin=io.StringIO("{}"), stdout=out) == 0
    assert "UNRESOLVED" in json.loads(out.getvalue())["systemMessage"]


def ignored_only(status_unused=None):
    edge = Edge("orders.controllers.reports", "orders.infrastructure.repository")
    return SensorResult(Status.VIOLATION, {RULE: "KEPT"}, (Violation(RULE, edge, "ignored"),), None,
                        "c" * 64, "2.17", 0, "")


def test_v2_options_use_the_given_contract_and_accept_only_reviewed_exceptions(tmp_path, monkeypatch):
    reviewed = tmp_path / "reviewed.json"
    reviewed.write_text(json.dumps({"schema": "coding-agent-gates/reviewed-exceptions/v1", "exceptions": {
        RULE: ["orders.controllers.reports -> orders.infrastructure.repository"]}}))
    contract = tmp_path / "v2.importlinter"
    seen = {}

    def fake_sensor(root, config):
        seen["config"] = config
        return ignored_only()

    monkeypatch.setattr(gates.sensor, "run_sensor", fake_sensor)
    out = io.StringIO()
    raw = json.dumps({"session_id": "s", "hook_event_name": "Stop", "stop_hook_active": False})
    hook.main(["--workspace", str(tmp_path / "ws"), "--state-dir", str(tmp_path / "state"),
               "--events", str(tmp_path / "events.jsonl"), "--run-id", "r1",
               "--contract", str(contract), "--reviewed-exceptions", str(reviewed)],
              stdin=io.StringIO(raw), stdout=out, clock=iter(range(100)).__next__)
    event = json.loads((tmp_path / "events.jsonl").read_text())

    assert seen["config"] == contract
    assert event["sensor"]["status"] == "pass" and event["sensor"]["raw_status"] == "violation"
    assert event["decision"] == "allow"


def test_without_v2_options_an_ignored_import_still_blocks(tmp_path, monkeypatch):
    monkeypatch.setattr(gates.sensor, "run_sensor", lambda root, config: ignored_only())
    out = io.StringIO()
    raw = json.dumps({"session_id": "s", "hook_event_name": "Stop", "stop_hook_active": False})
    hook.main(["--workspace", str(tmp_path / "ws"), "--state-dir", str(tmp_path / "state"),
               "--events", str(tmp_path / "events.jsonl"), "--run-id", "r1"],
              stdin=io.StringIO(raw), stdout=out, clock=iter(range(100)).__next__)

    assert json.loads(out.getvalue())["decision"] == "block"
    assert "raw_status" not in json.loads((tmp_path / "events.jsonl").read_text())["sensor"]
