"""Pure logic of the version 2 study: reviewed exceptions, bounds, planning, per-turn outcomes."""

import math
from collections import Counter

import pytest
from hypothesis import given
from hypothesis import strategies as st

import study_v2 as sv
from gates.linter_output import Edge
from gates.result import SensorResult, Status, Violation

RULE = "Controllers must not import infrastructure repositories directly"
LEGACY = "orders.controllers.reports -> orders.infrastructure.repository"
REVIEWED = {RULE: (LEGACY,)}


def result(status, *violations):
    return SensorResult(status, {RULE: "BROKEN" if any(v.kind == "broken" for v in violations) else "KEPT"},
                        tuple(violations), None, "ab" * 32, "2.17",
                        1 if any(v.kind == "broken" for v in violations) else 0, "raw")


def ignored(importer, imported):
    return Violation(RULE, Edge(importer, imported), "ignored")


def broken(importer, imported):
    return Violation(RULE, Edge(importer, imported, (3,)), "broken")


class TestReviewedExceptions:
    def test_only_the_reviewed_ignore_becomes_a_pass(self):
        r = sv.accept_reviewed_exceptions(
            result(Status.VIOLATION, ignored("orders.controllers.reports", "orders.infrastructure.repository")),
            REVIEWED)
        assert r.status is Status.PASS
        assert r.violations == ()
        assert r.exit_code == 0

    def test_a_new_broken_edge_is_still_a_violation(self):
        r = sv.accept_reviewed_exceptions(
            result(Status.VIOLATION,
                   ignored("orders.controllers.reports", "orders.infrastructure.repository"),
                   broken("orders.controllers.fulfilment", "orders.infrastructure.stock")),
            REVIEWED)
        assert r.status is Status.VIOLATION
        assert [v.edge.importer for v in r.violations] == ["orders.controllers.fulfilment"]
        assert r.exit_code == 1

    def test_an_unreviewed_ignore_is_still_a_violation(self):
        r = sv.accept_reviewed_exceptions(
            result(Status.VIOLATION, ignored("orders.controllers.fulfilment", "orders.infrastructure.stock")),
            REVIEWED)
        assert r.status is Status.VIOLATION

    def test_reviewing_an_edge_for_another_rule_does_not_accept_it(self):
        r = sv.accept_reviewed_exceptions(
            result(Status.VIOLATION, ignored("orders.controllers.reports", "orders.infrastructure.repository")),
            {"Some other rule": (LEGACY,)})
        assert r.status is Status.VIOLATION

    def test_pass_and_checker_error_are_unchanged(self):
        ok = result(Status.PASS)
        err = SensorResult.checker_error("boom", fingerprint=None)
        assert sv.accept_reviewed_exceptions(ok, REVIEWED) is ok
        assert sv.accept_reviewed_exceptions(err, REVIEWED) is err

    def test_parses_the_reviewed_exceptions_file(self):
        data = {"schema": sv.REVIEWED_SCHEMA, "exceptions": {RULE: [LEGACY]}}
        assert sv.parse_reviewed(data) == {RULE: (LEGACY,)}
        with pytest.raises(ValueError):
            sv.parse_reviewed({"schema": "other", "exceptions": {}})
        with pytest.raises(ValueError):
            sv.parse_reviewed({"schema": sv.REVIEWED_SCHEMA, "exceptions": {RULE: "not a list"}})


class TestBounds:
    def test_zero_failures_in_ten_matches_the_closed_form(self):
        assert sv.upper_bound(0, 10) == pytest.approx(1 - 0.05 ** 0.1, abs=1e-9)
        assert round(sv.upper_bound(0, 10), 3) == 0.259

    def test_known_clopper_pearson_values(self):
        # One-sided 95% exact bounds (Clopper-Pearson), checked against the
        # binomial CDF directly below.
        assert sv.upper_bound(0, 3) == pytest.approx(1 - 0.05 ** (1 / 3), abs=1e-9)
        assert sv.upper_bound(3, 3) == 1.0
        assert sv.lower_bound(0, 3) == 0.0
        assert sv.lower_bound(3, 3) == pytest.approx(0.05 ** (1 / 3), abs=1e-9)

    def test_rejects_impossible_counts(self):
        for k, n in ((-1, 3), (4, 3), (0, 0)):
            with pytest.raises(ValueError):
                sv.upper_bound(k, n)


def binom_cdf(k, n, p):
    return sum(math.comb(n, i) * p**i * (1 - p) ** (n - i) for i in range(k + 1))


