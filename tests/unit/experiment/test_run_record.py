"""Run-record parsing and building. Pure: synthetic inputs only, labelled synthetic-test."""

import json
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

import run_record as rr

GATED = {"settings": {"hooks": {"Stop": []}}, "run_id": "T01__B__r1", "arm": "B", "task_id": "T01",
         "agent_config": {"model": "claude-sonnet-5-5", "effort": "medium"}, "plan": {"sequence": 4}}
UNGATED = {**GATED, "settings": {"autoMemoryEnabled": False}, "arm": "A"}
RESULT = {"type": "result", "subtype": "success", "is_error": False, "total_cost_usd": 0.42,
          "duration_ms": 61000, "duration_api_ms": 40000, "num_turns": 9,
          "modelUsage": {"claude-sonnet-5-5": {"inputTokens": 10, "outputTokens": 900,
                                               "cacheReadInputTokens": 5000, "cacheCreationInputTokens": 800,
                                               "costUSD": 0.42}}}


def stop(decision, sensor="pass", semantic=None, message=""):
    e = {"hook_event_name": "Stop", "decision": decision, "sensor": {"status": sensor, "seconds": 0.5},
         "output": {"systemMessage": message} if message else {}}
    if semantic:
        e["semantic"] = semantic
    return e


def build(prepared=GATED, result=RESULT, events=(), **kw):
    defaults = dict(evidence_kind="synthetic-test", prepared=prepared, result=result, timed_out=False,
                    exit_code=0, attempt_s=70.0, events=list(events), evaluation=None, started_at=None,
                    finished_at=None, environment={}, ledger=None, artifacts={})
    defaults.update(kw)
    return rr.build_record(**defaults)


class TestStream:
    def test_finds_the_result_and_keeps_bad_lines_visible(self):
        events, result, bad = rr.parse_stream(['{"type":"system"}', "not json", "[1]", json.dumps(RESULT), ""])

        assert len(events) == 2 and result == RESULT and len(bad) == 2

    def test_no_result_event(self):
        assert rr.parse_stream(['{"type":"assistant"}'])[1] is None


class TestTermination:
    @pytest.mark.parametrize(("result", "timed_out", "code", "expected"), [
        (RESULT, False, 0, "completed"),
        (RESULT, True, None, "wall_timeout"),
        ({**RESULT, "subtype": "error_max_budget_usd", "is_error": True}, False, 1, "budget_exhausted"),
        ({**RESULT, "is_error": True}, False, 1, "cli_error"),
        (RESULT, False, 1, "cli_error"),
        (None, False, 1, "cli_error"),
    ])
    def test_cases(self, result, timed_out, code, expected):
        assert rr.termination(result, timed_out=timed_out, exit_code=code) == expected


