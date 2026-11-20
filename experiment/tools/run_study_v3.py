#!/usr/bin/env python3
"""Plan, freeze and run the version 3 study (experiment/protocol-v3.md).

    .venv/bin/python experiment/tools/run_study_v3.py freeze --write|--check
    .venv/bin/python experiment/tools/run_study_v3.py plan --study NAME
    .venv/bin/python experiment/tools/run_study_v3.py run --study NAME

Version 3 adds one factor to version 2: how much of the architecture rule the
workspace ``CLAUDE.md`` states (``experiment/v3/study.json`` → ``guidance``).
Everything else is the frozen version 2 machinery, used unchanged: the session
driver, the Stop hook, the contracts, the scenarios, the workspace history,
the acceptance tests, the evaluator and the slip definitions. This module only

- plans sessions over guidance x scenario x model x arm;
- builds each workspace from the version 2 history with ``CLAUDE.md`` taken
  from the session's guidance file (``prepare_v2.build_workspace`` already
  accepts a history whose entries name a source file);
- records the guidance level in each session's record;
- checks both manifests (version 2's and ``experiment/v3/frozen-manifest.json``)
  before any session.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import copy
import hashlib
import json
import random
import shutil
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
TOOLS = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "experiment"), str(TOOLS)]

import prepare_v2 as pv  # noqa: E402
import run_pilot  # noqa: E402
import run_study_v2 as rs  # noqa: E402
import spend_ledger  # noqa: E402
import study_v2  # noqa: E402
from evaluator import evaluate as ev  # noqa: E402
from evaluator import evaluate_v2 as ev2  # noqa: E402

V3 = ROOT / "experiment" / "v3"
STUDY_PATH = V3 / "study.json"
MANIFEST = V3 / "frozen-manifest.json"
# Version 3's own frozen inputs. The version 2 inputs it reuses stay frozen by
# experiment/v2/frozen-manifest.json, which is checked as well.
FROZEN_PATTERNS = (
    "experiment/protocol-v3.md",
    "experiment/v3/study.json",
    "experiment/v3/instructions/*.md",
    "experiment/tools/run_study_v3.py",
)
ORDER_SCHEMA = "coding-agent-gates/run-order-v3/v1"


def load_study(path: Path = STUDY_PATH) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def run_id(guidance: str, scenario_id: str, arm: str, model_key: str, repeat: int) -> str:
    return f"{guidance}-{study_v2.run_id(scenario_id, arm, model_key, repeat)}"


def plan_sessions(guidance: list[str], scenarios: list[str], arms: list[str], models: list[str], *,
                  repeats: int, seed: int) -> list[dict[str, Any]]:
    """Every (guidance, scenario, model, arm) cell once per repeat, shuffled within each repeat block."""
    rng = random.Random(seed)
    plan: list[dict[str, Any]] = []
    for repeat in range(1, repeats + 1):
        block = [(g, s, m, a) for g in guidance for s in scenarios for m in models for a in arms]
        rng.shuffle(block)
        for g, s, m, a in block:
            plan.append({"sequence": len(plan) + 1, "repeat": repeat, "guidance": g, "scenario_id": s,
                         "arm": a, "model_key": m, "run_id": run_id(g, s, a, m, repeat)})
    return plan


def history_for(instruction_file: str, root: Path = ROOT) -> dict[str, Any]:
    """The version 2 workspace history with ``CLAUDE.md`` taken from ``instruction_file``."""
    history = copy.deepcopy(pv.load_json(root / "experiment" / "v2" / "history" / "history.json"))
    replaced = 0
    for commit in history["commits"]:
        for i, item in enumerate(commit["paths"]):
            if item == "CLAUDE.md":
                commit["paths"][i] = {"path": "CLAUDE.md", "source": instruction_file}
                replaced += 1
    if replaced != 1:
        raise pv.NotRunnable(f"expected exactly one CLAUDE.md entry in the version 2 history, found {replaced}")
    return history


_session = threading.local()
_v2_build_workspace = pv.build_workspace
_v2_prepare = pv.prepare


def _build_workspace(workspace: Path, *, root: Path = ROOT, history: dict[str, Any] | None = None,
                     git: pv.GitRunner = pv.subprocess.run) -> str:
    return _v2_build_workspace(workspace, root=root, history=history or history_for(_session.instruction, root),
                               git=git)


def _prepare(scenario: dict[str, Any], entry: dict[str, Any], *, study: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    """``prepare_v2.prepare`` with the session's guidance file as ``CLAUDE.md``."""
    level = entry["guidance"]
    instruction = study["guidance"][level]["instruction_file"]
    _session.instruction = instruction
    try:
        prepared = _v2_prepare(scenario, entry, study=study, **kwargs)
    finally:
        _session.instruction = None
    workspace = Path(prepared["paths"]["workspace"])
    if (workspace / "CLAUDE.md").read_bytes() != (ROOT / instruction).read_bytes():
        raise pv.NotRunnable(f"workspace CLAUDE.md is not {instruction}")
    prepared.update({"guidance": level, "instruction_file": instruction,
                     "instruction_sha256": pv.sha256_file(ROOT / instruction),
                     "study_sha256": pv.sha256_file(STUDY_PATH)})
    (Path(prepared["paths"]["base"]) / "prepared.json").write_text(json.dumps(prepared, indent=2) + "\n",
                                                                   encoding="utf-8")
    return prepared


