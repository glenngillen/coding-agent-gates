"""Run preparation for arms A/B/C. Git is mocked; the example tree is a tmp_path replica."""

import json
import subprocess
from collections import Counter

import pytest
from hypothesis import given
from hypothesis import strategies as st

import prepare_run as pr

ARMS = pr.load_arms()  # read-only: the committed arm definitions


def fake_root(tmp_path):
    root = tmp_path / "example"
    for rel, text in {
        "src/orders/__init__.py": "", "src/orders/controllers/orders.py": "x = 1\n",
        "src/gates/sensor.py": "s", "src/gates/stop_hook.py": "h",
        "tests/unit/orders/test_order_behaviour.py": "b", "tests/unit/orders/test_order_service.py": "v",
        "experiment/instruction.md": "rules\n", "experiment/tools/spend_ledger.py": "l",
        "experiment/tools/experiment_stop_hook.py": "e", "experiment/evaluator/evaluate.py": "secret",
        "experiment/evaluator/acceptance/test_t01.py": "secret", ".importlinter": "[importlinter]\n",
        "semantic/rubric.md": "r", "integrations/check_architecture.py": "c",
    }.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    (root / ".venv").mkdir()
    return root


class FakeGit:
    def __init__(self):
        self.calls = []

    def __call__(self, argv, *, cwd, env, **kwargs):
        self.calls.append(argv)
        out = "abc123\n" if "rev-parse" in argv else ""
        return subprocess.CompletedProcess(argv, 0, out, "")


TASK = {"id": "T01-lookup", "request": "Add a lookup."}


def prepare(tmp_path, arm, which=lambda name: f"/bin/{name}"):
    root = fake_root(tmp_path)
    git = FakeGit()
    prepared = pr.prepare(TASK, arm, 1, pilot="p", arms=ARMS, root=root, work_dir=tmp_path / "work",
                          runs_dir=tmp_path / "runs", ledger=tmp_path / "ledger.json", git=git,
                          which=which, python="/venv/python")
    return prepared, root, git


class TestPlanOrder:
    def test_every_task_gets_every_arm_once_per_repeat(self):
        plan = pr.plan_order(["T1", "T2", "T3"], ["A", "B", "C"], seed=7, repeats=2)

        assert Counter((p["task_id"], p["repeat"]) for p in plan) == {
            (t, r): 3 for t in ("T1", "T2", "T3") for r in (1, 2)}
        for t in ("T1", "T2", "T3"):
            arms = [p["arm"] for p in plan if p["task_id"] == t and p["repeat"] == 1]
            assert sorted(arms) == ["A", "B", "C"]

    def test_the_seed_fixes_the_order(self):
        assert pr.plan_order(["T1", "T2"], ["A", "B", "C"], 3) == pr.plan_order(["T1", "T2"], ["A", "B", "C"], 3)

    @given(st.integers(0, 10_000), st.integers(1, 12), st.integers(1, 3))
    def test_plan_properties(self, seed, n_tasks, repeats):
        tasks = [f"T{i:02d}" for i in range(n_tasks)]
        plan = pr.plan_order(tasks, ["A", "B", "C"], seed, repeats)

        assert [p["sequence"] for p in plan] == list(range(1, len(plan) + 1))
        assert len({p["run_id"] for p in plan}) == len(plan) == 3 * n_tasks * repeats
        assert all(p["position_in_task"] in (1, 2, 3) for p in plan)


