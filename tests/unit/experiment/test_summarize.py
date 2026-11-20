"""Pilot summaries from synthetic records (evidence_kind synthetic-test, never real data)."""

from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

import run_record as rr
import summarize as sm

RESULT = {"type": "result", "subtype": "success", "is_error": False, "total_cost_usd": 0.5,
          "duration_ms": 60000, "duration_api_ms": 30000, "num_turns": 5}


def record(arm="B", task="T01", behavior="pass", structural="pass", cost=0.5, result=True,
           tampered=False, not_started=False, timed_out=False, blocks=0, converged=True,
           eval_calls=(), dev_calls=(), model_usage=None, settings_check=None):
    settings = {"hooks": {"Stop": []}} if arm != "A" else {}
    prepared = {"settings": settings, "run_id": f"{task}__{arm}__r1", "arm": arm, "task_id": task,
                "agent_config": {"model": "m"}, "plan": {"position_in_task": 1},
                "_not_started": not_started}
    res = None if not result else {**RESULT, "total_cost_usd": cost} if cost is not None else \
        {k: v for k, v in RESULT.items() if k != "total_cost_usd"}
    if res is not None and model_usage is not None:
        res = {**res, "modelUsage": model_usage}
    events = []
    if arm != "A":
        events = [{"hook_event_name": "Stop", "decision": "block", "sensor": {"status": "violation"}}] * blocks
        last = {"hook_event_name": "Stop", "decision": "allow",
                "sensor": {"status": "pass" if converged else "violation"},
                "output": {} if converged else {"systemMessage": "UNRESOLVED"}}
        if dev_calls:
            last["semantic"] = {"status": "pass", "calls": list(dev_calls)}
        events.append(last)
    evaluation = None if not_started else {
        "behavior": {"status": behavior}, "structural": {"status": structural},
        "semantic_judge": {"status": "pass"}, "semantic_judge_calls": list(eval_calls),
        "tampering": {"detected": tampered, "baseline_tests_modified": []}}
    ledger = None if not_started else {"agent_entry_id": "e", "reserved_usd": "7.78",
                                       "charged_usd": str(cost) if cost is not None else "7.78",
                                       "cost_known": cost is not None}
    return rr.build_record(evidence_kind="synthetic-test", prepared=prepared, result=None if not_started else res,
                           timed_out=timed_out, exit_code=0, attempt_s=None if not_started else 60.0,
                           events=[] if not_started else events, evaluation=evaluation, started_at=None,
                           finished_at=None, environment={}, ledger=ledger, artifacts={},
                           settings_integrity=settings_check)


class TestSpread:
    def test_empty(self):
        assert sm.spread([]) == {"n": 0, "median": None, "q1": None, "q3": None, "min": None, "max": None}

    def test_whole_numbers_are_never_written_in_exponent_form(self):
        assert sm.spread([900, 1200])["median"] == "1050"
        assert sm.spread([900])["max"] == "900"

    def test_quartiles(self):
        assert sm.spread([1, 2, 3, 4, 5]) == {"n": 5, "median": "3", "q1": "2", "q3": "4", "min": "1", "max": "5"}


class TestArmSummary:
    def test_denominators_include_every_attempt(self):
        records = [record(), record(not_started=True), record(timed_out=True, cost=None)]

        s = sm.summarize_arm(records)

        assert s["attempted"] == 3 and s["started"] == 2
        assert sum(s["termination"].values()) == 3
        assert s["termination"]["not_started_cap"] == 1

    def test_accepted_requires_completion_behaviour_structure_and_no_tampering(self):
        records = [record(), record(structural="violation"), record(behavior="fail"), record(tampered=True),
                   record(timed_out=True)]

        assert sm.summarize_arm(records)["accepted"] == 1

    def test_zero_accepted_makes_cost_per_outcome_undefined_but_spend_visible(self):
        s = sm.summarize_arm([record(behavior="fail", cost=0.8), record(structural="violation", cost=0.2)])

        assert s["accepted"] == 0
        assert s["cost_per_accepted_outcome_usd"] is None
        assert s["cost_per_accepted_outcome_note"] == "undefined: zero accepted outcomes"
        assert Decimal(s["spend_usd"]["total_charged"]) == Decimal("1.0")

    def test_unknown_cost_holds_the_reservation_and_is_flagged(self):
        s = sm.summarize_arm([record(cost=None, timed_out=True)])

        assert s["spend_usd"]["held_for_unknown_cost"] == "7.78"
        assert s["spend_usd"]["runs_with_unknown_cost"] == 1
        assert s["agent_usage_missing_runs"] == 1

    def test_censored_repair_loops_are_counted_not_averaged(self):
        s = sm.summarize_arm([record(blocks=1), record(blocks=3, converged=False)])

        assert s["repair_cycles"]["converged_runs"] == 1
        assert s["repair_cycles"]["censored_runs"] == 1
        assert s["repair_cycles"]["converged_cycles"]["median"] == "1"


