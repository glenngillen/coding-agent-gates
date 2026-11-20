"""Independent final evaluator. Processes are mocked; files live in tmp_path only
(apart from read-only reads of the example's committed frozen files)."""

import json
import subprocess
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from evaluator import evaluate as ev
from gates.result import SensorResult, Status
from gates.semantic import JudgeOutcome

JUNIT_PASS = '<testsuites><testsuite tests="3" failures="0" errors="0" skipped="0"/></testsuites>'
JUNIT_FAIL = '<testsuites><testsuite tests="3" failures="1" errors="0" skipped="0"/></testsuites>'


def run(status, tests=3):
    return ev.TestRun(status, tests, 0, 0, 0, 0)


class TestClassifyTestRun:
    def test_exit_zero_with_tests_is_a_pass(self):
        assert ev.classify_test_run(0, JUNIT_PASS).status == "pass"

    def test_exit_one_with_failures_is_a_fail(self):
        assert ev.classify_test_run(1, JUNIT_FAIL).status == "fail"

    @pytest.mark.parametrize(("code", "junit"), [
        (0, None),  # no report
        (0, '<testsuite tests="0" failures="0" errors="0"/>'),  # nothing ran
        (2, JUNIT_FAIL),  # interrupted / collection error
        (5, JUNIT_PASS),  # no tests collected
        (1, JUNIT_PASS),  # exit and report disagree
        (0, JUNIT_FAIL),
        (None, JUNIT_PASS),
        (0, "not xml"),
    ])
    def test_everything_else_is_an_error_never_a_pass(self, code, junit):
        assert ev.classify_test_run(code, junit).status == "error"


class TestBehaviorStatus:
    def test_both_must_pass(self):
        assert ev.behavior_status(run("pass"), run("pass")) == "pass"
        assert ev.behavior_status(run("pass"), run("fail")) == "fail"
        assert ev.behavior_status(run("fail"), run("pass")) == "fail"

    def test_any_error_is_an_error(self):
        assert ev.behavior_status(run("error"), run("fail")) == "error"
        assert ev.behavior_status(run("pass"), run("error")) == "error"


class TestRunTests:
    def test_runs_only_against_the_snapshot_source_with_an_isolated_config(self, tmp_path):
        test_file = tmp_path / "test_x.py"
        test_file.write_text("def test_x(): pass\n")
        seen = {}

        def runner(argv, *, cwd, env, **kwargs):
            seen.update(argv=argv, cwd=cwd, env=env)
            (Path(cwd) / "junit.xml").write_text(JUNIT_PASS)
            return subprocess.CompletedProcess(argv, 0, "3 passed", "")

        result = ev.run_tests(tmp_path / "snap", [test_file], tmp_path / "work", runner=runner)

        assert result.status == "pass"
        src = str((tmp_path / "snap" / "src").resolve())
        assert seen["env"]["PYTHONPATH"] == src
        assert seen["env"]["EVAL_SNAPSHOT_SRC"] == src
        assert "-c" in seen["argv"] and str(tmp_path / "work" / "pytest.ini") in seen["argv"]
        assert (tmp_path / "work" / "conftest.py").is_file()  # the frozen guard travels with the tests
        assert (tmp_path / "work" / "test_x.py").is_file()

    def test_a_timeout_is_an_error(self, tmp_path):
        def runner(argv, **kwargs):
            raise subprocess.TimeoutExpired(argv, 1)

        result = ev.run_tests(tmp_path / "snap", [], tmp_path / "work", runner=runner)

        assert result.status == "error"

    def test_missing_report_is_an_error(self, tmp_path):
        def runner(argv, **kwargs):
            return subprocess.CompletedProcess(argv, 0, "", "")

        assert ev.run_tests(tmp_path / "snap", [], tmp_path / "work", runner=runner).status == "error"