class TestArmDifferences:
    def settings(self, arm, tmp_path):
        return pr.settings_for(arm, ARMS, workspace=tmp_path / "ws", state_dir=tmp_path / "s",
                               events=tmp_path / "e.jsonl", rid="r", ledger=tmp_path / "l.json",
                               python="/py")

    def test_arm_a_has_no_hook(self, tmp_path):
        assert self.settings("A", tmp_path) == {"autoMemoryEnabled": False}

    def test_arm_b_runs_the_sensor_only(self, tmp_path):
        args = self.settings("B", tmp_path)["hooks"]["Stop"][0]["hooks"][0]["args"]

        assert "--semantic" not in args and "--ledger" not in args
        assert args[args.index("--max-repairs") + 1] == "3"

    def test_arm_c_adds_only_the_semantic_stage(self, tmp_path):
        b = self.settings("B", tmp_path)["hooks"]["Stop"][0]["hooks"][0]
        c = self.settings("C", tmp_path)["hooks"]["Stop"][0]["hooks"][0]

        extra = [a for a in c["args"] if a not in b["args"]]
        assert extra == ["--semantic", "--ledger", str(tmp_path / "l.json")]

    def test_agent_command_is_identical_apart_from_the_settings_file(self, tmp_path):
        argv = {arm: pr.agent_argv(ARMS, settings_path=tmp_path / arm / "settings.json",
                                   instruction_path=tmp_path / "CLAUDE.md") for arm in "ABC"}

        def without_settings(a):
            i = a.index("--settings")
            return a[:i] + a[i + 2:]

        assert without_settings(argv["A"]) == without_settings(argv["B"]) == without_settings(argv["C"])
        assert argv["A"][argv["A"].index("--model") + 1] == ARMS["agent"]["model"]
        assert argv["A"][argv["A"].index("--setting-sources") + 1] == ""

    def test_prompt_is_identical_in_every_arm(self):
        assert pr.prompt_for(TASK, ARMS).startswith(TASK["request"])


class TestPrepare:
    def test_workspace_holds_only_the_application_and_its_tests(self, tmp_path):
        prepared, _, _ = prepare(tmp_path, "B")
        ws = tmp_path / "work" / "p" / "T01-lookup__B__r1" / "workspace"

        files = {p.relative_to(ws).as_posix() for p in ws.rglob("*") if p.is_file() and ".venv" not in p.parts}
        assert files == {"src/orders/__init__.py", "src/orders/controllers/orders.py",
                         "tests/test_order_behaviour.py", "tests/test_order_service.py",
                         "CLAUDE.md", "pyproject.toml", ".gitignore"}
        assert (ws / "CLAUDE.md").read_text() == "rules\n"
        assert (ws / ".venv").is_symlink()
        assert prepared["baseline_commit"] == "abc123"

    def test_records_workspace_and_gate_hashes_for_tamper_detection(self, tmp_path):
        prepared, _, _ = prepare(tmp_path, "C")

        assert set(prepared["workspace"]) == {"CLAUDE.md", "pyproject.toml",
                                              "tests/test_order_behaviour.py", "tests/test_order_service.py"}
        assert {".importlinter", "semantic/rubric.md", "src/gates/sensor.py",
                "experiment/tools/experiment_stop_hook.py"} <= set(prepared["gates"])
        assert not any("evaluator" in k for k in prepared["gates"])

    def test_settings_file_sits_outside_the_workspace(self, tmp_path):
        prepared, _, _ = prepare(tmp_path, "B")

        settings = tmp_path / "work" / "p" / "T01-lookup__B__r1" / "settings.json"
        assert json.loads(settings.read_text()) == prepared["settings"]
        assert prepared["paths"]["workspace"] not in str(settings.parent) + "/"

    def test_baseline_is_committed_with_a_fixed_identity(self, tmp_path):
        _, _, git = prepare(tmp_path, "A")

        assert [c[c.index("init.defaultBranch=main") + 1] for c in git.calls] == ["init", "add", "commit", "rev-parse"]

    def test_no_cli_at_all_is_not_runnable(self, tmp_path):
        with pytest.raises(pr.NotRunnable):
            prepare(tmp_path, "C", which=lambda name: None)

    def test_arm_c_refuses_when_only_the_judge_is_missing(self, tmp_path):
        arms = json.loads(json.dumps(ARMS))
        arms["agent"]["cli"] = "agent-cli"
        root = fake_root(tmp_path)

        with pytest.raises(pr.NotRunnable, match="not replaced by an arm B run"):
            pr.prepare(TASK, "C", 1, pilot="p", arms=arms, root=root, work_dir=tmp_path / "w",
                       runs_dir=tmp_path / "r", git=FakeGit(),
                       which=lambda name: "/bin/agent-cli" if name == "agent-cli" else None)

    def test_a_workspace_is_never_reused(self, tmp_path):
        prepare(tmp_path, "A")
        with pytest.raises(pr.NotRunnable, match="never reuse"):
            pr.prepare(TASK, "A", 1, pilot="p", arms=ARMS, root=tmp_path / "example",
                       work_dir=tmp_path / "work", runs_dir=tmp_path / "runs", git=FakeGit(),
                       which=lambda n: "/bin/x")

    def test_unknown_arm_is_refused(self, tmp_path):
        with pytest.raises(pr.NotRunnable):
            prepare(tmp_path, "D")
