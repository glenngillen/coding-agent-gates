"""Unit tests for the local CI simulation (gates.ci_simulation).

Pure: the process runner is injected, and filesystem work happens only inside
pytest's tmp_path (under the gitignored .tmp/). The committed example workflow
is read, never executed.
"""

from pathlib import Path

import pytest
import yaml
from hypothesis import given, strategies as st

from gates.ci_simulation import (
    Completed,
    JobPlan,
    UnsupportedWorkflow,
    extract_snapshots,
    plan_job,
    run_job,
    tail,
    tree_digest,
    version_matches,
)

ROOT = Path(__file__).resolve().parents[3]


def workflow(steps, **job_extra):
    job = {"name": "architecture-contracts", "runs-on": "ubuntu-latest",
           "timeout-minutes": 10, "steps": steps, **job_extra}
    return {"name": "architecture", "jobs": {"architecture-contracts": job}}


STEPS = [
    {"uses": "actions/checkout@v6"},
    {"uses": "actions/setup-python@v5", "with": {"python-version-file": ".python-version"}},
    {"name": "Install pinned environment", "run": "python -m venv .venv\n"},
    {"name": "Check architecture contracts (full package)",
     "run": ".venv/bin/python integrations/check_architecture.py"},
]


class TestPlanJob:
    def test_committed_example_workflow_is_fully_supported(self):
        wf = yaml.safe_load((ROOT / "integrations/github-actions.yaml").read_text())
        plan = plan_job(wf, "architecture-contracts")
        assert plan.check_name == "architecture-contracts"
        assert [s.kind for s in plan.steps] == ["checkout", "setup-python", "run", "run"]
        assert plan.steps[1].python_version_file == ".python-version"
        assert plan.steps[-1].run == ".venv/bin/python integrations/check_architecture.py"

    def test_names_unnamed_steps_like_github(self):
        plan = plan_job(workflow(STEPS), "architecture-contracts")
        assert plan.steps[0].name == "Run actions/checkout@v6"
        assert plan.steps[2].name == "Install pinned environment"
        unnamed = plan_job(workflow([{"run": "echo one\necho two"}]), "architecture-contracts")
        assert unnamed.steps[0].name == "Run echo one"

    def test_workflow_default_working_directory_applies_to_run_steps_only(self):
        wf = workflow(STEPS)
        wf["defaults"] = {"run": {"working-directory": "examples/x"}}
        plan = plan_job(wf, "architecture-contracts")
        assert plan.steps[2].working_directory == "examples/x"
        assert plan.steps[0].working_directory == "."
        assert plan.steps[1].working_directory == "."

    def test_step_working_directory_overrides_default(self):
        wf = workflow([{"run": "true", "working-directory": "sub"}])
        wf["defaults"] = {"run": {"working-directory": "examples/x"}}
        assert plan_job(wf, "architecture-contracts").steps[0].working_directory == "sub"

    def test_job_name_falls_back_to_id(self):
        wf = workflow([{"run": "true"}])
        del wf["jobs"]["architecture-contracts"]["name"]
        assert plan_job(wf, "architecture-contracts").check_name == "architecture-contracts"

    @pytest.mark.parametrize("bad, why", [
        ({"uses": "actions/cache@v4"}, "actions/cache"),
        ({"run": "echo ${{ github.sha }}"}, "expression"),
        ({"run": "true", "if": "always()"}, "if"),
        ({"run": "true", "env": {"A": "1"}}, "env"),
        ({"run": "true", "shell": "pwsh"}, "shell"),
        ({"uses": "actions/setup-python@v5", "with": {"python-version": "3.12"}}, "python-version-file"),
        ({"name": "nothing"}, "run or uses"),
        ({"run": "true", "uses": "actions/checkout@v4"}, "both"),
    ])
    def test_rejects_what_it_cannot_reproduce(self, bad, why):
        with pytest.raises(UnsupportedWorkflow, match=why):
            plan_job(workflow([bad]), "architecture-contracts")

    @pytest.mark.parametrize("extra", [{"needs": "x"}, {"if": "true"}, {"strategy": {}},
                                       {"services": {}}, {"env": {"A": "1"}}])
    def test_rejects_unsupported_job_keys(self, extra):
        with pytest.raises(UnsupportedWorkflow):
            plan_job(workflow(STEPS, **extra), "architecture-contracts")

    def test_missing_job_names_the_available_ones(self):
        with pytest.raises(UnsupportedWorkflow, match="architecture-contracts"):
            plan_job(workflow(STEPS), "nope")


class FakeRunner:
    """Returns scripted results keyed on a substring of the step script."""

    def __init__(self, results, version="3.12.15"):
        self.results = results
        self.version = version
        self.calls = []

    def __call__(self, argv, cwd, env, timeout):
        self.calls.append({"argv": argv, "cwd": cwd, "env": env, "timeout": timeout})
        if len(argv) == 3 and argv[1] == "-c" and "version_info" in argv[2]:
            return Completed(0, f"{self.version}\n/opt/python3.12/bin/python3.12\n", False)
        script = Path(argv[-1]).read_text()
        for needle, result in self.results.items():
            if needle in script:
                return result
        return Completed(0, "", False)


def clock():
    t = [0.0]

    def tick():
        t[0] += 0.5
        return t[0]

    return tick


def make_workspace(tmp_path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / ".python-version").write_text("3.12\n")
    return ws


