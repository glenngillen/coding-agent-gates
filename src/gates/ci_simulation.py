"""Run one GitHub Actions job's steps locally, in a clean copy. Not a hosted run.

``integrations/simulate_ci.py`` is the command. This module holds the parts
that can be tested without running anything:

* ``plan_job`` reads a parsed workflow and returns the job's steps, refusing
  anything it cannot reproduce faithfully (expressions, conditionals, step
  environments, other shells, unknown actions) instead of skipping it.
* ``run_job`` executes the planned steps with an injected process runner:
  ``actions/checkout`` is satisfied by the clean copy made before the job,
  ``actions/setup-python`` puts a local interpreter that matches the
  workflow's ``python-version-file`` first on ``PATH``, and each ``run`` step
  goes through ``bash --noprofile --norc -eo pipefail``, GitHub's default for
  Linux runners. The first failing step fails the job; later steps are
  skipped, as on GitHub.

What this cannot reproduce (recorded in every result): the ubuntu-latest
image, the real actions' code, GitHub's ``GITHUB_*`` environment and token,
the trigger event, and anything about required checks or merging.
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

SCHEMA = "coding-agent-gates/ci-simulation/v1"
LABEL = ("LOCAL SIMULATION of a GitHub Actions job. Not a hosted run: no GitHub "
         "runner, check run, required status check or merge decision was involved.")
NOT_REPRODUCED = (
    "runs-on image (ubuntu-latest): steps ran on the local OS instead",
    "actions/checkout: replaced by a clean copy of the working tree's tracked and unignored files",
    "actions/setup-python: replaced by a local interpreter whose version matches python-version-file",
    "GITHUB_* environment variables, GITHUB_TOKEN and the permissions block",
    "the triggering event (pull_request/push) and its merge commit",
    "required-check configuration and any effect on merging",
)

ALLOWED_JOB_KEYS = {"name", "runs-on", "timeout-minutes", "steps", "defaults", "permissions"}
ALLOWED_STEP_KEYS = {"name", "uses", "with", "run", "working-directory"}
DEFAULT_TIMEOUT_MINUTES = 360  # GitHub's default job timeout
SNAPSHOT_RE = re.compile(r"\bsnapshot:? ([0-9a-f]{12})\b", re.IGNORECASE)
VERSION_PROBE = "import os, sys; print('%d.%d.%d' % sys.version_info[:3]); print(os.path.realpath(sys.executable))"


class UnsupportedWorkflow(ValueError):
    """The workflow uses something this simulation cannot reproduce faithfully."""


@dataclass(frozen=True)
class Step:
    kind: str  # "checkout" | "setup-python" | "run"
    name: str
    uses: str | None = None
    run: str | None = None
    working_directory: str = "."
    python_version_file: str | None = None


@dataclass(frozen=True)
class JobPlan:
    workflow_name: str | None
    job_id: str
    check_name: str
    timeout_minutes: float
    steps: tuple[Step, ...]


@dataclass(frozen=True)
class Completed:
    exit: int | None  # None when the process was killed by the timeout
    output: str  # stdout and stderr combined, as in a job log
    timed_out: bool


Runner = Callable[[list[str], Path, dict[str, str], float], Completed]


def _no_expressions(value: Any, where: str) -> None:
    if isinstance(value, str) and "${{" in value:
        raise UnsupportedWorkflow(f"{where}: GitHub expression syntax (${{{{ }}}}) is not evaluated locally")
    if isinstance(value, dict):
        for k, v in value.items():
            _no_expressions(v, f"{where}.{k}")
    if isinstance(value, list):
        for i, v in enumerate(value):
            _no_expressions(v, f"{where}[{i}]")


def _working_directory(defaults: Any, where: str) -> str | None:
    if defaults is None:
        return None
    if not isinstance(defaults, dict) or set(defaults) - {"run"}:
        raise UnsupportedWorkflow(f"{where}: only defaults.run.working-directory is supported")
    run = defaults.get("run", {})
    if not isinstance(run, dict) or set(run) - {"working-directory"}:
        raise UnsupportedWorkflow(f"{where}: only defaults.run.working-directory is supported")
    wd = run.get("working-directory")
    if wd is not None and not isinstance(wd, str):
        raise UnsupportedWorkflow(f"{where}: working-directory must be a string")
    return wd


def _plan_step(raw: Any, index: int, default_wd: str) -> Step:
    where = f"step {index + 1}"
    if not isinstance(raw, dict):
        raise UnsupportedWorkflow(f"{where}: not a mapping")
    extra = set(raw) - ALLOWED_STEP_KEYS
    if extra:
        raise UnsupportedWorkflow(f"{where}: unsupported key(s) {sorted(map(str, extra))}")
    name = raw.get("name")
    if name is not None and not isinstance(name, str):
        raise UnsupportedWorkflow(f"{where}: name must be a string")
    has_run, has_uses = "run" in raw, "uses" in raw
    if has_run and has_uses:
        raise UnsupportedWorkflow(f"{where}: has both run and uses")
    if not (has_run or has_uses):
        raise UnsupportedWorkflow(f"{where}: needs run or uses")
    if has_run:
        command = raw["run"]
        if not isinstance(command, str) or "with" in raw:
            raise UnsupportedWorkflow(f"{where}: run must be a string, without 'with'")
        wd = raw.get("working-directory", default_wd)
        if not isinstance(wd, str):
            raise UnsupportedWorkflow(f"{where}: working-directory must be a string")
        first = command.strip().splitlines()[0] if command.strip() else ""
        return Step("run", name or f"Run {first}", run=command, working_directory=wd)
    uses = raw["uses"]
    if not isinstance(uses, str) or "working-directory" in raw:
        raise UnsupportedWorkflow(f"{where}: uses must be a string, without working-directory")
    action = uses.split("@", 1)[0]
    with_ = raw.get("with", {})
    if not isinstance(with_, dict):
        raise UnsupportedWorkflow(f"{where}: with must be a mapping")
    display = name or f"Run {uses}"
    if action == "actions/checkout":
        if with_:
            raise UnsupportedWorkflow(f"{where}: actions/checkout inputs are not supported")
        return Step("checkout", display, uses=uses)
    if action == "actions/setup-python":
        if set(with_) != {"python-version-file"} or not isinstance(with_["python-version-file"], str):
            raise UnsupportedWorkflow(f"{where}: actions/setup-python is supported only with python-version-file")
        return Step("setup-python", display, uses=uses, python_version_file=with_["python-version-file"])
    raise UnsupportedWorkflow(f"{where}: action {action} has no local equivalent")


def plan_job(workflow: Any, job_id: str) -> JobPlan:
    """Return the steps of ``job_id``, or raise UnsupportedWorkflow."""
    if not isinstance(workflow, dict) or not isinstance(workflow.get("jobs"), dict):
        raise UnsupportedWorkflow("workflow has no jobs mapping")
    jobs = workflow["jobs"]
    if job_id not in jobs:
        raise UnsupportedWorkflow(f"no job {job_id!r}; jobs: {sorted(map(str, jobs))}")
    job = jobs[job_id]
    if not isinstance(job, dict):
        raise UnsupportedWorkflow(f"job {job_id!r} is not a mapping")
    extra = set(job) - ALLOWED_JOB_KEYS
    if extra:
        raise UnsupportedWorkflow(f"job {job_id!r}: unsupported key(s) {sorted(map(str, extra))}")
    _no_expressions(job, f"job {job_id!r}")
    default_wd = (_working_directory(job.get("defaults"), f"job {job_id!r}")
                  or _working_directory(workflow.get("defaults"), "workflow")
                  or ".")
    steps = job.get("steps")
    if not isinstance(steps, list) or not steps:
        raise UnsupportedWorkflow(f"job {job_id!r} has no steps list")
    timeout = job.get("timeout-minutes", DEFAULT_TIMEOUT_MINUTES)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
        raise UnsupportedWorkflow(f"job {job_id!r}: timeout-minutes must be a positive number")
    name = job.get("name", job_id)
    if not isinstance(name, str):
        raise UnsupportedWorkflow(f"job {job_id!r}: name must be a string")
    wf_name = workflow.get("name")
    return JobPlan(wf_name if isinstance(wf_name, str) else None, str(job_id), name, float(timeout),
                   tuple(_plan_step(raw, i, default_wd) for i, raw in enumerate(steps)))


def version_matches(requested: str, actual: str) -> bool:
    """True when every component of ``requested`` (e.g. 3.12) equals ``actual``'s."""
    want = requested.strip().split(".")
    have = actual.strip().split(".")
    return len(want) <= len(have) and want == have[:len(want)]