class TestPlan:
    SCEN = ["S1", "S2"]
    ARMS = ["A", "B", "C"]
    MODELS = ["sonnet", "haiku"]

    def test_every_cell_appears_once_per_repeat_with_unique_ids(self):
        plan = sv.plan_sessions(self.SCEN, self.ARMS, self.MODELS, repeats=3, seed=7)
        assert len(plan) == 2 * 3 * 2 * 3
        assert len({p["run_id"] for p in plan}) == len(plan)
        cells = Counter((p["scenario_id"], p["arm"], p["model_key"]) for p in plan)
        assert set(cells.values()) == {3}
        assert [p["sequence"] for p in plan] == list(range(1, len(plan) + 1))

    def test_repeats_are_blocked_and_order_is_seeded(self):
        plan = sv.plan_sessions(self.SCEN, self.ARMS, self.MODELS, repeats=3, seed=7)
        assert [p["repeat"] for p in plan] == sorted(p["repeat"] for p in plan)
        assert plan == sv.plan_sessions(self.SCEN, self.ARMS, self.MODELS, repeats=3, seed=7)
        assert plan != sv.plan_sessions(self.SCEN, self.ARMS, self.MODELS, repeats=3, seed=8)


def stop(status, decision, semantic=None):
    event = {"hook_event_name": "Stop", "sensor": {"status": status}, "decision": decision}
    if semantic:
        event["semantic"] = {"status": semantic}
    return event


UPS = {"hook_event_name": "UserPromptSubmit"}


class TestTurns:
    def test_split_events_by_user_prompt(self):
        events = [UPS, stop("pass", "allow"), UPS, stop("violation", "block"), stop("pass", "allow")]
        assert [len(t) for t in sv.split_turns(events, 3)] == [1, 2, 0]

    def test_gated_turn_slip_caught_and_repaired(self):
        turns = sv.turn_outcomes(
            gated=True, n_steps=2,
            turn_results=[{"subtype": "success"}, {"subtype": "success"}],
            end_statuses=["pass", "pass"],
            events=[UPS, stop("violation", "block"), stop("pass", "allow"), UPS, stop("pass", "allow")])
        assert [t["slip"] for t in turns] == [True, False]
        assert turns[0]["caught"] is True and turns[0]["repaired"] is True
        assert turns[0]["repair_requests"] == 1
        assert turns[1]["caught"] is None

    def test_ungated_turn_slip_comes_from_the_turn_end_snapshot(self):
        turns = sv.turn_outcomes(
            gated=False, n_steps=2, turn_results=[{"subtype": "success"}, {"subtype": "success"}],
            end_statuses=["violation", "violation"], events=[])
        assert [t["slip"] for t in turns] == [True, True]
        assert turns[0]["caught"] is None and turns[0]["repaired"] is None

    def test_unreached_turns_are_censored_and_checker_errors_unknown(self):
        turns = sv.turn_outcomes(gated=False, n_steps=3, turn_results=[{"subtype": "success"}],
                                 end_statuses=["checker_error"], events=[])
        assert turns[0]["slip"] is None
        assert [t["reached"] for t in turns] == [True, False, False]
        assert turns[2]["slip"] is None and turns[2]["censored"] is True

    def test_a_blocked_turn_that_runs_out_of_repairs_is_caught_not_repaired(self):
        turns = sv.turn_outcomes(
            gated=True, n_steps=1, turn_results=[{"subtype": "success"}], end_statuses=["violation"],
            events=[UPS] + [stop("violation", "block")] * 3 + [stop("violation", "allow")])
        assert turns[0]["caught"] is True and turns[0]["repaired"] is False
        assert turns[0]["repair_requests"] == 3

    def test_a_semantic_block_after_a_structural_pass_is_not_a_structural_slip(self):
        turns = sv.turn_outcomes(
            gated=True, n_steps=1, turn_results=[{"subtype": "success"}], end_statuses=["pass"],
            events=[UPS, stop("pass", "block", semantic="violation"), stop("pass", "allow", semantic="pass")])
        assert turns[0]["slip"] is False
        assert turns[0]["semantic_first"] == "violation"
        assert turns[0]["repair_requests"] == 1


def stop_edges(status, decision, *edges):
    event = stop(status, decision)
    event["sensor"]["violations"] = [{"importer": a, "imported": b} for a, b in edges]
    return event


NEW = ("orders.controllers.fulfilment", "orders.infrastructure.stock")
OTHER = ("orders.controllers.fulfilment", "orders.infrastructure.catalog")