class TestUsage:
    def test_categories_per_model(self):
        usage = rr.agent_usage(RESULT)

        assert usage["cost_usd"] == "0.42"
        assert usage["by_model"]["claude-sonnet-5-5"]["cache_read_input_tokens"] == 5000

    def test_missing_usage_stays_missing_not_zero(self):
        assert rr.agent_usage(None)["cost_usd"] is None
        assert rr.agent_usage({"type": "result"})["missing"]
        assert rr.agent_usage({"total_cost_usd": -1})["cost_usd"] is None

    def test_judge_calls_with_unknown_cost_leave_the_total_unavailable(self):
        calls = [{"ledger_entry_id": "a", "cost_usd": "0.001", "usage": {"input_tokens": 3}},
                 {"ledger_entry_id": "b", "cost_usd": None}, {"cost_usd": None}]

        usage = rr.judge_usage(calls)

        assert usage["cost_usd"] is None
        assert usage["known_cost_subtotal_usd"] == "0.001"
        assert (usage["calls"], usage["started_calls"], usage["unknown_cost_calls"]) == (3, 2, 1)

    def test_unknown_cost_calls_keep_their_ledger_charge(self):
        calls = [{"ledger_entry_id": "a", "cost_usd": "0.002", "reservation_usd": "1.3721"},
                 {"ledger_entry_id": "b", "cost_usd": None, "reservation_usd": "1.38"},
                 {"ledger_entry_id": "c", "cost_usd": None, "reservation_usd": "1.38",
                  "ledger_charged_usd": "0"},  # the CLI never started: nothing charged
                 {"cost_usd": None, "reservation_usd": "1.38"}]  # refused by the ledger: not started

        usage = rr.judge_usage(calls)

        assert usage["unknown_cost_calls"] == 2
        assert usage["unknown_cost_held_usd"] == "1.38"
        assert usage["unknown_cost_unrecorded_charge_calls"] == 0
        assert usage["known_cost_subtotal_usd"] == "0.002"

    def test_an_unknown_call_without_any_charge_is_counted_not_guessed(self):
        usage = rr.judge_usage([{"ledger_entry_id": "b", "cost_usd": None}])

        assert usage["unknown_cost_held_usd"] == "0"
        assert usage["unknown_cost_unrecorded_charge_calls"] == 1

    def test_token_categories_count_calls_that_did_not_report_them(self):
        calls = [{"ledger_entry_id": "a", "cost_usd": "0.001", "usage": {"input_tokens": 3, "output_tokens": 9}},
                 {"ledger_entry_id": "b", "cost_usd": "0.001", "usage": {"input_tokens": 4}},
                 {"ledger_entry_id": "c", "cost_usd": None, "usage": None}]

        usage = rr.judge_usage(calls)

        assert usage["tokens"] == {"input_tokens": 7, "output_tokens": 9}
        assert usage["tokens_missing_calls"] == {"input_tokens": 1, "output_tokens": 2,
                                                 "cache_read_input_tokens": 3,
                                                 "cache_creation_input_tokens": 3}


class TestGateState:
    def test_arm_without_gate(self):
        assert rr.gate_state(False, []) == "no_gate"

    @pytest.mark.parametrize(("events", "state"), [
        ([], "missing"),
        ([stop("block", "violation"), stop("allow")], "passed"),
        ([stop("block", "violation")], "interrupted"),
        ([stop("allow", "violation", message="Architecture gate UNRESOLVED: still")], "unresolved"),
        ([stop("allow", semantic={"status": "inconclusive"})], "semantic_inconclusive"),
        ([stop("allow", semantic={"status": "pass"})], "passed"),
    ])
    def test_last_stop_decides(self, events, state):
        assert rr.gate_state(True, events) == state


