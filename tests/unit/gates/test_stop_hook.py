"""Claude Code Stop-hook adapter. The sensor is injected; state uses a temp directory."""

import json

import pytest
from hypothesis import given
from hypothesis import strategies as st

from gates.linter_output import Edge
from gates.result import SensorResult, Status, Violation
from gates.stop_hook import FileStateStore, SessionState, handle_event, session_key

RULE = "Controllers must not import infrastructure repositories directly"


def passing():
    return SensorResult(Status.PASS, {RULE: "KEPT"}, (), None, "aa" * 32, "2.17", 0, "")


def violating():
    edge = Edge("orders.controllers.orders", "orders.infrastructure.repository", (16,))
    return SensorResult(Status.VIOLATION, {RULE: "BROKEN"}, (Violation(RULE, edge),), None,
                        "bb" * 32, "2.17", 1, "raw")


def checker_error():
    return SensorResult.checker_error("lint-imports not found", fingerprint="cc" * 32)


def stop(session="s1", active=False):
    return json.dumps({"session_id": session, "hook_event_name": "Stop",
                       "stop_hook_active": active, "cwd": "/x", "transcript_path": "/t"})


def prompt(session="s1"):
    return json.dumps({"session_id": session, "hook_event_name": "UserPromptSubmit",
                       "prompt": "hi", "cwd": "/x", "transcript_path": "/t"})


class Sensor:
    def __init__(self, *results):
        self.results, self.calls = list(results), 0

    def __call__(self):
        self.calls += 1
        result = self.results[min(self.calls - 1, len(self.results) - 1)]
        if isinstance(result, Exception):
            raise result
        return result


@pytest.fixture
def store(tmp_path):
    return FileStateStore(tmp_path / "state")


def run(raw, sensor, store, max_repairs=3):
    outcome = handle_event(raw, run_sensor=sensor, store=store, max_repairs=max_repairs)
    payload = json.loads(outcome.stdout) if outcome.stdout else None
    return outcome, payload


class TestStop:
    def test_pass_allows_stopping(self, store):
        outcome, payload = run(stop(), Sensor(passing()), store)

        assert outcome.exit_code == 0
        assert "decision" not in (payload or {})
        assert store.load(session_key("s1")).outcome == "passed"

    def test_violation_blocks_with_the_diagnostic_as_reason(self, store):
        outcome, payload = run(stop(), Sensor(violating()), store)

        assert outcome.exit_code == 0
        assert payload["decision"] == "block"
        assert "orders.controllers.orders -> orders.infrastructure.repository" in payload["reason"]
        assert "repair request 1 of 3" in payload["reason"]

    def test_checker_error_blocks_and_never_reads_as_a_pass(self, store):
        _, payload = run(stop(), Sensor(checker_error()), store)

        assert payload["decision"] == "block"
        assert "ARCHITECTURE CHECK ERROR" in payload["reason"]
        assert store.load(session_key("s1")).outcome == "open"

    def test_sensor_crash_is_treated_as_a_checker_error(self, store):
        _, payload = run(stop(), Sensor(RuntimeError("kaboom")), store)

        assert payload["decision"] == "block"
        assert "kaboom" in payload["reason"]

    def test_repair_then_pass_resets_the_budget(self, store):
        sensor = Sensor(violating(), passing(), violating())

        run(stop(), sensor, store)
        _, second = run(stop(active=True), sensor, store)
        _, third = run(stop(), sensor, store)

        assert "decision" not in (second or {})
        assert "repair request 1 of 3" in third["reason"]

    def test_retry_exhaustion_ends_unresolved_not_passed(self, store):
        sensor = Sensor(violating())
        for attempt in range(1, 4):
            _, payload = run(stop(active=attempt > 1), sensor, store)
            assert payload["decision"] == "block"

        outcome, payload = run(stop(active=True), sensor, store)

        assert outcome.exit_code == 0
        assert "decision" not in payload  # the turn is allowed to end ...
        assert "UNRESOLVED" in payload["systemMessage"]  # ... but not as a success
        assert "not passed" in payload["systemMessage"]
        state = store.load(session_key("s1"))
        assert state.outcome == "unresolved"
        assert state.last_status == "violation"

    def test_exhausted_session_stays_unresolved_until_the_next_prompt(self, store):
        sensor = Sensor(violating())
        for _ in range(4):
            run(stop(), sensor, store)

        _, still = run(stop(), sensor, store)
        assert "UNRESOLVED" in still["systemMessage"]

        run(prompt(), sensor, store)
        _, fresh = run(stop(), sensor, store)
        assert fresh["decision"] == "block"
        assert "repair request 1 of 3" in fresh["reason"]

    def test_budget_is_independent_of_stop_hook_active(self, store):
        # Claude Code's own consecutive-continuation cap resets whenever Claude
        # calls a tool, so it does not bound an edit-and-retry loop. The adapter
        # keeps its own count even if stop_hook_active is always false.
        sensor = Sensor(violating())
        for _ in range(3):
            run(stop(active=False), sensor, store)
        _, payload = run(stop(active=False), sensor, store)
        assert "UNRESOLVED" in payload["systemMessage"]

    def test_sessions_are_isolated(self, store):
        sensor = Sensor(violating())
        for _ in range(4):
            run(stop("session-a"), sensor, store)

        _, other = run(stop("session-b"), sensor, store)

        assert other["decision"] == "block"
        assert "repair request 1 of 3" in other["reason"]

    def test_corrupt_state_fails_closed_to_unresolved(self, store):
        store.directory.mkdir(parents=True)
        (store.directory / f"{session_key('s1')}.json").write_text("{nope")

        _, payload = run(stop(), Sensor(violating()), store)

        assert "UNRESOLVED" in payload["systemMessage"]

    def test_corrupt_state_with_a_passing_check_still_passes(self, store):
        store.directory.mkdir(parents=True)
        (store.directory / f"{session_key('s1')}.json").write_text("{nope")

        _, payload = run(stop(), Sensor(passing()), store)

        assert "decision" not in (payload or {})