def tree_digest(files: Iterable[tuple[str, bytes]]) -> str:
    """SHA-256 over sorted (path, SHA-256 of content) pairs: the checked-out snapshot."""
    h = hashlib.sha256()
    for path, content in sorted(files, key=lambda f: f[0]):
        h.update(path.encode("utf-8", "surrogatepass") + b"\0")
        h.update(hashlib.sha256(content).hexdigest().encode() + b"\n")
    return h.hexdigest()


def extract_snapshots(text: str) -> list[str]:
    """Sensor snapshot ids (12 hex chars) printed in a step's log, de-duplicated in order."""
    seen: list[str] = []
    for match in SNAPSHOT_RE.findall(text):
        if match not in seen:
            seen.append(match)
    return seen


def tail(text: str, lines: int) -> tuple[str, int]:
    all_lines = text.splitlines()
    return "\n".join(all_lines[-lines:]), len(all_lines)


def _step_env(base_env: dict[str, str], bindir: Path | None) -> dict[str, str]:
    env = {k: v for k, v in base_env.items()
           if k not in {"VIRTUAL_ENV", "PYTHONPATH", "PYTHONHOME", "PIP_REQUIRE_VIRTUALENV"}
           and not k.startswith("GITHUB_")}
    env["CI"] = "true"
    if bindir is not None:
        env["PATH"] = f"{bindir}{os.pathsep}{env.get('PATH', '')}"
    return env


