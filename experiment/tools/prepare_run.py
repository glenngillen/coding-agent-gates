#!/usr/bin/env python3
"""Prepare isolated runs for the three study arms.

    .venv/bin/python experiment/tools/prepare_run.py plan --pilot NAME --seed N
    .venv/bin/python experiment/tools/prepare_run.py prepare --pilot NAME --task T01-lookup --arm B

``plan`` fixes the run order: tasks in their frozen order, the three arms in a
random order within each task (``random.Random(seed)``), one repeat. The plan
is written to ``experiment/runs/<pilot>/order.json`` before any run starts.

``prepare`` creates one run's isolated workspace under ``.tmp/runs/<pilot>/``:

- a clean copy of the baseline order service (``src/orders``), its two test
  modules, a minimal ``pyproject.toml``, the frozen instruction file as
  ``CLAUDE.md`` and a ``.venv`` link to this example's environment, committed
  to a fresh Git repository so the final diff is exact;
- no gate code, contract, rubric, fixtures, evaluator files or experiment
  tooling. Every arm gets the same workspace. The arms differ only in the
  ``--settings`` file written next to (not inside) the workspace: none for A,
  the Stop hook with the structural sensor for B, the same hook plus the
  semantic stage for C.

It records hashes of the workspace and of every out-of-workspace gate file in
``prepared.json`` so the evaluator can detect tampering. Arm C refuses to
prepare when the ``claude`` CLI the judge needs is missing: such a run is not
runnable and is never turned into an arm B run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
TOOLS = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "experiment"), str(TOOLS)]

from evaluator import evaluate as ev  # noqa: E402

ARMS_PATH = ROOT / "experiment" / "arms.json"
TASKS_DIR = ROOT / "experiment" / "tasks"
RUNS_DIR = ROOT / "experiment" / "runs"
WORK_DIR = ROOT / ".tmp" / "runs"
HOOK = TOOLS / "experiment_stop_hook.py"
LEDGER = ROOT / "experiment" / "runs" / "spend-ledger.json"
PREPARED_SCHEMA = "coding-agent-gates/prepared-run/v1"

WORKSPACE_PYPROJECT = """\
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
addopts = ["-p", "no:cacheprovider"]
"""
WORKSPACE_GITIGNORE = "__pycache__/\n*.py[cod]\n.venv\n"
BASELINE_DATE = "2026-11-19T00:00:00+00:00"
GIT_IDENTITY = ["-c", "user.name=experiment", "-c", "user.email=experiment@example.invalid",
                "-c", "commit.gpgsign=false", "-c", "init.defaultBranch=main"]


class NotRunnable(Exception):
    """The run cannot be prepared as specified (for example, arm C without a judge)."""


def load_arms(path: Path = ARMS_PATH) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_tasks(directory: Path = TASKS_DIR) -> list[dict[str, Any]]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(Path(directory).glob("*.json"))]


def run_id(task_id: str, arm: str, repeat: int) -> str:
    return f"{task_id}__{arm}__r{repeat}"


def plan_order(task_ids: Sequence[str], arms: Sequence[str], seed: int, repeats: int = 1) -> list[dict]:
    """Tasks keep their frozen order; arms are shuffled within each task and repeat."""
    rng = random.Random(seed)
    plan, sequence = [], 0
    for repeat in range(1, repeats + 1):
        for task_id in task_ids:
            order = list(arms)
            rng.shuffle(order)
            for position, arm in enumerate(order, 1):
                sequence += 1
                plan.append({"sequence": sequence, "task_id": task_id, "arm": arm, "repeat": repeat,
                             "position_in_task": position, "run_id": run_id(task_id, arm, repeat)})
    return plan


def gate_paths(root: Path = ROOT) -> dict[str, Path]:
    """Every development-time gate file outside the workspace, keyed by path relative to ``root``."""
    paths = [root / ".importlinter", root / "semantic" / "rubric.md", root / HOOK.relative_to(ROOT),
             root / "experiment" / "tools" / "spend_ledger.py"]
    paths += sorted((root / "src" / "gates").glob("*.py"))
    return {p.relative_to(root).as_posix(): p for p in paths}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prompt_for(task: dict[str, Any], arms: dict[str, Any]) -> str:
    """Identical framing in every arm: the task's request plus the frozen suffix."""
    return task["request"] + arms["prompt_suffix"]