class TestOtherInput:
    @pytest.mark.parametrize(
        "raw",
        ["", "not json", "[]", json.dumps({"hook_event_name": "Stop"}),
         json.dumps({"session_id": 7, "hook_event_name": "Stop"}),
         json.dumps({"session_id": "", "hook_event_name": "Stop"})],
    )
    def test_malformed_input_reports_unresolved_without_running_or_blocking(self, raw, store):
        sensor = Sensor(passing())

        outcome, payload = run(raw, sensor, store)

        assert outcome.exit_code == 0
        assert sensor.calls == 0
        assert "decision" not in payload
        assert "UNRESOLVED" in payload["systemMessage"]

    def test_user_prompt_resets_only_that_session(self, store):
        sensor = Sensor(violating())
        run(stop("a"), sensor, store)
        run(stop("b"), sensor, store)

        outcome, payload = run(prompt("a"), sensor, store)

        assert outcome.exit_code == 0 and payload is None and sensor.calls == 2
        assert store.load(session_key("a")).repairs_requested == 0
        assert store.load(session_key("b")).repairs_requested == 1

    def test_unrelated_events_are_ignored(self, store):
        raw = json.dumps({"session_id": "s1", "hook_event_name": "PostToolUse"})
        sensor = Sensor(passing())

        outcome, payload = run(raw, sensor, store)

        assert (outcome.exit_code, payload, sensor.calls) == (0, None, 0)

    def test_reset_all_removes_only_state_files(self, store):
        run(stop("a"), Sensor(violating()), store)
        keep = store.directory / "README.txt"
        keep.write_text("not state")

        store.reset_all()

        assert store.load(session_key("a")).repairs_requested == 0
        assert keep.exists()


class BrokenStore:
    """A state store whose chosen operations raise, like an unwritable directory."""

    def __init__(self, *failing, error=PermissionError(13, "Permission denied")):
        self.failing, self.error = set(failing), error
        self.inner = {}

    def _maybe_fail(self, op):
        if op in self.failing:
            raise self.error

    def load(self, key):
        self._maybe_fail("load")
        return self.inner.get(key, SessionState())

    def save(self, key, state):
        self._maybe_fail("save")
        self.inner[key] = state

    def delete(self, key):
        self._maybe_fail("delete")
        self.inner.pop(key, None)


class TestStateStorageFailure:
    """State-store failures must end the loop UNRESOLVED, never request another repair.

    The repair budget only bounds the loop if each repair request is recorded first.
    If the count cannot be read or written, a block would be unbounded.
    """

    @pytest.mark.parametrize("failing", [("save",), ("load",), ("load", "save")])
    @pytest.mark.parametrize("result", [violating, checker_error])
    def test_unrecordable_budget_never_blocks(self, failing, result):
        store, sensor = BrokenStore(*failing), Sensor(result())
        for _ in range(10):  # far beyond max_repairs=3
            outcome, payload = run(stop(), sensor, store)
            assert outcome.exit_code == 0
            assert "decision" not in payload
            assert "UNRESOLVED" in payload["systemMessage"]
            assert "repair budget" in payload["systemMessage"]

    def test_unrecordable_pass_still_allows_stop_and_reports_the_pass(self):
        outcome, payload = run(stop(), Sensor(passing()), BrokenStore("save"))

        assert outcome.exit_code == 0
        assert "decision" not in payload
        assert "ARCHITECTURE CHECK PASSED" in payload["systemMessage"]

    def test_unwritable_state_directory_on_disk_never_blocks(self, tmp_path):
        # The state directory path is occupied by a file, so mkdir/write fail with
        # a real OSError, as with an unwritable .claude/architecture-gate/.
        blocker = tmp_path / "state"
        blocker.write_text("not a directory")
        store, sensor = FileStateStore(blocker), Sensor(violating())

        for _ in range(5):
            outcome, payload = run(stop(), sensor, store)
            assert outcome.exit_code == 0
            assert "decision" not in payload
            assert "UNRESOLVED" in payload["systemMessage"]

    def test_failed_reset_on_user_prompt_does_not_block_the_prompt(self):
        outcome, payload = run(prompt(), Sensor(passing()), BrokenStore("delete"))

        assert outcome.exit_code == 0
        assert "decision" not in (payload or {})
        assert "could not reset" in payload["systemMessage"]

    def test_unexpected_store_exception_types_are_contained(self):
        store = BrokenStore("load", "save", error=RuntimeError("weird backend"))
        outcome, payload = run(stop(), Sensor(violating()), store)

        assert outcome.exit_code == 0
        assert "decision" not in payload
        assert "UNRESOLVED" in payload["systemMessage"]


