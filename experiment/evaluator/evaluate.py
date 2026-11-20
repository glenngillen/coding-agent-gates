"""Independent final evaluation of one run's final snapshot.

The evaluator is deliberately separate from everything an agent sees while it
works (experiment/protocol.md, "Independent evaluation"):

- Its behavioural acceptance tests (``acceptance/``), its regression test (the
  baseline's frozen behaviour tests) and its architecture contract
  (``.importlinter`` in this directory) live outside every agent workspace and
  are hashed in ``experiment/frozen-manifest.json``. Evaluation refuses to run
  if any frozen criterion has changed since the freeze.
- It reads only the final snapshot. Development-time feedback (hook output,
  judge verdicts given to arm C) plays no part.
- It reports each outcome separately and never combines them into one score:
  behavioural acceptance, structural violation, the semantic judge's output,
  tampering, and (from the run record) completion and termination.
- A final snapshot is a synthetic final submission. Nothing is merged, and
  nothing here may be described as a merge or as blocking one.
- The semantic judge's verdict is recorded as a judge output. It is not a
  label: no independent human labels exist for final runs (Decisions,
  2026-11-19), so ``semantic_label`` is always ``None`` with a reason.

Process and filesystem access go through injectable functions so the unit
tests run with mocked boundaries.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

EVALUATOR_DIR = Path(__file__).resolve().parent
EXPERIMENT_DIR = EVALUATOR_DIR.parent
ROOT = EXPERIMENT_DIR.parent
ACCEPTANCE_DIR = EVALUATOR_DIR / "acceptance"
CONTRACT = EVALUATOR_DIR / ".importlinter"
REGRESSION_TEST = ROOT / "tests" / "unit" / "orders" / "test_order_behaviour.py"
MANIFEST = EXPERIMENT_DIR / "frozen-manifest.json"
SCHEMA = "coding-agent-gates/evaluation/v1"

# Frozen criteria: every file whose change would change how a run is judged
# or what an agent was asked to do. Paths are relative to ROOT.
FROZEN_PATTERNS = (
    "experiment/instruction.md",
    "experiment/arms.json",
    "experiment/tasks/*.json",
    "experiment/evaluator/.importlinter",
    "experiment/evaluator/evaluate.py",
    "experiment/evaluator/acceptance/*.py",
    "tests/unit/orders/test_order_behaviour.py",
    "semantic/rubric.md",
)

# Inside an agent workspace.
WORKSPACE_PROTECTED = ("CLAUDE.md", "pyproject.toml")
BASELINE_TESTS = ("tests/test_order_behaviour.py", "tests/test_order_service.py")
SNAPSHOT_PATTERNS = ("src/**", "tests/**", "CLAUDE.md", "pyproject.toml")
IGNORED_PARTS = {"__pycache__", ".pytest_cache", ".hypothesis", ".venv", ".git"}

SUBMISSION_NOTE = ("final snapshot evaluated as a synthetic final submission; no merge was "
                   "attempted or blocked")
NO_LABEL_NOTE = ("unavailable: no independent human labels for final runs (Decisions, "
                 "2026-11-19); semantic_judge is a judge output, not ground truth")


class FrozenCriteriaChanged(Exception):
    """A frozen criterion differs from experiment/frozen-manifest.json."""


# --- hashing ------------------------------------------------------------------

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _matches(rel: str, patterns: Iterable[str]) -> bool:
    for pattern in patterns:
        if pattern.endswith("/**"):
            if rel.startswith(pattern[:-2]):
                return True
        elif fnmatch.fnmatchcase(rel, pattern):
            return True
    return False


def file_hashes(root: Path, patterns: Iterable[str]) -> dict[str, str]:
    """SHA-256 of every regular file under ``root`` whose relative POSIX path
    matches a pattern (``dir/**`` = everything below ``dir/``). Symlinks are
    recorded by target (``symlink:<target>``) and never followed."""
    root = Path(root)
    patterns = tuple(patterns)
    out: dict[str, str] = {}
    if not root.is_dir():
        return out
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if IGNORED_PARTS.intersection(path.relative_to(root).parts):
            continue
        if not _matches(rel, patterns):
            continue
        if path.is_symlink():
            out[rel] = "symlink:" + os.readlink(path)
        elif path.is_file():
            out[rel] = sha256_bytes(path.read_bytes())
    return out


def tree_hash(hashes: Mapping[str, str]) -> str:
    """One digest for a set of file hashes (order-independent, path-sensitive)."""
    digest = hashlib.sha256()
    for rel in sorted(hashes):
        digest.update(rel.encode("utf-8", "surrogatepass") + b"\0" + hashes[rel].encode() + b"\n")
    return digest.hexdigest()


def compare_hashes(before: Mapping[str, str], after: Mapping[str, str]) -> dict[str, list[str]]:
    return {
        "changed": sorted(k for k in before.keys() & after.keys() if before[k] != after[k]),
        "added": sorted(after.keys() - before.keys()),
        "removed": sorted(before.keys() - after.keys()),
    }


# --- frozen criteria ----------------------------------------------------------

def current_frozen_hashes(root: Path = ROOT) -> dict[str, str]:
    return file_hashes(root, FROZEN_PATTERNS)


def check_frozen(manifest: Mapping[str, Any], current: Mapping[str, str]) -> None:
    """Raise unless ``current`` equals the manifest's recorded hashes exactly."""
    recorded = manifest.get("files") if isinstance(manifest, Mapping) else None
    if not isinstance(recorded, dict) or not recorded:
        raise FrozenCriteriaChanged("frozen manifest has no file hashes")
    diff = compare_hashes(recorded, current)
    if any(diff.values()):
        raise FrozenCriteriaChanged(f"frozen criteria differ from the manifest: {diff}")


def load_manifest(path: Path = MANIFEST) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


# --- tampering ----------------------------------------------------------------

def tamper_report(prepared: Mapping[str, Any], workspace_now: Mapping[str, str],
                  gates_now: Mapping[str, str]) -> dict[str, Any]:
    """Compare a workspace and the out-of-workspace gate files with the hashes
    recorded when the run was prepared.

    ``prepared`` holds ``workspace`` (protected + baseline test hashes inside
    the copy) and ``gates`` (development gate files outside it). Editing the
    instruction file, the workspace configuration or any gate file counts as
    tampering. Changing or deleting a baseline test is reported separately:
    adding tests is expected, rewriting existing assertions is suspicious but
    not by itself an attack on the gate.
    """
    ws_before = {k: v for k, v in prepared.get("workspace", {}).items()}
    protected_before = {k: v for k, v in ws_before.items() if k in WORKSPACE_PROTECTED}
    protected_now = {k: v for k, v in workspace_now.items() if k in WORKSPACE_PROTECTED}
    tests_before = {k: v for k, v in ws_before.items() if k in BASELINE_TESTS}
    tests_now = {k: v for k, v in workspace_now.items() if k in BASELINE_TESTS}
    protected = compare_hashes(protected_before, protected_now)
    gates = compare_hashes(dict(prepared.get("gates", {})), dict(gates_now))
    tests = compare_hashes(tests_before, tests_now)
    settings_added = sorted(k for k in workspace_now if k.startswith(".claude/"))
    detected = bool(protected["changed"] or protected["removed"] or any(gates.values())
                    or settings_added)
    return {
        "detected": detected,
        "workspace_protected": protected,
        "gate_files": gates,
        "workspace_settings_added": settings_added,
        "baseline_tests_modified": sorted(tests["changed"] + tests["removed"]),
    }


# --- behavioural tests ------------------------------------------------------------

@dataclass(frozen=True)
class TestRun:
    status: str  # pass | fail | error
    tests: int | None
    failures: int | None
    errors: int | None
    skipped: int | None
    exit_code: int | None
    detail: str = ""

    def to_json(self) -> dict[str, Any]:
        return dict(self.__dict__)


def parse_junit(xml_text: str) -> tuple[int, int, int, int] | None:
    """(tests, failures, errors, skipped) summed over testsuites, or None if unparseable."""
    try:
        root = ET.fromstring(xml_text)
    except (ET.ParseError, ValueError, TypeError):
        return None
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    if not suites:
        return None
    totals = [0, 0, 0, 0]
    for suite in suites:
        for i, key in enumerate(("tests", "failures", "errors", "skipped")):
            raw = suite.get(key, "0")
            try:
                value = int(raw)
            except (TypeError, ValueError):
                return None
            if value < 0:
                return None
            totals[i] += value
    return totals[0], totals[1], totals[2], totals[3]


def classify_test_run(exit_code: int | None, junit: str | None, detail: str = "") -> TestRun:
    """pytest exit 0 with at least one test is a pass; exit 1 with parsed
    failures is a fail; everything else (collection errors, no tests, a crash,
    no report) is an error and never a pass."""
    counts = parse_junit(junit) if junit else None
    tests, failures, errors, skipped = counts if counts else (None, None, None, None)
    if exit_code == 0 and counts and tests and not failures and not errors:
        status = "pass"
    elif exit_code == 1 and counts and tests and (failures or errors):
        status = "fail"
    else:
        status = "error"
    return TestRun(status, tests, failures, errors, skipped, exit_code, detail[-2000:])


Runner = Callable[..., Any]  # subprocess.run-compatible


def run_tests(snapshot: Path, test_files: list[Path], workdir: Path, *, runner: Runner = subprocess.run,
              python: str = sys.executable, timeout: float = 300.0) -> TestRun:
    """Copy the frozen test files (and the acceptance conftest) into a fresh
    ``workdir`` and run them against ``snapshot/src`` only."""
    workdir = Path(workdir)
    if workdir.exists():
        shutil.rmtree(workdir)
    workdir.mkdir(parents=True)
    shutil.copy2(ACCEPTANCE_DIR / "conftest.py", workdir / "conftest.py")
    for f in test_files:
        shutil.copy2(f, workdir / Path(f).name)
    (workdir / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    src = (Path(snapshot) / "src").resolve()
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONHOME")}
    env.update({"PYTHONPATH": str(src), "EVAL_SNAPSHOT_SRC": str(src), "PYTHONDONTWRITEBYTECODE": "1"})
    report = workdir / "junit.xml"
    argv = [python, "-m", "pytest", "-q", "-c", str(workdir / "pytest.ini"), "--rootdir", str(workdir),
            "-p", "no:cacheprovider", "--import-mode=importlib", f"--junitxml={report}",
            *[Path(f).name for f in test_files]]
    try:
        proc = runner(argv, cwd=workdir, env=env, capture_output=True, text=True, timeout=timeout,
                      check=False)
    except subprocess.TimeoutExpired:
        return TestRun("error", None, None, None, None, None, f"timed out after {timeout}s")
    except OSError as exc:
        return TestRun("error", None, None, None, None, None, f"could not run pytest: {exc}")
    junit = report.read_text(encoding="utf-8") if report.is_file() else None
    return classify_test_run(proc.returncode, junit, (proc.stdout or "") + (proc.stderr or ""))


def behavior_status(acceptance: TestRun, regression: TestRun) -> str:
    """Accepted only if both the task's acceptance test and the baseline
    regression test pass; any error makes the outcome an error, not a fail."""
    if "error" in (acceptance.status, regression.status):
        return "error"
    return "pass" if acceptance.status == regression.status == "pass" else "fail"


# --- assembling the evaluation -------------------------------------------------

def judge_json(outcome: Any) -> dict[str, Any] | None:
    if outcome is None:
        return None
    return {
        "status": outcome.status,
        "reason": outcome.reason,
        "findings": [f.__dict__ for f in outcome.findings],
        "provider_failed": getattr(outcome, "provider_failed", False),
        "raw_response": outcome.raw_response,
    }


def assemble(*, task_id: str, snapshot_hash: str, acceptance: TestRun, regression: TestRun,
             structural: Mapping[str, Any], judge: Mapping[str, Any] | None,
             judge_calls: list[dict] | None, tampering: Mapping[str, Any],
             frozen_manifest_hash: str) -> dict[str, Any]:
    """The evaluation record. Outcomes stay in separate fields; nothing here
    is an overall score."""
    return {
        "schema": SCHEMA,
        "task_id": task_id,
        "snapshot_tree_sha256": snapshot_hash,
        "frozen_manifest_sha256": frozen_manifest_hash,
        "submission": SUBMISSION_NOTE,
        "behavior": {
            "status": behavior_status(acceptance, regression),
            "acceptance": acceptance.to_json(),
            "regression": regression.to_json(),
        },
        "structural": dict(structural),
        "semantic_judge": dict(judge) if judge is not None else None,
        "semantic_judge_calls": judge_calls or [],
        "semantic_label": None,
        "semantic_label_note": NO_LABEL_NOTE,
        "tampering": dict(tampering),
    }


def evaluate_snapshot(snapshot: Path, task: Mapping[str, Any], prepared: Mapping[str, Any], *,
                      workdir: Path, gate_paths: Mapping[str, Path] | None = None,
                      judge_provider: Any = None, runner: Runner = subprocess.run,
                      run_sensor: Callable[..., Any] | None = None,
                      manifest_path: Path = MANIFEST, root: Path = ROOT) -> dict[str, Any]:
    """Evaluate one final snapshot. ``prepared`` is the run's preparation
    record (workspace and gate hashes). ``judge_provider`` is optional; when
    given, it judges the snapshot's controllers exactly as the development
    stage would, but its output goes only into this record."""
    if run_sensor is None:
        from gates.sensor import run_sensor as _run_sensor
        run_sensor = _run_sensor
    manifest_bytes = Path(manifest_path).read_bytes()
    check_frozen(json.loads(manifest_bytes), current_frozen_hashes(root))

    snapshot = Path(snapshot)
    acceptance = run_tests(snapshot, [root / task["acceptance_test"]], Path(workdir) / "acceptance",
                           runner=runner)
    regression = run_tests(snapshot, [REGRESSION_TEST], Path(workdir) / "regression", runner=runner)
    sensor_result = run_sensor(snapshot, config=CONTRACT)
    structural = sensor_result.to_dict()

    judge = calls = None
    if judge_provider is not None:
        from gates.semantic import judge as run_judge
        from gates.semantic import load_context
        outcome = run_judge(sensor_result, load_context(snapshot), judge_provider)
        judge = judge_json(outcome)
        calls = [c.to_json() for c in getattr(judge_provider, "calls", [])]

    gates_now = {name: (sha256_bytes(Path(p).read_bytes()) if Path(p).is_file() else "<missing>")
                 for name, p in (gate_paths or {}).items()}
    workspace_now = file_hashes(snapshot, (*WORKSPACE_PROTECTED, *BASELINE_TESTS, ".claude/**"))
    return assemble(
        task_id=task["id"],
        snapshot_hash=tree_hash(file_hashes(snapshot, SNAPSHOT_PATTERNS)),
        acceptance=acceptance, regression=regression, structural=structural,
        judge=judge, judge_calls=calls,
        tampering=tamper_report(prepared, workspace_now, gates_now),
        frozen_manifest_hash=sha256_bytes(manifest_bytes),
    )