class TestNewEdges:
    def test_a_violation_carried_over_from_an_earlier_turn_is_persisting_not_a_new_slip(self):
        turns = sv.turn_outcomes(
            gated=False, n_steps=2, turn_results=[{"subtype": "success"}] * 2,
            end_statuses=["violation", "violation"], end_edges=[[NEW], [NEW]], events=[])
        assert [t["slip"] for t in turns] == [True, False]
        assert turns[1]["persisting_violation"] is True
        assert turns[0]["new_edges"] == [list(NEW)]

    def test_a_further_new_edge_on_top_of_a_persisting_one_is_a_slip(self):
        turns = sv.turn_outcomes(
            gated=False, n_steps=2, turn_results=[{"subtype": "success"}] * 2,
            end_statuses=["violation", "violation"], end_edges=[[NEW], [NEW, OTHER]], events=[])
        assert turns[1]["slip"] is True and turns[1]["new_edges"] == [list(OTHER)]

    def test_gated_first_candidate_edges_come_from_the_hook_event(self):
        events = [UPS, stop_edges("violation", "allow", NEW), UPS, stop_edges("violation", "allow", NEW)]
        turns = sv.turn_outcomes(gated=True, n_steps=2, turn_results=[{"subtype": "success"}] * 2,
                                 end_statuses=["violation", "violation"], end_edges=[[NEW], [NEW]],
                                 events=events)
        assert [t["slip"] for t in turns] == [True, False]
        assert turns[0]["caught"] is False  # the gate allowed the stop (for example, budget spent)

    def test_an_unknown_start_state_makes_the_slip_unknown(self):
        turns = sv.turn_outcomes(gated=False, n_steps=2, turn_results=[{"subtype": "success"}] * 2,
                                 end_statuses=["checker_error", "violation"], end_edges=[None, [NEW]],
                                 events=[])
        assert turns[1]["slip"] is None


class TestSummary:
    def test_counts_sessions_and_turns_per_cell_with_bounds(self):
        def rec(arm, slips, final="pass"):
            return {"identity": {"scenario_id": "S1", "arm": arm, "model_key": "haiku"},
                    "outcome": {"termination": "completed", "final_structural": final},
                    "turns": [{"reached": True, "slip": s, "censored": False} for s in slips]}
        records = [rec("A", [False, True]), rec("A", [False, False]), rec("B", [True, False], "pass")]
        cells = sv.summarize_cells(records)
        a = cells[("S1", "A", "haiku")]
        assert (a["sessions"], a["sessions_with_slip"]) == (2, 1)
        assert (a["turns"], a["turn_slips"]) == (4, 1)
        assert a["session_slip_upper95"] == pytest.approx(sv.upper_bound(1, 2))
        b = cells[("S1", "B", "haiku")]
        assert b["final_violations"] == 0

    def test_arm_c_sessions_without_their_judge_are_reported_outside_the_denominators(self):
        record = {"identity": {"scenario_id": "S1", "arm": "C", "model_key": "haiku"},
                  "outcome": {"termination": "completed", "final_structural": "pass", "judge_unavailable": True},
                  "turns": [{"reached": True, "slip": True, "censored": False}]}
        c = sv.summarize_cells([record])[("S1", "C", "haiku")]
        assert (c["attempted"], c["judge_unavailable"], c["sessions"], c["turns"]) == (1, 1, 0, 0)


class TestProperties:
    @given(st.integers(1, 60).flatmap(lambda n: st.tuples(st.integers(0, n), st.just(n))))
    def test_bounds_are_ordered_and_have_the_stated_coverage(self, kn):
        k, n = kn
        lo, hi = sv.lower_bound(k, n), sv.upper_bound(k, n)
        assert 0.0 <= lo <= k / n <= hi <= 1.0
        if k < n:
            assert binom_cdf(k, n, hi) == pytest.approx(0.05, abs=1e-6)
        if k > 0:
            assert 1 - binom_cdf(k - 1, n, lo) == pytest.approx(0.05, abs=1e-6)

    @given(st.lists(st.sampled_from(["UPS", "pass", "violation", "checker_error"]), max_size=20),
           st.integers(1, 5))
    def test_turn_outcomes_never_raise_and_counts_are_consistent(self, kinds, n_steps):
        events = [UPS if k == "UPS" else stop(k, "block" if k == "violation" else "allow") for k in kinds]
        reached = min(n_steps, sum(1 for k in kinds if k == "UPS"))
        turns = sv.turn_outcomes(gated=True, n_steps=n_steps, turn_results=[{"subtype": "success"}] * reached,
                                 end_statuses=["pass"] * reached, events=events)
        assert len(turns) == n_steps
        assert sum(t["reached"] for t in turns) == reached
        for t in turns:
            if t["caught"]:
                assert t["slip"] is True and t["repair_requests"] >= 1
            if not t["reached"]:
                assert t["slip"] is None