class TestProperties:
    @given(st.text(min_size=1))
    def test_session_key_is_a_safe_filename(self, session_id):
        key = session_key(session_id)
        assert len(key) == 32 and all(c in "0123456789abcdef" for c in key)

    @given(st.text(min_size=1), st.text(min_size=1))
    def test_distinct_sessions_get_distinct_keys(self, a, b):
        if a != b:
            assert session_key(a) != session_key(b)

    @given(st.text())
    def test_arbitrary_input_never_raises_and_always_emits_valid_json(self, raw):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory(dir=".tmp" if Path(".tmp").is_dir() else None) as d:
            outcome = handle_event(raw, run_sensor=Sensor(violating()),
                                   store=FileStateStore(Path(d)), max_repairs=2)
        assert outcome.exit_code == 0
        if outcome.stdout:
            json.loads(outcome.stdout)


class TestSemanticStage:
    """Arm C's optional semantic stage. The judge is injected; nothing is called."""

    @staticmethod
    def judge_returning(*outcomes):
        from gates.semantic import JudgeOutcome  # noqa: F401  (documents the type)

        calls = []

        def run():
            calls.append(1)
            outcome = outcomes[min(len(calls) - 1, len(outcomes) - 1)]
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        run.calls = calls
        return run

    @staticmethod
    def outcome(status, provider_failed=False):
        from gates.semantic import Finding, JudgeOutcome

        findings = (Finding("src/orders/controllers/orders.py", 3, 4, "discount rule"),) \
            if status == "violation" else ()
        return JudgeOutcome(status, f"{status} reason", findings, provider_failed=provider_failed)

    def run(self, raw, sensor, store, judge, max_repairs=3):
        outcome = handle_event(raw, run_sensor=sensor, store=store, max_repairs=max_repairs,
                               run_semantic=judge)
        return outcome, (json.loads(outcome.stdout) if outcome.stdout else None)

    def test_structural_failure_never_reaches_the_judge(self, store):
        judge = self.judge_returning(self.outcome("pass"))

        _, payload = self.run(stop(), Sensor(violating()), store, judge)

        assert payload["decision"] == "block"
        assert judge.calls == []

    def test_semantic_violation_requests_a_repair_from_the_same_budget(self, store):
        judge = self.judge_returning(self.outcome("violation"))

        _, payload = self.run(stop(), Sensor(passing()), store, judge)

        assert payload["decision"] == "block"
        assert "SEMANTIC VIOLATION" in payload["reason"]
        state = store.load(session_key("s1"))
        assert (state.repairs_requested, state.last_status) == (1, "violation")

    def test_semantic_violations_exhaust_the_budget_and_end_unresolved(self, store):
        judge = self.judge_returning(self.outcome("violation"))
        for _ in range(2):
            self.run(stop(active=True), Sensor(passing()), store, judge, max_repairs=2)

        _, payload = self.run(stop(active=True), Sensor(passing()), store, judge, max_repairs=2)

        assert "decision" not in payload
        assert "UNRESOLVED" in payload["systemMessage"]
        assert store.load(session_key("s1")).outcome == "unresolved"

    def test_semantic_pass_allows_the_stop_and_says_a_pass_can_be_wrong(self, store):
        _, payload = self.run(stop(), Sensor(passing()), store, self.judge_returning(self.outcome("pass")))

        assert "decision" not in payload
        assert "can be wrong" in payload["systemMessage"]
        assert store.load(session_key("s1")).outcome == "passed"

    @pytest.mark.parametrize("failed", [False, True])
    def test_abstention_or_judge_failure_ends_without_a_pass(self, store, failed):
        judge = self.judge_returning(self.outcome("inconclusive", provider_failed=failed))

        _, payload = self.run(stop(), Sensor(passing()), store, judge)

        assert "decision" not in payload
        assert "INCONCLUSIVE (not a pass)" in payload["systemMessage"]
        assert store.load(session_key("s1")).outcome == "semantic_inconclusive"

    def test_a_crashing_judge_is_inconclusive_not_a_pass(self, store):
        _, payload = self.run(stop(), Sensor(passing()), store,
                              self.judge_returning(RuntimeError("boom")))

        assert "decision" not in payload
        assert store.load(session_key("s1")).outcome == "semantic_inconclusive"