KNOWN_CALL = {"ledger_entry_id": "j", "cost_usd": "0.002", "reservation_usd": "1.3721",
              "usage": {"input_tokens": 2, "output_tokens": 150, "cache_read_input_tokens": 8000,
                        "cache_creation_input_tokens": 0}}
UNKNOWN_CALL = {"ledger_entry_id": "u", "cost_usd": None, "reservation_usd": "1.38", "usage": None}


class TestJudgeHolds:
    def test_review_probe_known_agent_cost_plus_reserved_evaluation_judge(self):
        # US$0.50 known agent cost and one evaluation judge call whose cost is unknown.
        s = sm.summarize_arm([record(arm="A", eval_calls=[UNKNOWN_CALL])])

        spend = s["spend_usd"]
        assert spend["known"] == "0.5"
        assert spend["held_for_unknown_cost"] == "1.38"
        assert Decimal(spend["total_charged"]) == Decimal("1.88")
        assert spend["runs_with_unknown_cost"] == 1
        assert spend["judge_unknown_cost_calls_without_recorded_hold"] == 0

    def test_development_judge_failure_holds_its_reservation(self):
        s = sm.summarize_arm([record(arm="C", dev_calls=[UNKNOWN_CALL], eval_calls=[KNOWN_CALL])])

        assert s["spend_usd"]["held_for_unknown_cost"] == "1.38"
        assert Decimal(s["spend_usd"]["total_charged"]) == Decimal("0.5") + Decimal("0.002") + Decimal("1.38")

    def test_zero_accepted_with_judge_failures_keeps_the_held_spend(self):
        s = sm.summarize_arm([record(arm="C", behavior="fail", dev_calls=[UNKNOWN_CALL], eval_calls=[UNKNOWN_CALL])])

        assert s["accepted"] == 0 and s["cost_per_accepted_outcome_usd"] is None
        assert s["spend_usd"]["held_for_unknown_cost"] == "2.76"
        assert Decimal(s["spend_usd"]["total_charged"]) == Decimal("3.26")

    def test_older_records_without_a_recorded_hold_are_counted(self):
        r = record(arm="A", eval_calls=[UNKNOWN_CALL])
        del r["usage"]["evaluation_judge"]["unknown_cost_held_usd"]

        s = sm.summarize_arm([r])

        assert s["spend_usd"]["held_for_unknown_cost"] == "0"
        assert s["spend_usd"]["judge_unknown_cost_calls_without_recorded_hold"] == 1


class TestUnavailableJudge:
    def test_unavailable_development_judge_is_not_runnable_through_to_the_summary(self):
        # Collection -> summary: the agent succeeded and final checks passed, but arm C's
        # development judge failed, so the run is not runnable and never accepted.
        r = record(arm="C", dev_calls=[UNKNOWN_CALL], eval_calls=[KNOWN_CALL])
        r_events_failed = rr.build_record(
            evidence_kind="synthetic-test",
            prepared={"settings": {"hooks": {"Stop": []}}, "run_id": "T01__C__r1", "arm": "C",
                      "task_id": "T01", "agent_config": {"model": "m"}, "plan": {"position_in_task": 1}},
            result=RESULT, timed_out=False, exit_code=0, attempt_s=60.0,
            events=[{"hook_event_name": "Stop", "decision": "allow", "sensor": {"status": "pass"},
                     "semantic": {"status": "inconclusive", "provider_failed": True,
                                  "calls": [UNKNOWN_CALL]}}],
            evaluation={"behavior": {"status": "pass"}, "structural": {"status": "pass"},
                        "semantic_judge": {"status": "pass"}, "semantic_judge_calls": [KNOWN_CALL],
                        "tampering": {"detected": False, "baseline_tests_modified": []}},
            started_at=None, finished_at=None, environment={},
            ledger={"agent_entry_id": "e", "charged_usd": "0.5", "cost_known": True}, artifacts={})

        assert sm.accepted(r) is True
        assert sm.accepted(r_events_failed) is False
        s = sm.summarize_arm([r, r_events_failed])
        assert s["attempted"] == 2 and s["started"] == 2
        assert s["termination"] == {"completed": 1, "not_runnable": 1}
        assert s["not_runnable"] == 1 and s["completed_within_budget"] == 1 and s["accepted"] == 1
        # The not-runnable run's agent and judge spend stays in the total.
        each = Decimal("0.5") + Decimal("0.002") + Decimal("1.38")
        assert Decimal(s["spend_usd"]["total_charged"]) == 2 * each

    def test_legacy_record_without_termination_check_is_not_accepted_when_not_runnable(self):
        r = record()
        r["outcome"]["not_runnable"] = "judge unavailable"
        assert sm.accepted(r) is False