def run_job(plan: JobPlan, workspace: Path, *, sim_root: Path, python: str, runner: Runner,
            clock: Callable[[], float], base_env: dict[str, str], tail_lines: int = 80) -> dict[str, Any]:
    """Execute ``plan`` in ``workspace`` and return the job record (no file output)."""
    sim_root.mkdir(parents=True, exist_ok=True)
    budget = plan.timeout_minutes * 60
    started = clock()
    bindir: Path | None = None
    records: list[dict[str, Any]] = []
    conclusion, failing = "success", None

    for index, step in enumerate(plan.steps):
        record: dict[str, Any] = {"name": step.name, "kind": step.kind, "uses": step.uses,
                                  "command": step.run, "working_directory": step.working_directory}
        if failing is not None:
            records.append({**record, "outcome": "skipped", "exit": None})
            continue
        t0 = clock()
        output, exit_code, timed_out = "", 0, False
        if step.kind == "checkout":
            output = "Satisfied by the clean copy made before the job started."
        elif step.kind == "setup-python":
            version_file = workspace / (step.python_version_file or "")
            requested = version_file.read_text().strip() if version_file.is_file() else ""
            probe = runner([python, "-c", VERSION_PROBE], workspace, _step_env(base_env, None), 60)
            lines = probe.output.split()
            actual, executable = (lines + ["", ""])[:2]
            if not requested:
                exit_code, output = 1, f"python-version-file {step.python_version_file} not found or empty"
            elif probe.exit != 0 or not version_matches(requested, actual):
                exit_code = 1
                output = (f"Requested Python {requested} (from {step.python_version_file}); "
                          f"local interpreter {python} reports {actual or 'nothing'}.")
            else:
                bindir = sim_root / "toolcache" / "bin"
                bindir.mkdir(parents=True, exist_ok=True)
                for alias in ("python", "python3"):
                    link = bindir / alias
                    if link.is_symlink() or link.exists():
                        link.unlink()
                    link.symlink_to(executable)
                output = f"Python {actual} ({executable}) matches {requested} from {step.python_version_file}."
        else:
            script = sim_root / "steps" / f"{index + 1:02d}.sh"
            script.parent.mkdir(parents=True, exist_ok=True)
            script.write_text(step.run or "")
            remaining = max(budget - (clock() - started), 1.0)
            done = runner(["bash", "--noprofile", "--norc", "-eo", "pipefail", str(script)],
                          workspace / step.working_directory, _step_env(base_env, bindir), remaining)
            output, exit_code, timed_out = done.output, done.exit, done.timed_out
        kept, total = tail(output, tail_lines)
        outcome = "timed_out" if timed_out else ("success" if exit_code == 0 else "failure")
        records.append({**record, "outcome": outcome, "exit": exit_code,
                        "duration_s": round(clock() - t0, 3),
                        "output_lines": total, "output_sha256": hashlib.sha256(output.encode()).hexdigest(),
                        "output_tail": kept, "snapshots": extract_snapshots(output)})
        if outcome != "success":
            conclusion, failing = outcome, step.name

    return {"workflow_name": plan.workflow_name, "job_id": plan.job_id, "check_name": plan.check_name,
            "timeout_minutes": plan.timeout_minutes, "conclusion": conclusion, "failing_step": failing,
            "duration_s": round(clock() - started, 3), "steps": records}