def run(tmp_path, runner, steps=STEPS):
    plan = plan_job(workflow(steps), "architecture-contracts")
    ws = make_workspace(tmp_path)
    return run_job(plan, ws, sim_root=tmp_path / "sim", python="/usr/bin/python3.12",
                   runner=runner, clock=clock(), base_env={"PATH": "/usr/bin", "VIRTUAL_ENV": "/x"})


class TestRunJob:
    def test_success_runs_every_step(self, tmp_path):
        runner = FakeRunner({"check_architecture": Completed(0, "ARCHITECTURE CHECK PASSED (snapshot 470476b02ddd): rule\n", False)})
        result = run(tmp_path, runner)
        assert result["conclusion"] == "success"
        assert result["failing_step"] is None
        assert [s["outcome"] for s in result["steps"]] == ["success"] * 4
        assert result["steps"][-1]["snapshots"] == ["470476b02ddd"]

    def test_failure_stops_the_job_and_skips_later_steps(self, tmp_path):
        runner = FakeRunner({"venv": Completed(1, "boom", False)})
        result = run(tmp_path, runner)
        assert result["conclusion"] == "failure"
        assert result["failing_step"] == "Install pinned environment"
        assert [s["outcome"] for s in result["steps"]] == ["success", "success", "failure", "skipped"]
        assert result["steps"][3]["exit"] is None
        assert not any("check_architecture" in Path(c["argv"][-1]).read_text()
                       for c in runner.calls if c["argv"][0] == "bash")

    def test_violation_exit_is_the_failing_named_check(self, tmp_path):
        runner = FakeRunner({"check_architecture": Completed(1, "ARCHITECTURE CHECK FAILED (snapshot abcdefabcdef)\n", False)})
        result = run(tmp_path, runner)
        assert result["conclusion"] == "failure"
        assert result["failing_step"] == "Check architecture contracts (full package)"
        assert result["steps"][-1]["exit"] == 1
        assert result["check_name"] == "architecture-contracts"

    def test_timeout_is_not_a_pass(self, tmp_path):
        runner = FakeRunner({"check_architecture": Completed(None, "", True)})
        result = run(tmp_path, runner)
        assert result["conclusion"] == "timed_out"
        assert result["steps"][-1]["outcome"] == "timed_out"

    def test_wrong_interpreter_version_fails_setup_python(self, tmp_path):
        runner = FakeRunner({}, version="3.11.9")
        result = run(tmp_path, runner)
        assert result["failing_step"] == "Run actions/setup-python@v5"
        assert "3.12" in result["steps"][1]["output_tail"]
        assert all(c["argv"][0] != "bash" for c in runner.calls)

    def test_run_steps_use_github_bash_flags_and_the_pinned_python_first_on_path(self, tmp_path):
        runner = FakeRunner({})
        run(tmp_path, runner)
        bash = [c for c in runner.calls if c["argv"][0] == "bash"]
        assert bash[0]["argv"][:5] == ["bash", "--noprofile", "--norc", "-eo", "pipefail"]
        env = bash[0]["env"]
        bindir = env["PATH"].split(":")[0]
        assert (Path(bindir) / "python").resolve() == Path("/opt/python3.12/bin/python3.12")
        assert "VIRTUAL_ENV" not in env
        assert env["CI"] == "true"
        assert "GITHUB_ACTIONS" not in env

    def test_run_step_timeout_is_the_remaining_job_budget(self, tmp_path):
        runner = FakeRunner({})
        run(tmp_path, runner)
        bash = [c for c in runner.calls if c["argv"][0] == "bash"]
        assert all(0 < c["timeout"] <= 600 for c in bash)


class TestHelpers:
    def test_extract_snapshots(self):
        text = "ARCHITECTURE CHECK PASSED (snapshot 0123456789ab): x\nSnapshot: 0123456789ab\nSnapshot: ba9876543210\n"
        assert extract_snapshots(text) == ["0123456789ab", "ba9876543210"]

    def test_tail_keeps_the_last_lines(self):
        text = "\n".join(str(i) for i in range(100))
        kept, total = tail(text, 3)
        assert kept == "97\n98\n99" and total == 100


class TestProperties:
    @given(st.recursive(st.none() | st.booleans() | st.integers() | st.text(max_size=8),
                        lambda c: st.lists(c, max_size=4) | st.dictionaries(st.text(max_size=8), c, max_size=4),
                        max_leaves=20),
           st.text(max_size=8))
    def test_plan_job_accepts_or_rejects_cleanly(self, wf, job):
        try:
            plan = plan_job(wf, job)
        except UnsupportedWorkflow:
            return
        assert isinstance(plan, JobPlan)
        assert all(s.kind in {"checkout", "setup-python", "run"} for s in plan.steps)

    @given(st.dictionaries(st.text(min_size=1, max_size=12), st.binary(max_size=32), max_size=8))
    def test_tree_digest_ignores_order(self, files):
        items = list(files.items())
        assert tree_digest(items) == tree_digest(list(reversed(items)))

    @given(st.dictionaries(st.text(min_size=1, max_size=12), st.binary(max_size=32), min_size=1, max_size=8),
           st.binary(min_size=1, max_size=8))
    def test_tree_digest_sees_content_changes(self, files, extra):
        items = list(files.items())
        path, content = items[0]
        changed = [(path, content + extra)] + items[1:]
        assert tree_digest(items) != tree_digest(changed)

    @given(st.integers(0, 20), st.integers(0, 20), st.integers(0, 99))
    def test_version_prefix_matches(self, major, minor, patch):
        assert version_matches(f"{major}.{minor}", f"{major}.{minor}.{patch}")
        assert not version_matches(f"{major}.{minor + 1}", f"{major}.{minor}.{patch}")