def install() -> None:
    """Route the version 2 runner's workspace preparation through the guidance factor."""
    pv.build_workspace = _build_workspace
    pv.prepare = _prepare


def current_frozen_hashes(root: Path = ROOT) -> dict[str, str]:
    return ev.file_hashes(root, FROZEN_PATTERNS)


def check_frozen() -> None:
    ev.check_frozen(ev.load_manifest(ev2.MANIFEST), ev2.current_frozen_hashes())
    ev.check_frozen(ev.load_manifest(MANIFEST), current_frozen_hashes())


def run_session(scenario: dict, entry: dict, study: dict, study_name: str, ledger: Path, env: dict) -> dict[str, Any]:
    record = rs.run_session(scenario, entry, study, study_name, ledger, env)
    record["identity"]["guidance"] = entry["guidance"]
    record["identity"]["protocol"] = study["protocol"]
    path = pv.RUNS_DIR / study_name / entry["run_id"] / "record.json"
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return record


def cmd_freeze(args: argparse.Namespace) -> int:
    current = current_frozen_hashes()
    if args.check:
        try:
            check_frozen()
        except (ev.FrozenCriteriaChanged, OSError, ValueError) as exc:
            print(f"NOT FROZEN: {exc}")
            return 1
        print(f"frozen: {len(current)} version 3 files match {MANIFEST.relative_to(ROOT)}; version 2 manifest matches")
        return 0
    if MANIFEST.exists():
        print(f"refusing to overwrite {MANIFEST.relative_to(ROOT)}: version 3 is frozen once, before any run")
        return 1
    manifest = {"schema": "coding-agent-gates/frozen-manifest/v1",
                "written_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "note": args.note,
                "patterns": list(FROZEN_PATTERNS), "files": current, "tree_sha256": ev.tree_hash(current),
                "depends_on": {"experiment/v2/frozen-manifest.json": pv.sha256_file(ev2.MANIFEST)}}
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {MANIFEST.relative_to(ROOT)} ({len(current)} files)")
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    study = load_study()
    out = pv.RUNS_DIR / args.study / "order.json"
    if out.exists():
        print(f"refusing to overwrite an existing plan: {out}")
        return 1
    plan = plan_sessions(list(study["guidance"]), study["scenarios"], sorted(study["arms"]), list(study["models"]),
                         repeats=study["repeats"], seed=study["seed"])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"schema": ORDER_SCHEMA, "study": args.study, "seed": study["seed"],
                               "method": "run_study_v3.plan_sessions",
                               "written_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                               "runs": plan}, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out.relative_to(ROOT)} ({len(plan)} sessions)")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    if shutil.which("claude") is None:
        print("NOT RUN: the claude CLI is not on PATH")
        return 5
    check_frozen()
    install()
    study = load_study()
    scenarios = pv.load_scenarios()
    env = run_pilot.environment()
    plan = json.loads((pv.RUNS_DIR / args.study / "order.json").read_text())["runs"]
    todo = [e for e in plan if not (pv.RUNS_DIR / args.study / e["run_id"] / "record.json").exists()]
    workers = args.workers or study["workers"]
    print(f"{len(todo)} of {len(plan)} sessions to do; workers={workers}", flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(run_session, scenarios[e["scenario_id"]], e, study, args.study, args.ledger, env)
                   for e in todo]
        for f in futures:
            f.result()
    return 6 if rs.STOP.is_set() else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p_freeze = sub.add_parser("freeze")
    group = p_freeze.add_mutually_exclusive_group(required=True)
    group.add_argument("--write", action="store_true")
    group.add_argument("--check", action="store_true")
    p_freeze.add_argument("--note", default="")
    p_plan = sub.add_parser("plan")
    p_plan.add_argument("--study", required=True)
    p_run = sub.add_parser("run")
    p_run.add_argument("--study", required=True)
    p_run.add_argument("--workers", type=int, default=None)
    p_run.add_argument("--ledger", type=Path, default=spend_ledger.DEFAULT_PATH)
    args = parser.parse_args()
    return {"freeze": cmd_freeze, "plan": cmd_plan, "run": cmd_run}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
