"""Version 2 preparation, session driver and evaluator helpers. No processes, no network.

Git is mocked; workspaces are tmp_path replicas; the committed study files are read read-only.
"""

import json
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

import prepare_v2 as pv
import run_study_v2 as rs
from evaluator import evaluate_v2 as ev2

STUDY = pv.load_study()
SCENARIOS = pv.load_scenarios()


class FakeGit:
    def __init__(self):
        self.calls = []

    def __call__(self, argv, *, cwd, env, **kwargs):
        self.calls.append((argv, env.get("GIT_AUTHOR_DATE")))
        out = "abc123\n" if "rev-parse" in argv else ""
        return type("P", (), {"stdout": out, "returncode": 0})()


class TestStudyDefinition:
    def test_declared_budget_matches_the_session_caps_and_fits_the_remaining_cap(self):
        b = STUDY["budget"]
        sessions = len(STUDY["scenarios"]) * len(STUDY["arms"]) * len(STUDY["models"]) * STUDY["repeats"]
        assert sessions == b["sessions"] == 36
        per_model = sessions // len(STUDY["models"])
        caps = sum(Decimal(m["max_budget_usd"]) * per_model for m in STUDY["models"].values())
        assert caps == Decimal(b["agent_cap_sum_usd"])
        assert caps + Decimal(b["judge_allowance_usd"]) == Decimal(b["declared_usd"]) <= Decimal("97")

    def test_both_agent_configurations_and_three_repeats(self):
        assert STUDY["models"]["sonnet"]["model"] == "claude-sonnet-5-5"
        assert STUDY["models"]["sonnet"]["effort"] == "medium"
        assert STUDY["models"]["haiku"]["model"] == "claude-haiku-5-5"
        assert STUDY["repeats"] == 3 and set(STUDY["arms"]) == {"A", "B", "C"}

    def test_every_scenario_has_several_dependent_steps_with_acceptance_tests(self):
        assert set(SCENARIOS) == set(STUDY["scenarios"])
        for s in SCENARIOS.values():
            assert len(s["steps"]) == 4
            assert all(step["acceptance_test"].startswith("experiment/v2/evaluator/acceptance/") for step in s["steps"])


class TestArgv:
    def test_rule_is_delivered_only_through_the_workspace_claude_md(self, tmp_path):
        argv = pv.agent_argv(STUDY, "sonnet", settings_path=tmp_path / "s.json")
        assert "--append-system-prompt-file" not in argv
        assert argv[argv.index("--setting-sources") + 1] == "project"
        assert argv[argv.index("--input-format") + 1] == "stream-json"
        assert argv[argv.index("--effort") + 1] == "medium"
        assert argv[argv.index("--max-budget-usd") + 1] == "3.00"

    def test_haiku_runs_without_an_effort_flag(self, tmp_path):
        argv = pv.agent_argv(STUDY, "haiku", settings_path=tmp_path / "s.json")
        assert "--effort" not in argv and argv[argv.index("--model") + 1] == "claude-haiku-5-5"


class TestSettings:
    def kw(self, tmp_path):
        return dict(workspace=tmp_path / "ws", state_dir=tmp_path / "st", events=tmp_path / "ev",
                    rid="r", ledger=tmp_path / "l.json", python="py", root=tmp_path)

    def test_arm_a_has_no_hooks(self, tmp_path):
        assert pv.settings_for("A", STUDY, **self.kw(tmp_path)) == {"autoMemoryEnabled": False}

    def test_gated_arms_hook_stop_and_user_prompt_with_the_v2_contract(self, tmp_path):
        b = pv.settings_for("B", STUDY, **self.kw(tmp_path))
        assert set(b["hooks"]) == {"Stop", "UserPromptSubmit"}
        args = b["hooks"]["Stop"][0]["hooks"][0]["args"]
        assert args[args.index("--contract") + 1].endswith("experiment/v2/development.importlinter")
        assert args[args.index("--reviewed-exceptions") + 1].endswith("experiment/v2/reviewed-exceptions.json")
        assert "--semantic" not in args
        c = pv.settings_for("C", STUDY, **self.kw(tmp_path))
        assert "--semantic" in c["hooks"]["Stop"][0]["hooks"][0]["args"]


class TestWorkspace:
    def test_history_is_replayed_commit_by_commit_with_dates(self, tmp_path):
        git = FakeGit()
        head = pv.build_workspace(tmp_path / "ws", git=git)
        commits = [c for c in git.calls if "commit" in c[0]]
        history = json.loads(pv.HISTORY_PATH.read_text())
        assert head == "abc123"
        assert [c[1] for c in commits] == [h["date"] for h in history["commits"]]
        assert (tmp_path / "ws" / "CLAUDE.md").read_bytes() == pv.INSTRUCTION.read_bytes()
        assert (tmp_path / "ws" / "src" / "orders" / "controllers" / "reports.py").is_file()
        assert "reports" in (tmp_path / "ws" / "src" / "orders" / "wiring.py").read_text()

    def test_an_existing_workspace_is_never_reused(self, tmp_path):
        (tmp_path / "ws").mkdir()
        with pytest.raises(pv.NotRunnable):
            pv.build_workspace(tmp_path / "ws", git=FakeGit())