def settings_for(arm: str, arms: dict[str, Any], *, workspace: Path, state_dir: Path, events: Path,
                 rid: str, ledger: Path, python: str) -> dict[str, Any]:
    """The run's ``--settings`` file: auto-memory off, plus the arm's Stop hook (if any)."""
    settings: dict[str, Any] = {"autoMemoryEnabled": False}
    hook = arms["arms"][arm]["stop_hook"]
    if hook is None:
        return settings
    args = [str(HOOK), "--workspace", str(workspace), "--state-dir", str(state_dir),
            "--events", str(events), "--run-id", rid, "--max-repairs", str(arms["max_repairs"])]
    if hook.get("semantic"):
        args += ["--semantic", "--ledger", str(ledger)]
    settings["hooks"] = {"Stop": [{"hooks": [{
        "type": "command", "command": python, "args": args,
        # The judge's own timeout is 180 s; the sensor's is 120 s.
        "timeout": 330 if hook.get("semantic") else 150,
        "onFailure": "continue",
    }]}]}
    return settings


def agent_argv(arms: dict[str, Any], *, settings_path: Path, instruction_path: Path) -> list[str]:
    a = arms["agent"]
    return [a["cli"], "-p", "--model", a["model"], "--effort", a["effort"],
            "--output-format", a["output_format"], "--verbose",
            "--no-session-persistence", "--setting-sources", a["setting_sources"],
            "--settings", str(settings_path),
            "--append-system-prompt-file", str(instruction_path),
            "--tools", ",".join(a["tools"]),
            "--allowedTools", *a["allowed_tools"],
            "--disallowedTools", *a["disallowed_tools"],
            *(["--disable-slash-commands"] if a.get("disable_slash_commands") else []),
            "--permission-mode", a["permission_mode"],
            "--permission-prompts", a["permission_prompts"],
            "--max-budget-usd", a["max_budget_usd"]]


GitRunner = Callable[..., Any]


def _git(runner: GitRunner, workspace: Path, *args: str) -> str:
    env = {**os.environ, "GIT_AUTHOR_DATE": BASELINE_DATE, "GIT_COMMITTER_DATE": BASELINE_DATE}
    proc = runner(["git", *GIT_IDENTITY, *args], cwd=workspace, env=env, capture_output=True,
                  text=True, check=True)
    return (proc.stdout or "").strip()