class TestTamperReport:
    PREPARED = {
        "workspace": {"CLAUDE.md": "c1", "pyproject.toml": "p1",
                      "tests/test_order_behaviour.py": "t1", "tests/test_order_service.py": "t2"},
        "gates": {".importlinter": "g1", "src/gates/sensor.py": "g2"},
    }

    def now(self, **changes):
        ws = dict(self.PREPARED["workspace"])
        ws.update(changes)
        return {k: v for k, v in ws.items() if v is not None}

    def test_untouched_is_clean(self):
        report = ev.tamper_report(self.PREPARED, self.now(), dict(self.PREPARED["gates"]))

        assert report["detected"] is False
        assert report["baseline_tests_modified"] == []

    @pytest.mark.parametrize("change", [{"CLAUDE.md": "edited"}, {"pyproject.toml": None}])
    def test_editing_the_instruction_or_configuration_is_tampering(self, change):
        report = ev.tamper_report(self.PREPARED, self.now(**change), dict(self.PREPARED["gates"]))

        assert report["detected"] is True

    def test_editing_a_gate_file_outside_the_workspace_is_tampering(self):
        gates = {".importlinter": "edited", "src/gates/sensor.py": "g2"}

        report = ev.tamper_report(self.PREPARED, self.now(), gates)

        assert report["detected"] is True
        assert report["gate_files"]["changed"] == [".importlinter"]

    def test_adding_workspace_settings_is_tampering(self):
        report = ev.tamper_report(self.PREPARED, self.now(**{".claude/settings.json": "x"}),
                                  dict(self.PREPARED["gates"]))

        assert report["detected"] is True
        assert report["workspace_settings_added"] == [".claude/settings.json"]

    def test_changed_baseline_tests_are_reported_separately_not_as_tampering(self):
        report = ev.tamper_report(
            self.PREPARED, self.now(**{"tests/test_order_behaviour.py": "edited",
                                       "tests/test_order_service.py": None}),
            dict(self.PREPARED["gates"]))

        assert report["detected"] is False
        assert report["baseline_tests_modified"] == ["tests/test_order_behaviour.py",
                                                     "tests/test_order_service.py"]


class TestFrozenCriteria:
    def test_matching_hashes_pass(self):
        ev.check_frozen({"files": {"a": "1"}}, {"a": "1"})

    @pytest.mark.parametrize("current", [{"a": "2"}, {}, {"a": "1", "b": "1"}])
    def test_any_difference_refuses(self, current):
        with pytest.raises(ev.FrozenCriteriaChanged):
            ev.check_frozen({"files": {"a": "1"}}, current)

    @pytest.mark.parametrize("manifest", [{}, {"files": {}}, {"files": []}, []])
    def test_a_manifest_without_hashes_refuses(self, manifest):
        with pytest.raises(ev.FrozenCriteriaChanged):
            ev.check_frozen(manifest, {"a": "1"})

    def test_the_committed_manifest_matches_the_committed_files(self):
        # Read-only check of the example's own committed files.
        ev.check_frozen(ev.load_manifest(), ev.current_frozen_hashes())


class TestFileHashes:
    def test_patterns_ignore_caches_and_record_symlinks_by_target(self, tmp_path):
        (tmp_path / "src" / "orders" / "__pycache__").mkdir(parents=True)
        (tmp_path / "src" / "orders" / "a.py").write_text("x")
        (tmp_path / "src" / "orders" / "__pycache__" / "a.pyc").write_text("y")
        (tmp_path / "other.txt").write_text("z")
        (tmp_path / "CLAUDE.md").symlink_to("/elsewhere")

        hashes = ev.file_hashes(tmp_path, ("src/**", "CLAUDE.md"))

        assert set(hashes) == {"src/orders/a.py", "CLAUDE.md"}
        assert hashes["CLAUDE.md"] == "symlink:/elsewhere"