class TestBuildRecord:
    def test_converged_repairs_are_counted(self):
        record = build(events=[stop("block", "violation"), stop("allow")])

        assert record["repair"] == {"applicable": True, "cycles": 1, "censored": False, "note": None,
                                    "checker_invocations": {"sensor": 2, "judge": 0}}
        assert record["outcome"]["completed_within_budget"] is True
        assert rr.validate_record(record) == []

    def test_unconverged_repairs_are_censored_not_zero(self):
        record = build(events=[stop("block", "violation")] * 3 +
                       [stop("allow", "violation", message="UNRESOLVED")])

        assert record["repair"]["censored"] is True
        assert record["repair"]["cycles"] == 3
        assert "lower bound" in record["repair"]["note"]

    def test_arm_a_repair_is_not_applicable(self):
        record = build(prepared=UNGATED)

        assert record["repair"]["applicable"] is False and record["repair"]["cycles"] is None
        assert record["usage"]["development_judge"] is None
        assert record["outcome"]["gate_final_state"] == "no_gate"

    def test_judge_failure_marks_the_run_not_runnable(self):
        events = [stop("allow", semantic={"status": "inconclusive", "provider_failed": True, "calls": []})]

        record = build(events=events)

        assert record["outcome"]["not_runnable"]

    def test_judge_failure_is_not_runnable_even_when_the_agent_succeeds(self):
        # Review probe: successful CLI result, development judge provider failure and
        # passing final checks must not become a completed (or accepted) run.
        failed_call = {"ledger_entry_id": "j1", "cost_usd": None, "reservation_usd": "1.38", "usage": None}
        events = [stop("allow", semantic={"status": "inconclusive", "provider_failed": True,
                                          "calls": [failed_call]})]
        evaluation = {"behavior": {"status": "pass"}, "structural": {"status": "pass"},
                      "semantic_judge": {"status": "pass"}, "semantic_judge_calls": [],
                      "tampering": {"detected": False, "baseline_tests_modified": []}}

        record = build(events=events, evaluation=evaluation, ledger={"agent_entry_id": "e"})

        o = record["outcome"]
        assert o["termination"] == "not_runnable" and o["completed_within_budget"] is False
        assert o["agent_started"] is True and o["agent_termination"] == "completed"
        assert record["usage"]["agent"]["cost_usd"] == "0.42"
        assert record["usage"]["development_judge"]["unknown_cost_held_usd"] == "1.38"

    def test_nothing_started_is_not_marked_as_an_agent_start(self):
        record = build(result=None, exit_code=None, not_runnable="judge unavailable at preparation")

        assert record["outcome"]["termination"] == "not_runnable"
        assert record["outcome"]["agent_started"] is False and record["outcome"]["agent_termination"] is None

    def test_semantic_label_is_always_null_and_submission_is_not_a_merge(self):
        evaluation = {"semantic_judge": {"status": "violation"}, "behavior": {"status": "pass"},
                      "structural": {"status": "pass"}, "tampering": {"detected": False,
                                                                      "baseline_tests_modified": []}}
        record = build(evaluation=evaluation)

        assert record["outcome"]["semantic_judge"] == "violation"
        assert record["outcome"]["semantic_label"] is None
        assert "not a merge" in record["outcome"]["submission"]

    def test_ci_queue_time_is_not_applicable_rather_than_zero(self):
        record = build()

        assert record["time"]["ci_queue_s"] is None and record["time"]["ci_queue_note"]
        assert record["time"]["model_api_s"] == 40.0

    def test_refuses_unknown_evidence_kind(self):
        with pytest.raises(ValueError):
            build(evidence_kind="made-up")

    def test_loads_rejects_a_record_with_a_label(self):
        record = build()
        record["outcome"]["semantic_label"] = "violation"

        with pytest.raises(ValueError, match="semantic_label"):
            rr.loads(rr.dumps(record))


class TestSettingsIntegrity:
    def test_without_a_settings_check_the_record_says_not_checked(self):
        record = build(evaluation={"tampering": {"detected": False}})

        assert record["outcome"]["settings_file_check"] == "not_checked"
        assert record["outcome"]["tampering_detected"] is False
        assert record["settings_integrity"] is None

    @pytest.mark.parametrize("status", ["changed", "missing", "unreadable"])
    def test_a_changed_or_deleted_settings_file_is_tampering(self, status):
        record = build(evaluation={"tampering": {"detected": False}},
                       settings_integrity={"status": status, "detected": True})

        assert record["outcome"]["tampering_detected"] is True
        assert record["outcome"]["settings_file_check"] == status

    def test_settings_tampering_counts_even_without_an_evaluation(self):
        record = build(settings_integrity={"status": "missing", "detected": True})

        assert record["outcome"]["tampering_detected"] is True

    def test_unchanged_settings_leave_the_evaluator_verdict_alone(self):
        record = build(evaluation={"tampering": {"detected": True}},
                       settings_integrity={"status": "unchanged", "detected": False})

        assert record["outcome"]["tampering_detected"] is True


class TestRedaction:
    def test_paths_and_secrets(self):
        text = "/home/me/example/src and /home/me/x; key sk-ant-abcdefghijklmnop and token: abcdefghijklmnopqrstuv"

        out = rr.redact(text, {"/home/me": "<home>", "/home/me/example": "<example>"})

        assert out.startswith("<example>/src and <home>/x")
        assert "sk-ant-" not in out and "abcdefghijklmnopqrstuv" not in out

    def test_init_event_drops_environment_listings(self):
        out = rr.sanitize_event({"type": "system", "subtype": "init", "tools": ["Bash"],
                                 "mcp_servers": [{"name": "x"}], "skills": ["y"]})

        assert out == {"type": "system", "subtype": "init", "tools": ["Bash"],
                       "omitted": ["mcp_servers", "skills"]}

    def test_compact_keeps_length_and_hash(self):
        out = rr.compact({"a": ["x" * 5000]}, limit=10)

        assert out["a"][0].startswith("x" * 10) and "5000 characters" in out["a"][0]


