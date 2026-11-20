#!/usr/bin/env python3
"""Run one CI job's own steps locally, in a clean copy. A LOCAL SIMULATION, not a hosted run.

    .venv/bin/python integrations/simulate_ci.py \\
        --workflow integrations/github-actions.yaml --job architecture-contracts \\
        --layout standalone [--overlay fixtures/direct_import] [--output evidence/X.json]

1. Copies the tracked and unignored files of this example (from the working
   tree, so uncommitted edits are included and recorded as such) into a fresh
   directory under .tmp/ci-sim/. ``--layout standalone`` puts them at the copy's
   root, as in a reader's own repository (integrations/github-actions.yaml).
   ``--layout site`` keeps their path inside the site repository
   (.github/workflows/coding-agent-gates.yml uses that working-directory).
2. Optionally copies an overlay directory (for example fixtures/direct_import,
   the pull request's change) over the example in the copy.
3. Runs the job's steps as planned by gates.ci_simulation: checkout is the
   clean copy, setup-python checks the local interpreter against
   python-version-file, and every run step goes through bash -eo pipefail.

Needs Git, Bash, a local Python matching .python-version (``--python``, default
python<version> on PATH) and network access for the step that installs
requirements.lock. Exit status: 0 job succeeded, 1 job failed or timed out,
2 the workflow or environment could not be simulated (nothing was judged).
The workspace is deleted afterwards unless --keep-workspace is given.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path

EXAMPLE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EXAMPLE / "src"))

import yaml  # noqa: E402  (installed from requirements.lock with pre-commit)

from gates.ci_simulation import (  # noqa: E402
    LABEL, NOT_REPRODUCED, SCHEMA, Completed, UnsupportedWorkflow, plan_job, run_job, tree_digest,
)


def git(*args: str, cwd: Path) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


def real_runner(argv: list[str], cwd: Path, env: dict[str, str], timeout: float) -> Completed:
    try:
        done = subprocess.run(argv, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        out = exc.output.decode() if isinstance(exc.output, bytes) else (exc.output or "")
        return Completed(None, out, True)
    except OSError as exc:
        return Completed(127, f"could not start {argv[0]}: {exc}", False)
    return Completed(done.returncode, done.stdout, False)


def tool_version(argv: list[str]) -> str | None:
    try:
        out = subprocess.run(argv, capture_output=True, text=True, timeout=30).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out.splitlines()[0] if out else None


def prepare_workspace(dest: Path, layout: str, overlay: Path | None) -> dict:
    top = Path(git("rev-parse", "--show-toplevel", cwd=EXAMPLE).strip())
    sub = EXAMPLE.relative_to(top)
    listed = git("ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", ".", cwd=EXAMPLE)
    rels = sorted(p for p in listed.split("\0") if p and (EXAMPLE / p).is_file())
    base = dest if layout == "standalone" else dest / sub
    for rel in rels:
        target = base / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(EXAMPLE / rel, target)
    overlay_files = []
    if overlay is not None:
        for src in sorted(p for p in overlay.rglob("*") if p.is_file()):
            rel = src.relative_to(overlay).as_posix()
            (base / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, base / rel)
            overlay_files.append({"path": rel, "sha256": hashlib.sha256(src.read_bytes()).hexdigest()})
    copied = sorted(p for p in base.rglob("*") if p.is_file())
    return {
        "layout": layout,
        "source_commit": git("rev-parse", "HEAD", cwd=EXAMPLE).strip(),
        "source_uncommitted_changes": bool(git("status", "--porcelain", "--", ".", cwd=EXAMPLE).strip()),
        "example_path_in_copy": "." if layout == "standalone" else sub.as_posix(),
        "files_copied": len(rels),
        "overlay": overlay.relative_to(EXAMPLE).as_posix() if overlay else None,
        "overlay_files": overlay_files,
        "example_tree_sha256": tree_digest((p.relative_to(base).as_posix(), p.read_bytes()) for p in copied),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one CI job's steps locally in a clean copy (a local simulation, not a hosted run).")
    parser.add_argument("--workflow", required=True, type=Path)
    parser.add_argument("--job", required=True)
    parser.add_argument("--layout", required=True, choices=["standalone", "site"])
    parser.add_argument("--overlay", type=Path, help="directory copied over the example in the clean copy")
    parser.add_argument("--python", help="interpreter for setup-python (default: python<version> on PATH)")
    parser.add_argument("--output", type=Path, help="write the JSON record here")
    parser.add_argument("--keep-workspace", action="store_true")
    args = parser.parse_args(argv)

    try:
        plan = plan_job(yaml.safe_load(args.workflow.read_text()), args.job)
    except (OSError, yaml.YAMLError, UnsupportedWorkflow) as exc:
        print(f"CI SIMULATION NOT RUN: {exc}", file=sys.stderr)
        return 2
    overlay = args.overlay.resolve() if args.overlay else None
    if overlay is not None and not overlay.is_dir():
        print(f"CI SIMULATION NOT RUN: overlay {args.overlay} is not a directory", file=sys.stderr)
        return 2
    version = (EXAMPLE / ".python-version").read_text().strip()
    python = args.python or shutil.which(f"python{version}")
    if not python:
        print(f"CI SIMULATION NOT RUN: no python{version} on PATH; pass --python", file=sys.stderr)
        return 2

    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    sim_root = EXAMPLE / ".tmp" / "ci-sim" / f"{stamp}-{plan.job_id}"
    workspace = sim_root / "workspace"
    workspace.mkdir(parents=True)
    try:
        try:
            source = prepare_workspace(workspace, args.layout, overlay)
        except (OSError, subprocess.CalledProcessError) as exc:
            print(f"CI SIMULATION NOT RUN: could not make the clean copy: {exc}", file=sys.stderr)
            return 2
        started_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        job = run_job(plan, workspace, sim_root=sim_root, python=python, runner=real_runner,
                      clock=time.monotonic, base_env=dict(os.environ))
    finally:
        if not args.keep_workspace:
            shutil.rmtree(sim_root, ignore_errors=True)

    workflow_bytes = args.workflow.read_bytes()
    try:
        workflow_display = args.workflow.resolve().relative_to(Path(git("rev-parse", "--show-toplevel", cwd=EXAMPLE).strip())).as_posix()
    except ValueError:
        workflow_display = str(args.workflow)
    record = {
        "schema": SCHEMA,
        "label": LABEL,
        "started_at": started_at,
        "command": "integrations/simulate_ci.py " + " ".join(argv if argv is not None else sys.argv[1:]),
        "workflow": {"path": workflow_display, "sha256": hashlib.sha256(workflow_bytes).hexdigest()},
        "source": source,
        "environment": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "python_requested": version,
            "python_interpreter": python,
            "bash": tool_version(["bash", "--version"]),
            "git": tool_version(["git", "--version"]),
        },
        "not_reproduced": list(NOT_REPRODUCED),
        "job": job,
        "workspace_kept": str(workspace) if args.keep_workspace else None,
    }
    text = json.dumps(record, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text)
    print(f"{LABEL}\njob {plan.check_name}: {job['conclusion'].upper()}"
          + (f" at step '{job['failing_step']}'" if job["failing_step"] else ""))
    for step in job["steps"]:
        print(f"  [{step['outcome']:>9}] {step['name']} (exit {step['exit']})")
    if job["failing_step"]:
        failed = next(s for s in job["steps"] if s["name"] == job["failing_step"])
        print("--- failing step log (tail) ---\n" + failed.get("output_tail", ""))
    return 0 if job["conclusion"] == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