class TestEvaluateSnapshot:
    """The whole evaluation with every boundary mocked."""

    def setup_snapshot(self, tmp_path):
        snap = tmp_path / "snap"
        (snap / "src" / "orders" / "controllers").mkdir(parents=True)
        (snap / "src" / "orders" / "controllers" / "orders.py").write_text("x = 1\n")
        (snap / "CLAUDE.md").write_text("rules")
        return snap

    def evaluate(self, tmp_path, sensor_status, junit=JUNIT_PASS, code=0, provider=None):
        snap = self.setup_snapshot(tmp_path)
        manifest = tmp_path / "manifest.json"
        frozen_root = tmp_path / "frozen"
        (frozen_root / "experiment").mkdir(parents=True)
        (frozen_root / "experiment" / "instruction.md").write_text("i")
        manifest.write_text(json.dumps({"files": ev.current_frozen_hashes(frozen_root)}))
        acceptance = tmp_path / "test_task.py"
        acceptance.write_text("")
        calls = []

        def runner(argv, *, cwd, **kwargs):
            calls.append(argv)
            (Path(cwd) / "junit.xml").write_text(junit)
            return subprocess.CompletedProcess(argv, code, "", "")

        def sensor(root, config):
            assert config == ev.CONTRACT  # the evaluator's own contract, never the snapshot's
            rules = {"Controllers must not import infrastructure repositories directly":
                     "KEPT" if sensor_status is Status.PASS else "BROKEN"}
            return SensorResult(sensor_status, rules, (), None, "f" * 64, "2.17", 0, "")

        task = {"id": "T00-test", "acceptance_test": str(acceptance)}
        prepared = {"workspace": {"CLAUDE.md": ev.sha256_bytes(b"rules")}, "gates": {}}
        return ev.evaluate_snapshot(snap, task, prepared, workdir=tmp_path / "work", runner=runner,
                                    run_sensor=sensor, judge_provider=provider,
                                    manifest_path=manifest, root=frozen_root), calls

    def test_outcomes_are_recorded_separately(self, tmp_path):
        record, calls = self.evaluate(tmp_path, Status.VIOLATION)

        assert record["behavior"]["status"] == "pass"
        assert record["structural"]["status"] == "violation"
        assert record["tampering"]["detected"] is False
        assert len(calls) == 2  # acceptance and regression, run separately

    def test_a_final_snapshot_is_never_called_a_merge(self, tmp_path):
        record, _ = self.evaluate(tmp_path, Status.PASS)

        assert "no merge" in record["submission"]
        assert "merged" not in json.dumps(record).replace("no merge", "")

    def test_judge_output_is_never_used_as_the_label(self, tmp_path):
        def provider(request):
            return json.dumps({"verdict": "pass", "findings": [], "rationale": "ok"})

        record, _ = self.evaluate(tmp_path, Status.PASS, provider=provider)

        assert record["semantic_judge"]["status"] == "pass"
        assert record["semantic_label"] is None
        assert "no independent human labels" in record["semantic_label_note"]

    def test_the_judge_is_not_asked_about_a_structural_violation(self, tmp_path):
        asked = []

        def provider(request):
            asked.append(request)
            return "{}"

        record, _ = self.evaluate(tmp_path, Status.VIOLATION, provider=provider)

        assert asked == []
        assert record["semantic_judge"]["status"] == "not_evaluated"

    def test_changed_frozen_criteria_refuse_to_evaluate(self, tmp_path):
        snap = self.setup_snapshot(tmp_path)
        manifest = tmp_path / "manifest.json"
        manifest.write_text(json.dumps({"files": {"experiment/instruction.md": "stale"}}))
        frozen_root = tmp_path / "frozen"
        (frozen_root / "experiment").mkdir(parents=True)
        (frozen_root / "experiment" / "instruction.md").write_text("i")

        with pytest.raises(ev.FrozenCriteriaChanged):
            ev.evaluate_snapshot(snap, {"id": "T", "acceptance_test": "x"}, {}, workdir=tmp_path / "w",
                                 run_sensor=lambda *a, **k: None, manifest_path=manifest,
                                 root=frozen_root)


class TestJudgeJson:
    def test_provider_failure_is_kept_visible(self):
        out = ev.judge_json(JudgeOutcome("inconclusive", "provider unavailable: x", provider_failed=True))

        assert out["status"] == "inconclusive"
        assert out["provider_failed"] is True


class TestProperties:
    @given(st.text())
    def test_parse_junit_never_raises(self, text):
        result = ev.parse_junit(text)
        assert result is None or all(isinstance(n, int) and n >= 0 for n in result)

    @given(st.lists(st.tuples(*(st.integers(0, 50),) * 4), min_size=1, max_size=5))
    def test_parse_junit_sums_suites(self, suites):
        xml = "<testsuites>" + "".join(
            f'<testsuite tests="{t}" failures="{f}" errors="{e}" skipped="{s}"/>' for t, f, e, s in suites
        ) + "</testsuites>"
        assert ev.parse_junit(xml) == tuple(sum(col) for col in zip(*suites))

    @given(st.integers(-3, 10) | st.none(), st.sampled_from([JUNIT_PASS, JUNIT_FAIL, None, "x"]))
    def test_a_pass_requires_exit_zero_and_a_clean_report(self, code, junit):
        if ev.classify_test_run(code, junit).status == "pass":
            assert code == 0 and junit == JUNIT_PASS

    @given(st.dictionaries(st.text(min_size=1, max_size=5), st.text(max_size=5), max_size=6),
           st.dictionaries(st.text(min_size=1, max_size=5), st.text(max_size=5), max_size=6))
    def test_compare_hashes_partitions_every_key(self, before, after):
        diff = ev.compare_hashes(before, after)
        unchanged = {k for k in before.keys() & after.keys() if before[k] == after[k]}
        assert set(diff["changed"]) | set(diff["added"]) | set(diff["removed"]) | unchanged == \
            before.keys() | after.keys()
        assert not set(diff["changed"]) & unchanged

    @given(st.dictionaries(st.text(min_size=1, max_size=8), st.text(max_size=8), max_size=8))
    def test_tree_hash_is_order_independent(self, hashes):
        assert ev.tree_hash(hashes) == ev.tree_hash(dict(reversed(list(hashes.items()))))
