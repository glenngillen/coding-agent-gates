#!/usr/bin/env python3
"""Prepare isolated sessions for the version 2 study (experiment/protocol-v2.md).

    .venv/bin/python experiment/tools/prepare_v2.py plan --study NAME

``plan`` writes ``experiment/runs/<study>/order.json`` from the frozen
``experiment/v2/study.json`` (scenarios x models x arms, shuffled within each
repeat block with the frozen seed) before any session starts.

``prepare`` (called by ``run_study_v2.py``) builds one session's workspace
under ``.tmp/runs/<study>/<run_id>/``:

- the v2 baseline (``experiment/v2/baseline``), committed as the Git history
  in ``experiment/v2/history/history.json`` so the agent sees a project with
  history, including the commit that added the legacy reports controller;
- ``CLAUDE.md`` holding ``experiment/v2/instruction.md``. This is the only
  place the architecture rule is stated: the CLI runs with
  ``--setting-sources project`` so Claude Code loads it, and nothing is passed
  with ``--append-system-prompt-file`` (probe-v2-2026-11-20 checked both);
- no gate code, contract, rubric, evaluator files or experiment tooling.

Arms differ only in the ``--settings`` file written next to the workspace:
auto-memory off for every arm, plus, for B and C, the experiment Stop hook on
``Stop`` and ``UserPromptSubmit`` (the repair budget resets each turn) with the
v2 development contract and reviewed exceptions, and for C the semantic stage.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
TOOLS = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "experiment"), str(TOOLS)]

import study_v2  # noqa: E402
from evaluator import evaluate as ev  # noqa: E402
from evaluator import evaluate_v2 as ev2  # noqa: E402

V2 = ROOT / "experiment" / "v2"
STUDY_PATH = V2 / "study.json"
SCENARIOS_DIR = V2 / "scenarios"
HISTORY_PATH = V2 / "history" / "history.json"
INSTRUCTION = V2 / "instruction.md"
DEV_CONTRACT = V2 / "development.importlinter"
REVIEWED = V2 / "reviewed-exceptions.json"
RUNS_DIR = ROOT / "experiment" / "runs"
WORK_DIR = ROOT / ".tmp" / "runs"
HOOK = TOOLS / "experiment_stop_hook.py"
LEDGER = RUNS_DIR / "spend-ledger.json"
PREPARED_SCHEMA = "coding-agent-gates/prepared-session-v2/v1"

WORKSPACE_PYPROJECT = """\
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
addopts = ["-p", "no:cacheprovider"]
"""
WORKSPACE_GITIGNORE = "__pycache__/\n*.py[cod]\n.venv\n"
GIT_IDENTITY = ["-c", "user.name=Order Service Team", "-c", "user.email=team@example.invalid",
                "-c", "commit.gpgsign=false", "-c", "init.defaultBranch=main"]
GENERATED = {"pyproject.toml": WORKSPACE_PYPROJECT, ".gitignore": WORKSPACE_GITIGNORE}


class NotRunnable(Exception):
    """The session cannot be prepared as specified."""


def load_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_study(path: Path = STUDY_PATH) -> dict[str, Any]:
    return load_json(path)


def load_scenarios(directory: Path = SCENARIOS_DIR) -> dict[str, dict[str, Any]]:
    scenarios = [load_json(p) for p in sorted(Path(directory).glob("*.json"))]
    return {s["id"]: s for s in scenarios}


def messages_for(scenario: dict[str, Any], study: dict[str, Any]) -> list[str]:
    """One user message per step, each with the same frozen suffix in every arm."""
    return [step["request"] + study["prompt_suffix"] for step in scenario["steps"]]


GitRunner = Callable[..., Any]


def _git(runner: GitRunner, workspace: Path, *args: str, date: str | None = None) -> str:
    env = dict(os.environ)
    if date:
        env.update({"GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date})
    proc = runner(["git", *GIT_IDENTITY, *args], cwd=workspace, env=env, capture_output=True,
                  text=True, check=True)
    return (proc.stdout or "").strip()


def _source_text(rel: str, source: str | None, root: Path) -> bytes:
    if source:
        return (root / source).read_bytes()
    if rel == "CLAUDE.md":
        return (root / "experiment" / "v2" / "instruction.md").read_bytes()
    if rel in GENERATED:
        return GENERATED[rel].encode()
    return (root / "experiment" / "v2" / "baseline" / rel).read_bytes()


def build_workspace(workspace: Path, *, root: Path = ROOT, history: dict[str, Any] | None = None,
                    git: GitRunner = subprocess.run) -> str:
    """Create the workspace by replaying the frozen history. Returns HEAD."""
    workspace = Path(workspace)
    if workspace.exists():
        raise NotRunnable(f"workspace already exists: {workspace} (sessions never reuse a workspace)")
    history = history or load_json(root / "experiment" / "v2" / "history" / "history.json")
    workspace.mkdir(parents=True)
    _git(git, workspace, "init", "-q")
    for commit in history["commits"]:
        for item in commit["paths"]:
            rel, source = (item, None) if isinstance(item, str) else (item["path"], item.get("source"))
            dest = workspace / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(_source_text(rel, source, root))
        _git(git, workspace, "add", "-A")
        _git(git, workspace, "commit", "-q", "-m", commit["message"], date=commit["date"])
    (workspace / ".venv").symlink_to(root / ".venv", target_is_directory=True)
    return _git(git, workspace, "rev-parse", "HEAD")


def git_log(workspace: Path, git: GitRunner = subprocess.run) -> list[str]:
    out = _git(git, Path(workspace), "log", "--format=%h %ad %s", "--date=short")
    return out.splitlines()


def gate_paths(root: Path = ROOT) -> dict[str, Path]:
    """Every development-time gate file outside the workspace, keyed by path relative to ``root``."""
    paths = [root / "experiment" / "v2" / "development.importlinter",
             root / "experiment" / "v2" / "reviewed-exceptions.json",
             root / "semantic" / "rubric.md", root / HOOK.relative_to(ROOT),
             root / "experiment" / "tools" / "spend_ledger.py", root / "experiment" / "tools" / "study_v2.py"]
    paths += sorted((root / "src" / "gates").glob("*.py"))
    return {p.relative_to(root).as_posix(): p for p in paths}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def settings_for(arm: str, study: dict[str, Any], *, workspace: Path, state_dir: Path, events: Path,
                 rid: str, ledger: Path, python: str, root: Path = ROOT) -> dict[str, Any]:
    """The session's ``--settings`` file: auto-memory off, plus the arm's hooks (if any)."""
    settings: dict[str, Any] = {"autoMemoryEnabled": False}
    hook = study["arms"][arm]["stop_hook"]
    if hook is None:
        return settings
    args = [str(root / HOOK.relative_to(ROOT)), "--workspace", str(workspace), "--state-dir", str(state_dir),
            "--events", str(events), "--run-id", rid, "--max-repairs", str(study["max_repairs"]),
            "--contract", str(root / "experiment" / "v2" / "development.importlinter"),
            "--reviewed-exceptions", str(root / "experiment" / "v2" / "reviewed-exceptions.json")]
    if hook.get("semantic"):
        args += ["--semantic", "--ledger", str(ledger)]
    command = {"type": "command", "command": python, "args": args,
               # The judge's own timeout is 180 s; the sensor's is 120 s.
               "timeout": 330 if hook.get("semantic") else 150, "onFailure": "continue"}
    settings["hooks"] = {"Stop": [{"hooks": [command]}], "UserPromptSubmit": [{"hooks": [dict(command)]}]}
    return settings


def agent_argv(study: dict[str, Any], model_key: str, *, settings_path: Path) -> list[str]:
    a, m = study["agent"], study["models"][model_key]
    effort = ["--effort", m["effort"]] if m.get("effort") else []
    return [a["cli"], "-p", "--model", m["model"], *effort,
            "--input-format", a["input_format"], "--output-format", a["output_format"], "--verbose",
            "--no-session-persistence", "--setting-sources", a["setting_sources"],
            "--settings", str(settings_path),
            "--tools", ",".join(a["tools"]),
            "--allowedTools", *a["allowed_tools"],
            "--disallowedTools", *a["disallowed_tools"],
            *(["--disable-slash-commands"] if a.get("disable_slash_commands") else []),
            "--permission-mode", a["permission_mode"],
            "--permission-prompts", a["permission_prompts"],
            "--max-budget-usd", m["max_budget_usd"]]


def prepare(scenario: dict[str, Any], entry: dict[str, Any], *, study: dict[str, Any], study_name: str,
            root: Path = ROOT, work_dir: Path = WORK_DIR, runs_dir: Path = RUNS_DIR, ledger: Path = LEDGER,
            git: GitRunner = subprocess.run, which: Callable[[str], str | None] = shutil.which,
            python: str | None = None) -> dict[str, Any]:
    arm, model_key, rid = entry["arm"], entry["model_key"], entry["run_id"]
    if arm not in study["arms"]:
        raise NotRunnable(f"unknown arm {arm!r}")
    if model_key not in study["models"]:
        raise NotRunnable(f"unknown model {model_key!r}")
    if which(study["agent"]["cli"]) is None:
        raise NotRunnable(f"the agent CLI {study['agent']['cli']!r} is not on PATH")
    base = Path(work_dir) / study_name / rid
    workspace, state_dir, events = base / "workspace", base / "hook-state", base / "hook-events.jsonl"
    head = build_workspace(workspace, root=root, git=git)
    python = python or str(root / ".venv" / "bin" / "python")
    settings = settings_for(arm, study, workspace=workspace, state_dir=state_dir, events=events, rid=rid,
                            ledger=ledger, python=python, root=root)
    settings_path = base / "settings.json"
    settings_path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    messages = messages_for(scenario, study)
    prepared = {
        "schema": PREPARED_SCHEMA,
        "prepared_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "study": study_name, "run_id": rid, "scenario_id": scenario["id"], "arm": arm,
        "model_key": model_key, "repeat": entry["repeat"], "plan": entry,
        "paths": {"base": str(base), "workspace": str(workspace), "settings": str(settings_path),
                  "hook_events": str(events), "hook_state": str(state_dir), "turns": str(base / "turns"),
                  "retained": str(Path(runs_dir) / study_name / rid)},
        "baseline_commit": head,
        "workspace": ev.file_hashes(workspace, (*ev2.WORKSPACE_PROTECTED, *ev2.BASELINE_TESTS, ev2.LEGACY_MODULE)),
        "workspace_tree_sha256": ev.tree_hash(ev.file_hashes(workspace, ev2.SNAPSHOT_PATTERNS)),
        "gates": {rel: sha256_file(p) for rel, p in gate_paths(root).items()},
        "settings": settings,
        "settings_sha256": sha256_file(settings_path),
        "messages": messages,
        "messages_sha256": hashlib.sha256(json.dumps(messages).encode()).hexdigest(),
        "scenario_sha256": sha256_file(scenario_file) if (
            scenario_file := root / "experiment" / "v2" / "scenarios" / f"{scenario['id']}.json").is_file() else None,
        "instruction_sha256": sha256_file(root / "experiment" / "v2" / "instruction.md"),
        "study_sha256": sha256_file(root / "experiment" / "v2" / "study.json"),
        "agent_argv": agent_argv(study, model_key, settings_path=settings_path),
        "agent_config": {**study["agent"], **study["models"][model_key]},
    }
    (base / "prepared.json").write_text(json.dumps(prepared, indent=2) + "\n", encoding="utf-8")
    return prepared


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p_plan = sub.add_parser("plan")
    p_plan.add_argument("--study", required=True)
    args = parser.parse_args()
    study = load_study()
    out = RUNS_DIR / args.study / "order.json"
    if out.exists():
        print(f"refusing to overwrite an existing plan: {out}")
        return 1
    plan = study_v2.plan_sessions(study["scenarios"], sorted(study["arms"]), list(study["models"]),
                                  repeats=study["repeats"], seed=study["seed"])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"schema": "coding-agent-gates/run-order-v2/v1", "study": args.study,
                               "seed": study["seed"], "method": "study_v2.plan_sessions",
                               "written_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                               "runs": plan}, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out.relative_to(ROOT)} ({len(plan)} sessions)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
