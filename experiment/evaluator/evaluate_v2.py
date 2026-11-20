"""Independent evaluation for the version 2 study (experiment/protocol-v2.md).

Reuses the pilot evaluator's helpers (hashing, JUnit parsing, test-run
classification) without changing ``evaluate.py``, which stays hashed in the
pilot's ``frozen-manifest.json``. Everything the v2 evaluator judges by lives
outside agent workspaces and is hashed in ``experiment/v2/frozen-manifest.json``;
evaluation refuses to run if any of it has changed since the freeze.

For one session's final snapshot it reports, in separate fields:

- behaviour: each step's frozen acceptance test, and the baseline tests as a
  regression check (both must pass for a step to count as accepted);
- structural: the sensor with the v2 evaluator contract, after accepting only
  the reviewed legacy exception (``study_v2.accept_reviewed_exceptions``);
- the semantic judge's output on the final controllers (a judge output, not a
  label);
- tampering, plus whether the legacy reports controller was modified.

``structural_status`` is also used on each turn-end snapshot.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any

from evaluator import evaluate as ev

V2 = ev.EXPERIMENT_DIR / "v2"
ROOT = ev.ROOT
CONTRACT = V2 / "evaluator" / ".importlinter"
ACCEPTANCE_DIR = V2 / "evaluator" / "acceptance"
BASELINE_TESTS_DIR = V2 / "baseline" / "tests"
REVIEWED = V2 / "reviewed-exceptions.json"
MANIFEST = V2 / "frozen-manifest.json"
SCHEMA = "coding-agent-gates/evaluation-v2/v1"

FROZEN_PATTERNS = (
    "experiment/protocol-v2.md",
    "experiment/v2/study.json",
    "experiment/v2/instruction.md",
    "experiment/v2/scenarios/*.json",
    "experiment/v2/history/**",
    "experiment/v2/baseline/**",
    "experiment/v2/development.importlinter",
    "experiment/v2/reviewed-exceptions.json",
    "experiment/v2/evaluator/.importlinter",
    "experiment/v2/evaluator/acceptance/*.py",
    "experiment/evaluator/evaluate_v2.py",
    "experiment/tools/study_v2.py",
    "experiment/tools/prepare_v2.py",
    "experiment/tools/run_study_v2.py",
    "experiment/tools/experiment_stop_hook.py",
    "semantic/rubric.md",
)

WORKSPACE_PROTECTED = ("CLAUDE.md", "pyproject.toml")
BASELINE_TESTS = ("tests/conftest.py", "tests/test_catalog.py", "tests/test_customers.py",
                  "tests/test_orders.py", "tests/test_reports.py")
LEGACY_MODULE = "src/orders/controllers/reports.py"
SNAPSHOT_PATTERNS = ev.SNAPSHOT_PATTERNS

# Appended to the baseline tests' conftest in the regression work directory so
# a misconfigured run cannot silently test the wrong package.
REGRESSION_GUARD = '''

import os as _os
from pathlib import Path as _Path

import orders as _orders


@pytest.fixture(autouse=True)
def _snapshot_guard():
    expected = _os.environ.get("EVAL_SNAPSHOT_SRC")
    assert expected, "EVAL_SNAPSHOT_SRC is not set: run through the evaluator"
    imported = _Path(_orders.__file__).resolve()
    assert _Path(expected).resolve() in imported.parents, f"orders imported from {imported}"
'''


def current_frozen_hashes(root: Path = ROOT) -> dict[str, str]:
    return ev.file_hashes(root, FROZEN_PATTERNS)


def load_reviewed(path: Path = REVIEWED) -> dict[str, tuple[str, ...]]:
    import study_v2
    return study_v2.parse_reviewed(json.loads(Path(path).read_text(encoding="utf-8")))


def run_tests(snapshot: Path, files: Iterable[Path], conftest_text: str, workdir: Path, *,
              runner: Callable[..., Any] = subprocess.run, python: str = sys.executable,
              timeout: float = 300.0) -> ev.TestRun:
    """Copy ``files`` and a conftest into a fresh ``workdir``; run them against ``snapshot/src``."""
    workdir = Path(workdir)
    if workdir.exists():
        shutil.rmtree(workdir)  # our own per-run evaluation directory
    workdir.mkdir(parents=True)
    (workdir / "conftest.py").write_text(conftest_text, encoding="utf-8")
    names = []
    for f in files:
        shutil.copy2(f, workdir / Path(f).name)
        names.append(Path(f).name)
    (workdir / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    src = (Path(snapshot) / "src").resolve()
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONHOME")}
    env.update({"PYTHONPATH": f"{src}{os.pathsep}{workdir}", "EVAL_SNAPSHOT_SRC": str(src),
                "PYTHONDONTWRITEBYTECODE": "1"})
    report = workdir / "junit.xml"
    argv = [python, "-m", "pytest", "-q", "-c", str(workdir / "pytest.ini"), "--rootdir", str(workdir),
            "-p", "no:cacheprovider", "-p", "no:randomly", f"--junitxml={report}", *names]
    try:
        proc = runner(argv, cwd=workdir, env=env, capture_output=True, text=True, timeout=timeout,
                      check=False)
    except subprocess.TimeoutExpired:
        return ev.TestRun("error", None, None, None, None, None, f"timed out after {timeout}s")
    except OSError as exc:
        return ev.TestRun("error", None, None, None, None, None, f"could not run pytest: {exc}")
    junit = report.read_text(encoding="utf-8") if report.is_file() else None
    return ev.classify_test_run(proc.returncode, junit, (proc.stdout or "") + (proc.stderr or ""))


def acceptance_conftest() -> str:
    return (ACCEPTANCE_DIR / "conftest.py").read_text(encoding="utf-8")


def regression_conftest() -> str:
    return (BASELINE_TESTS_DIR / "conftest.py").read_text(encoding="utf-8") + REGRESSION_GUARD


def regression_files() -> list[Path]:
    return sorted(BASELINE_TESTS_DIR.glob("test_*.py"))


def structural(snapshot: Path, *, run_sensor: Callable[..., Any] | None = None,
               reviewed: Mapping[str, tuple[str, ...]] | None = None) -> dict[str, Any]:
    """The v2 evaluator contract on a snapshot, with only reviewed exceptions accepted."""
    import study_v2
    if run_sensor is None:
        from gates.sensor import run_sensor as _run_sensor
        run_sensor = _run_sensor
    raw = run_sensor(Path(snapshot), config=CONTRACT)
    accepted = study_v2.accept_reviewed_exceptions(raw, reviewed if reviewed is not None else load_reviewed())
    return {**accepted.to_dict(), "raw_status": raw.status.value}


def structural_status(snapshot: Path, **kwargs) -> str:
    return structural(snapshot, **kwargs)["status"]


def tamper_report(prepared: Mapping[str, Any], workspace_now: Mapping[str, str],
                  gates_now: Mapping[str, str]) -> dict[str, Any]:
    """As the pilot's tamper report, with the v2 workspace's protected files and tests."""
    before = dict(prepared.get("workspace", {}))
    pick = lambda d, keys: {k: v for k, v in d.items() if k in keys}  # noqa: E731
    protected = ev.compare_hashes(pick(before, WORKSPACE_PROTECTED), pick(workspace_now, WORKSPACE_PROTECTED))
    tests = ev.compare_hashes(pick(before, BASELINE_TESTS), pick(workspace_now, BASELINE_TESTS))
    gates = ev.compare_hashes(dict(prepared.get("gates", {})), dict(gates_now))
    settings_added = sorted(k for k in workspace_now if k.startswith(".claude/"))
    legacy = ev.compare_hashes(pick(before, (LEGACY_MODULE,)), pick(workspace_now, (LEGACY_MODULE,)))
    return {
        "detected": bool(protected["changed"] or protected["removed"] or any(gates.values()) or settings_added),
        "workspace_protected": protected,
        "gate_files": gates,
        "workspace_settings_added": settings_added,
        "baseline_tests_modified": sorted(tests["changed"] + tests["removed"]),
        "legacy_reports_modified": bool(legacy["changed"] or legacy["removed"]),
    }


def evaluate_session(snapshot: Path, scenario: Mapping[str, Any], prepared: Mapping[str, Any], *,
                     workdir: Path, gate_paths: Mapping[str, Path] | None = None, judge_provider: Any = None,
                     runner: Callable[..., Any] = subprocess.run, run_sensor: Callable[..., Any] | None = None,
                     manifest_path: Path = MANIFEST, root: Path = ROOT) -> dict[str, Any]:
    """Evaluate a session's final snapshot against every step of its scenario."""
    manifest_bytes = Path(manifest_path).read_bytes()
    ev.check_frozen(json.loads(manifest_bytes), current_frozen_hashes(root))
    snapshot = Path(snapshot)
    steps = {}
    for step in scenario["steps"]:
        steps[step["id"]] = run_tests(snapshot, [root / step["acceptance_test"]], acceptance_conftest(),
                                      Path(workdir) / "acceptance" / step["id"], runner=runner).to_json()
    regression = run_tests(snapshot, regression_files(), regression_conftest(), Path(workdir) / "regression",
                           runner=runner).to_json()
    if run_sensor is None:
        from gates.sensor import run_sensor as _run_sensor
        run_sensor = _run_sensor
    struct = structural(snapshot, run_sensor=run_sensor)
    judge = calls = None
    if judge_provider is not None:
        from gates.result import SensorResult
        from gates.semantic import judge as run_judge
        from gates.semantic import load_context
        sensor_result = SensorResult.from_dict({k: v for k, v in struct.items() if k != "raw_status"})
        judge = ev.judge_json(run_judge(sensor_result, load_context(snapshot), judge_provider))
        calls = [c.to_json() for c in getattr(judge_provider, "calls", [])]
    gates_now = {name: (ev.sha256_bytes(Path(p).read_bytes()) if Path(p).is_file() else "<missing>")
                 for name, p in (gate_paths or {}).items()}
    workspace_now = ev.file_hashes(snapshot, (*WORKSPACE_PROTECTED, *BASELINE_TESTS, LEGACY_MODULE, ".claude/**"))
    accepted = [sid for sid, r in steps.items() if r["status"] == "pass" and regression["status"] == "pass"]
    return {
        "schema": SCHEMA,
        "scenario_id": scenario["id"],
        "snapshot_tree_sha256": ev.tree_hash(ev.file_hashes(snapshot, SNAPSHOT_PATTERNS)),
        "frozen_manifest_sha256": ev.sha256_bytes(manifest_bytes),
        "submission": ev.SUBMISSION_NOTE,
        "behavior": {"steps": steps, "regression": regression, "steps_accepted": accepted,
                     "all_steps_accepted": len(accepted) == len(steps)},
        "structural": struct,
        "semantic_judge": judge,
        "semantic_judge_calls": calls or [],
        "semantic_label": None,
        "semantic_label_note": ev.NO_LABEL_NOTE,
        "tampering": tamper_report(prepared, workspace_now, gates_now),
    }