class TestRetrySpend:
    def test_retried_attempt_judge_spend_is_included(self):
        r = record(arm="C", dev_calls=[KNOWN_CALL], eval_calls=[KNOWN_CALL])
        r["infrastructure_retries"] = [{
            "attempt": 1, "ledger": {"agent_entry_id": "e1", "charged_usd": "5.28", "cost_known": False},
            "usage": rr.attempt_judge_usage(True, [{"semantic": {"calls": [UNKNOWN_CALL]}}],
                                            {"semantic_judge_calls": [KNOWN_CALL]})}]

        s = sm.summarize_arm([r])

        final = Decimal("0.5") + 2 * Decimal("0.002")
        retry = Decimal("5.28") + Decimal("1.38") + Decimal("0.002")
        assert Decimal(s["spend_usd"]["total_charged"]) == final + retry
        assert Decimal(s["spend_usd"]["held_for_unknown_cost"]) == Decimal("5.28") + Decimal("1.38")


class TestTokenDistributions:
    def test_categories_by_source_with_denominators(self):
        mu = {"m": {"inputTokens": 10, "outputTokens": 900, "cacheReadInputTokens": 5000,
                    "cacheCreationInputTokens": 800, "costUSD": 0.5}}
        s = sm.summarize_arm([record(arm="C", model_usage=mu, dev_calls=[KNOWN_CALL], eval_calls=[KNOWN_CALL]),
                              record(arm="C", eval_calls=[KNOWN_CALL])])

        u = s["usage_tokens"]
        assert u["agent"]["output_tokens"]["median"] == "900"
        assert u["agent"]["output_tokens"]["observed_runs"] == 1
        assert u["agent"]["output_tokens"]["missing_runs"] == 1  # no modelUsage reported
        assert u["development_judge"]["applicable_runs"] == 1
        assert u["development_judge"]["cache_read_input_tokens"]["median"] == "8000"
        assert u["evaluation_judge"]["applicable_runs"] == 2
        assert u["evaluation_judge"]["input_tokens"]["n"] == 2

    def test_missing_categories_stay_missing_not_zero(self):
        s = sm.summarize_arm([record(arm="A", eval_calls=[UNKNOWN_CALL]),
                              record(arm="A", model_usage={"m": {"inputTokens": 5}})])

        ev = s["usage_tokens"]["evaluation_judge"]
        assert ev["applicable_runs"] == 1
        assert ev["output_tokens"] == {"observed_runs": 0, "missing_runs": 1, **sm.spread([])}
        agent = s["usage_tokens"]["agent"]
        assert agent["input_tokens"]["observed_runs"] == 1
        assert agent["output_tokens"]["observed_runs"] == 0 and agent["output_tokens"]["missing_runs"] == 2

    def test_arms_without_a_development_judge_are_not_applicable(self):
        s = sm.summarize_arm([record(arm="B"), record(arm="A")])

        dev = s["usage_tokens"]["development_judge"]
        assert dev["applicable_runs"] == 0 and dev["input_tokens"]["missing_runs"] == 0

    def test_legacy_judge_part_trusts_only_a_single_call(self):
        assert sm.judge_tokens({"started_calls": 1, "tokens": {"input_tokens": 3}})["input_tokens"] == 3
        assert sm.judge_tokens({"started_calls": 2, "tokens": {"input_tokens": 3}})["input_tokens"] is None
        assert sm.judge_tokens({"started_calls": 0, "tokens": None}) is None


class TestSettingsCheckCounts:
    def test_counts_settings_checks_and_folds_tampering(self):
        s = sm.summarize_arm([record(), record(settings_check={"status": "missing", "detected": True}),
                              record(settings_check={"status": "unchanged", "detected": False})])

        assert s["settings_file_check"] == {"missing": 1, "not_checked": 1, "unchanged": 1}
        assert s["tampering_detected"] == 1 and s["accepted"] == 2