def result(subtype="success", cost=None, is_error=False, duration=1000):
    return {"type": "result", "subtype": subtype, "is_error": is_error, "total_cost_usd": cost,
            "duration_ms": duration}


class TestDriveSession:
    def run(self, events, n=3, deadline=100.0):
        sent, ended, clock = [], [], iter(range(1000))
        stream = iter(events)
        res = rs.drive_session(sent.append, lambda timeout: next(stream, None), [f"m{i}" for i in range(n)],
                               deadline=deadline, clock=lambda: next(clock), on_turn_end=lambda i, e: ended.append(i))
        return res, sent, ended

    def test_sends_each_message_only_after_the_previous_result(self):
        (results, timed_out, eof), sent, ended = self.run(
            [{"type": "assistant"}, result(), result(), {"type": "system"}, result()])
        assert len(results) == 3 and not timed_out and not eof
        assert [json.loads(s)["message"]["content"] for s in sent] == ["m0", "m1", "m2"]
        assert ended == [0, 1, 2]

    def test_an_errored_turn_stops_further_messages(self):
        (results, _, _), sent, _ = self.run([result(), result("error_max_budget_usd", is_error=True)])
        assert len(results) == 2 and len(sent) == 2

    def test_silence_is_a_timeout_and_eof_ends_early(self):
        (results, timed_out, _), _, _ = self.run([result()])
        assert timed_out and len(results) == 1
        (results, timed_out, eof), _, _ = self.run([result(), {"type": "_eof"}])
        assert eof and not timed_out and len(results) == 1


class TestRecordHelpers:
    def test_termination(self):
        ok = [result(cost=0.1)] * 2
        assert rs.session_termination(ok, 2, timed_out=False, exit_code=0) == "completed"
        assert rs.session_termination(ok[:1], 2, timed_out=False, exit_code=0) == "cli_error"
        assert rs.session_termination([result("error_max_budget_usd")], 2, timed_out=False, exit_code=1) == "budget_exhausted"
        assert rs.session_termination(ok, 2, timed_out=True, exit_code=None) == "wall_timeout"
        assert rs.session_termination([], 2, timed_out=False, exit_code=1) == "cli_error"

    def test_turn_costs_are_differences_of_the_cumulative_total(self):
        assert rs.turn_costs([result(cost=0.25), result(cost=0.75), result(cost=None)]) == ["0.25", "0.50", None]

    def test_not_started_record_keeps_every_step_censored(self):
        scenario = SCENARIOS["S1-customer-insights"]
        placeholder = {"study": "x", "run_id": "r", "scenario_id": scenario["id"], "arm": "B",
                       "model_key": "haiku", "repeat": 1, "plan": {"sequence": 4}}
        record = rs.build_record(
            prepared=placeholder, study=STUDY, scenario=scenario, results=[], timed_out=False, exit_code=None,
            session_s=None, turn_statuses=[], hook_events=[], evaluation=None, settings_check=None, environment={},
            ledger=None, artifacts={}, retries=[], blind_id="b", started_at=None, finished_at=None, history=None,
            notes=["refused"], models_reported=[], not_started="refused")
        assert record["outcome"]["termination"] == "not_started_cap"
        assert all(t["censored"] for t in record["turns"]) and len(record["turns"]) == 4


class TestEvaluatorHelpers:
    def test_tamper_report_flags_protected_files_and_records_legacy_edits(self):
        prepared = {"workspace": {"CLAUDE.md": "a", "tests/test_orders.py": "b", ev2.LEGACY_MODULE: "c"},
                    "gates": {"g": "1"}}
        clean = ev2.tamper_report(prepared, {"CLAUDE.md": "a", "tests/test_orders.py": "b", ev2.LEGACY_MODULE: "c"},
                                  {"g": "1"})
        assert clean["detected"] is False and clean["legacy_reports_modified"] is False
        edited = ev2.tamper_report(prepared, {"CLAUDE.md": "x", "tests/test_orders.py": "y", ev2.LEGACY_MODULE: "z"},
                                   {"g": "1"})
        assert edited["detected"] is True and edited["legacy_reports_modified"] is True
        assert edited["baseline_tests_modified"] == ["tests/test_orders.py"]

    def test_the_v2_freeze_covers_the_study_tooling_and_criteria(self):
        for pattern in ("experiment/protocol-v2.md", "experiment/v2/study.json", "experiment/tools/run_study_v2.py",
                        "experiment/v2/evaluator/acceptance/*.py", "experiment/v2/baseline/**"):
            assert pattern in ev2.FROZEN_PATTERNS


class TestProperties:
    @given(st.lists(st.one_of(st.none(), st.floats(0, 50, allow_nan=False).map(lambda x: round(x, 6))), max_size=6))
    def test_turn_costs_sum_to_the_last_known_total(self, values):
        values = sorted(v for v in values if v is not None)
        costs = rs.turn_costs([result(cost=v) for v in values])
        if values:
            assert sum(Decimal(c) for c in costs) == Decimal(str(values[-1]))