def build_workspace(workspace: Path, *, root: Path = ROOT, instruction: Path | None = None,
                    git: GitRunner = subprocess.run) -> str:
    """Create the clean workspace and commit it. Returns the baseline commit id."""
    if workspace.exists():
        raise NotRunnable(f"workspace already exists: {workspace} (runs never reuse a workspace)")
    workspace.mkdir(parents=True)
    shutil.copytree(root / "src" / "orders", workspace / "src" / "orders",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    (workspace / "tests").mkdir()
    for name in ("test_order_behaviour.py", "test_order_service.py"):
        shutil.copy2(root / "tests" / "unit" / "orders" / name, workspace / "tests" / name)
    shutil.copy2(instruction or root / "experiment" / "instruction.md", workspace / "CLAUDE.md")
    (workspace / "pyproject.toml").write_text(WORKSPACE_PYPROJECT, encoding="utf-8")
    (workspace / ".gitignore").write_text(WORKSPACE_GITIGNORE, encoding="utf-8")
    (workspace / ".venv").symlink_to(root / ".venv", target_is_directory=True)
    _git(git, workspace, "init", "-q")
    _git(git, workspace, "add", "-A")
    _git(git, workspace, "commit", "-q", "-m", "baseline")
    return _git(git, workspace, "rev-parse", "HEAD")


def prepare(task: dict[str, Any], arm: str, repeat: int, *, pilot: str, arms: dict[str, Any],
            plan_entry: dict[str, Any] | None = None, root: Path = ROOT, work_dir: Path = WORK_DIR,
            runs_dir: Path = RUNS_DIR, ledger: Path = LEDGER, git: GitRunner = subprocess.run,
            which: Callable[[str], str | None] = shutil.which,
            python: str | None = None) -> dict[str, Any]:
    if arm not in arms["arms"]:
        raise NotRunnable(f"unknown arm {arm!r}")
    hook = arms["arms"][arm]["stop_hook"]
    if which(arms["agent"]["cli"]) is None:
        raise NotRunnable(f"the agent CLI {arms['agent']['cli']!r} is not on PATH")
    if hook and hook.get("semantic") and which("claude") is None:
        raise NotRunnable("arm C needs the live judge (claude CLI), which is not on PATH; "
                          "the run is not runnable and is not replaced by an arm B run")

    rid = run_id(task["id"], arm, repeat)
    base = Path(work_dir) / pilot / rid
    workspace, state_dir = base / "workspace", base / "hook-state"
    events = base / "hook-events.jsonl"
    instruction = root / "experiment" / "instruction.md"
    commit = build_workspace(workspace, root=root, instruction=instruction, git=git)
    python = python or str(root / ".venv" / "bin" / "python")
    settings = settings_for(arm, arms, workspace=workspace, state_dir=state_dir, events=events,
                            rid=rid, ledger=ledger, python=python)
    settings_path = base / "settings.json"
    settings_path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    prompt = prompt_for(task, arms)
    gates = gate_paths(root)
    prepared = {
        "schema": PREPARED_SCHEMA,
        "prepared_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pilot": pilot, "run_id": rid, "task_id": task["id"], "arm": arm, "repeat": repeat,
        "plan": plan_entry,
        "paths": {"base": str(base), "workspace": str(workspace), "settings": str(settings_path),
                  "hook_events": str(events), "hook_state": str(state_dir),
                  "retained": str(Path(runs_dir) / pilot / rid)},
        "baseline_commit": commit,
        "workspace": ev.file_hashes(workspace, (*ev.WORKSPACE_PROTECTED, *ev.BASELINE_TESTS)),
        "workspace_tree_sha256": ev.tree_hash(ev.file_hashes(workspace, ev.SNAPSHOT_PATTERNS)),
        "gates": {rel: sha256_file(p) for rel, p in gates.items()},
        "settings": settings,
        "settings_sha256": sha256_file(settings_path),
        "prompt": prompt,
        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "task_sha256": sha256_file(root / "experiment" / "tasks" / f"{task['id']}.json")
        if (root / "experiment" / "tasks" / f"{task['id']}.json").is_file() else None,
        "instruction_sha256": sha256_file(instruction),
        "arms_sha256": sha256_file(root / "experiment" / "arms.json")
        if (root / "experiment" / "arms.json").is_file() else None,
        "agent_argv": agent_argv(arms, settings_path=settings_path, instruction_path=workspace / "CLAUDE.md"),
        "agent_config": arms["agent"],
    }
    (base / "prepared.json").write_text(json.dumps(prepared, indent=2) + "\n", encoding="utf-8")
    return prepared


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p_plan = sub.add_parser("plan")
    p_plan.add_argument("--pilot", required=True)
    p_plan.add_argument("--seed", type=int, required=True)
    p_plan.add_argument("--repeats", type=int, default=1)
    p_prep = sub.add_parser("prepare")
    p_prep.add_argument("--pilot", required=True)
    p_prep.add_argument("--task", required=True)
    p_prep.add_argument("--arm", required=True)
    p_prep.add_argument("--repeat", type=int, default=1)
    args = parser.parse_args()
    arms = load_arms()
    tasks = load_tasks()
    if args.command == "plan":
        out = RUNS_DIR / args.pilot / "order.json"
        if out.exists():
            print(f"refusing to overwrite an existing plan: {out}")
            return 1
        out.parent.mkdir(parents=True, exist_ok=True)
        plan = plan_order([t["id"] for t in tasks], sorted(arms["arms"]), args.seed, args.repeats)
        out.write_text(json.dumps({"schema": "coding-agent-gates/run-order/v1", "pilot": args.pilot,
                                   "seed": args.seed, "method": "random.Random(seed).shuffle per task",
                                   "written_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                   "runs": plan}, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {out.relative_to(ROOT)} ({len(plan)} runs)")
        return 0
    task = next((t for t in tasks if t["id"] == args.task), None)
    if task is None:
        print(f"unknown task {args.task}")
        return 2
    try:
        prepared = prepare(task, args.arm, args.repeat, pilot=args.pilot, arms=arms)
    except NotRunnable as exc:
        print(f"NOT RUNNABLE: {exc}")
        return 4
    print(json.dumps({k: prepared[k] for k in ("run_id", "baseline_commit", "paths")}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
