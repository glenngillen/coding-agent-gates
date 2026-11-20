"""run_pilot.run_cell retry accounting. attempt_cell (CLI, ledger, evaluator) is mocked;
records go to tmp_path. Synthetic data only (evidence_kind is forced by run_cell to real,
but nothing here is written to experiment/runs)."""

from decimal import Decimal

import run_pilot as rp
import summarize as sm

ARMS = {"agent": {"model": "claude-sonnet-5-5", "effort": "medium"},
        "arms": {"C": {"stop_hook": True}}}
TASK = {"id": "T01-lookup", "acceptance_test": "x"}
ENTRY = {"run_id": "T01-lookup__C__r1", "arm": "C", "repeat": 1, "sequence": 1, "position_in_task": 1}
UNKNOWN_JUDGE = {"ledger_entry_id": "dj1", "cost_usd": None, "reservation_usd": "1.38", "usage": None}
KNOWN_JUDGE = {"ledger_entry_id": "ej", "cost_usd": "0.003", "reservation_usd": "1.38",
               "usage": {"input_tokens": 1, "output_tokens": 10, "cache_read_input_tokens": 0,
                         "cache_creation_input_tokens": 0}}
SUCCESS = {"type": "result", "subtype": "success", "is_error": False, "total_cost_usd": 0.75,
           "duration_ms": 1000, "duration_api_ms": 500, "num_turns": 3}
EVALUATION = {"behavior": {"status": "pass"}, "structural": {"status": "pass"},
              "semantic_judge": {"status": "pass"}, "semantic_judge_calls": [KNOWN_JUDGE],
              "tampering": {"detected": False, "baseline_tests_modified": []}}


def attempt(result, ledger, dev_calls):
    return {"prepared": {"settings": {"hooks": {"Stop": []}}, "run_id": ENTRY["run_id"], "arm": "C",
                         "task_id": TASK["id"], "repeat": 1, "plan": ENTRY, "agent_config": ARMS["agent"]},
            "run": {"result": result, "timed_out": False, "exit_code": 1 if result is None else 0,
                    "attempt_s": 10.0, "started_at": None, "finished_at": None, "bad_lines": []},
            "hook_events": [{"hook_event_name": "Stop", "decision": "allow", "sensor": {"status": "pass"},
                             "semantic": {"status": "pass", "calls": dev_calls}}],
            "bad_hook_lines": 0, "evaluation": EVALUATION, "artifacts": {"transcript": "t"},
            "ledger": ledger, "settings_integrity": None}


def test_summary_includes_both_attempts_agent_and_judge_spend(tmp_path, monkeypatch):
    attempts = iter([
        attempt(None, {"agent_entry_id": "a1", "reserved_usd": "5.28", "charged_usd": "5.28",
                       "cost_known": False, "status": "failed"}, [UNKNOWN_JUDGE]),
        attempt(SUCCESS, {"agent_entry_id": "a2", "reserved_usd": "5.28", "charged_usd": "0.75",
                          "cost_known": True, "status": "finished"}, [KNOWN_JUDGE]),
    ])
    monkeypatch.setattr(rp, "attempt_cell", lambda *a, **k: next(attempts))
    monkeypatch.setattr(rp, "ROOT", tmp_path)
    monkeypatch.setattr(rp.pr, "RUNS_DIR", tmp_path / "runs")
    rp.STOP.clear()

    record = rp.run_cell(TASK, ENTRY, ARMS, "p", tmp_path / "ledger.json", env={})

    [retry] = record["infrastructure_retries"]
    assert retry["usage"]["development_judge"]["unknown_cost_held_usd"] == "1.38"
    assert retry["usage"]["evaluation_judge"]["known_cost_subtotal_usd"] == "0.003"
    spend = sm.summarize_arm([record])["spend_usd"]
    first = Decimal("5.28") + Decimal("1.38") + Decimal("0.003")   # held agent + held dev judge + eval judge
    second = Decimal("0.75") + Decimal("0.003") + Decimal("0.003")  # agent + dev judge + eval judge
    assert Decimal(spend["total_charged"]) == first + second
    assert Decimal(spend["held_for_unknown_cost"]) == Decimal("5.28") + Decimal("1.38")
    assert spend["runs_with_unknown_cost"] == 1