class TestSummary:
    def test_paired_outcomes_by_task(self):
        s = sm.summarize([record("A", structural="violation"), record("B"), record("C")], pilot="p", plan_size=3)

        assert s["paired_by_task"][0]["arms"]["A"]["structural"] == "violation"
        assert s["missing_records"] == 0
        assert s["judge"]["false_positive_rate"] is None
        assert "independent human labels" in s["judge"]["rates_note"]

    def test_refuses_to_mix_real_and_synthetic(self):
        real = record()
        real["evidence_kind"] = "real"

        with pytest.raises(sm.MixedEvidence):
            sm.summarize([record(), real], pilot="p")

    def test_calibration_agreement_is_a_count(self):
        calibration = {"results": [
            {"kind": "calibration", "authored_label": "pass", "outcome": {"status": "pass"}},
            {"kind": "calibration", "authored_label": "violation", "outcome": {"status": "inconclusive"}},
            {"kind": "fixture", "outcome": {"status": "pass"}}]}

        cal = sm.judge_section([], calibration)["calibration"]

        assert cal["cases"] == 2 and cal["agreements"] == 1
        assert "not an accuracy rate" in cal["note"]


OUTCOME = st.fixed_dictionaries({
    "arm": st.sampled_from("ABC"), "behavior": st.sampled_from(["pass", "fail", "error"]),
    "structural": st.sampled_from(["pass", "violation", "checker_error"]),
    "cost": st.none() | st.decimals(0, 5, places=4).map(float), "tampered": st.booleans(),
    "not_started": st.booleans(), "timed_out": st.booleans(),
    "eval_unknown": st.booleans(), "dev_unknown": st.booleans(),
})


class TestProperties:
    @given(st.lists(st.tuples(st.booleans(), st.booleans()), max_size=10))
    def test_held_spend_equals_the_unknown_judge_reservations(self, flags):
        records = [record("C", eval_calls=[UNKNOWN_CALL if e else KNOWN_CALL],
                          dev_calls=[UNKNOWN_CALL if d else KNOWN_CALL]) for e, d in flags]
        s = sm.summarize_arm(records)
        unknown_calls = sum(e + d for e, d in flags)
        assert Decimal(s["spend_usd"]["held_for_unknown_cost"]) == Decimal("1.38") * unknown_calls
        assert s["spend_usd"]["runs_with_unknown_cost"] == sum(1 for e, d in flags if e or d)

    @given(st.lists(st.floats(-1e6, 1e6, allow_nan=False), min_size=1, max_size=30))
    def test_spread_is_ordered(self, xs):
        s = sm.spread(xs)
        assert Decimal(s["min"]) <= Decimal(s["q1"]) <= Decimal(s["median"]) <= Decimal(s["q3"]) <= Decimal(s["max"])

    @given(st.lists(OUTCOME, max_size=12))
    def test_counts_and_spend_are_consistent(self, outcomes):
        records = [record(o["arm"], behavior=o["behavior"], structural=o["structural"], cost=o["cost"],
                          tampered=o["tampered"], not_started=o["not_started"], timed_out=o["timed_out"],
                          eval_calls=[UNKNOWN_CALL if o["eval_unknown"] else KNOWN_CALL],
                          dev_calls=[UNKNOWN_CALL] if o["dev_unknown"] and o["arm"] == "C" else [])
                   for o in outcomes]
        summary = sm.summarize(records, pilot="p", plan_size=len(records))
        total = sum(a["attempted"] for a in summary["by_arm"].values())
        assert total == len(records)
        for arm in summary["by_arm"].values():
            assert sum(arm["termination"].values()) == arm["attempted"]
            assert 0 <= arm["accepted"] <= arm["completed_within_budget"] <= arm["started"] <= arm["attempted"]
            spend = arm["spend_usd"]
            assert Decimal(spend["total_charged"]) == Decimal(spend["known"]) + Decimal(spend["held_for_unknown_cost"])
            for source in arm["usage_tokens"].values():
                if not isinstance(source, dict):
                    continue
                for key in rr.TOKEN_CATEGORIES:
                    cat = source[key]
                    assert cat["observed_runs"] + cat["missing_runs"] == source["applicable_runs"]
                    assert cat["n"] == cat["observed_runs"]
                assert source["applicable_runs"] <= source["started_runs"] == arm["started"]
            if arm["accepted"] == 0:
                assert arm["cost_per_accepted_outcome_usd"] is None
            else:
                assert arm["cost_per_accepted_outcome_usd"] is not None