JSONISH = st.recursive(st.none() | st.booleans() | st.integers() | st.text(max_size=20),
                       lambda c: st.lists(c, max_size=4) | st.dictionaries(st.text(max_size=8), c, max_size=4),
                       max_leaves=20)


class TestProperties:
    @given(st.lists(st.text(max_size=80), max_size=10))
    def test_parse_stream_never_raises(self, lines):
        events, result, bad = rr.parse_stream(lines)
        assert len(events) + len(bad) <= len([line for line in lines if line.strip()])

    @given(st.lists(st.text(max_size=80), max_size=10))
    def test_parse_events_never_raises(self, lines):
        events, bad = rr.parse_events(lines)
        assert len(events) + bad == len([line for line in lines if line.strip()])

    @given(JSONISH)
    def test_agent_usage_never_raises_and_never_invents_cost(self, value):
        usage = rr.agent_usage(value if isinstance(value, dict) else None)
        if not (isinstance(value, dict) and "total_cost_usd" in value):
            assert usage["cost_usd"] is None

    @given(st.lists(st.sampled_from(["block", "allow"]), max_size=6),
           st.sampled_from(["pass", "violation", "checker_error"]))
    def test_repair_cycles_equal_blocks_and_censoring_matches_convergence(self, decisions, last_sensor):
        events = [stop(d, "violation") for d in decisions] + [stop("allow", last_sensor)]
        record = build(events=events)
        assert record["repair"]["cycles"] == decisions.count("block")
        assert record["repair"]["censored"] == (record["outcome"]["gate_final_state"] != "passed")

    @given(st.integers(0, 3), st.booleans(), st.floats(0, 1000, allow_nan=False))
    def test_record_roundtrips(self, blocks, timed_out, attempt):
        record = build(events=[stop("block", "violation")] * blocks + [stop("allow")],
                       timed_out=timed_out, attempt_s=attempt)
        assert rr.loads(rr.dumps(record)) == record

    @given(st.lists(st.fixed_dictionaries({
        "started": st.booleans(), "cost": st.none() | st.decimals(0, 2, places=4).map(str),
        "reservation": st.none() | st.decimals(0, 2, places=4).map(str),
        "charged": st.none() | st.decimals(0, 2, places=4).map(str),
        "usage": st.none() | st.dictionaries(st.sampled_from(rr.TOKEN_CATEGORIES), st.integers(-5, 10_000))}),
        max_size=6))
    def test_judge_usage_accounts_for_every_started_call(self, specs):
        calls = [{"ledger_entry_id": "e" if c["started"] else None, "cost_usd": c["cost"],
                  "reservation_usd": c["reservation"], "ledger_charged_usd": c["charged"],
                  "usage": c["usage"]} for c in specs]
        usage = rr.judge_usage(calls)
        started = [c for c in specs if c["started"]]
        unknown = [c for c in started if c["cost"] is None]
        assert usage["unknown_cost_calls"] == len(unknown)
        expected_held = sum(Decimal(c["charged"] or c["reservation"]) for c in unknown
                            if (c["charged"] or c["reservation"]) is not None)
        assert Decimal(usage["unknown_cost_held_usd"]) == expected_held
        assert usage["unknown_cost_unrecorded_charge_calls"] == sum(
            1 for c in unknown if c["charged"] is None and c["reservation"] is None)
        for key in rr.TOKEN_CATEGORIES:
            reported = [c["usage"][key] for c in started if c["usage"] and c["usage"].get(key, -1) >= 0]
            assert usage["tokens_missing_calls"][key] == len(started) - len(reported)
            assert (usage["tokens"] or {}).get(key) == (sum(reported) if reported else None)
        assert usage["cost_usd"] is None if unknown else usage["cost_usd"] is not None

    @given(JSONISH)
    def test_compact_is_idempotent_below_the_limit(self, value):
        once = rr.compact(value, limit=50)
        assert rr.compact(once, limit=10_000) == once
