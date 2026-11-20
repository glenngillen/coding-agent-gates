#!/usr/bin/env python3
"""Validate the frozen acceptance tests against the baseline, the reference
implementations and their negative variants.

    .venv/bin/python experiment/tools/validate_tasks.py [--out evidence/task-validation.json]

For every task in experiment/tasks/, in a disposable copy under
.tmp/task-validation/:

- baseline: the acceptance test must FAIL (the feature is missing), the
  regression test must pass and the evaluator's contract must pass;
- reference: acceptance, regression and contract must all pass;
- each negative variant (experiment/evaluator/reference/negatives.py) must
  produce exactly the outcome it declares.

This is the dedicated validation command for the acceptance tests. It runs
real pytest and lint-imports processes, so it is not part of the unit suite
(which runs against the baseline, where every acceptance test fails by
design). Exit 0 when every expectation holds, 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "experiment")]

from evaluator import evaluate as ev  # noqa: E402
from evaluator.reference.negatives import VARIANTS  # noqa: E402
from gates.sensor import installed_import_linter_version, run_sensor  # noqa: E402

WORK = ROOT / ".tmp" / "task-validation"


def load_tasks() -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8"))
            for p in sorted((ROOT / "experiment" / "tasks").glob("*.json"))]


def build(dest: Path, overlay: Path | None = None, edits=()) -> Path:
    if dest.exists():
        shutil.rmtree(dest)  # only our own disposable copy under .tmp/task-validation
    shutil.copytree(ROOT / "src" / "orders", dest / "src" / "orders",
                    ignore=shutil.ignore_patterns("__pycache__"))
    if overlay is not None:
        shutil.copytree(overlay, dest, dirs_exist_ok=True)
    for rel, old, new in edits:
        path = dest / rel
        text = path.read_text(encoding="utf-8")
        if text.count(old) != 1:
            raise SystemExit(f"variant edit does not apply exactly once to {rel}: {old[:60]!r}")
        path.write_text(text.replace(old, new), encoding="utf-8")
    return dest


def outcome(snapshot: Path, task: dict) -> dict:
    acceptance = ev.run_tests(snapshot, [ROOT / task["acceptance_test"]], snapshot / ".work" / "a")
    regression = ev.run_tests(snapshot, [ev.REGRESSION_TEST], snapshot / ".work" / "r")
    structural = run_sensor(snapshot, config=ev.CONTRACT)
    return {"acceptance": acceptance.status, "regression": regression.status,
            "behavior": ev.behavior_status(acceptance, regression),
            "structural": structural.status.value,
            "acceptance_counts": [acceptance.tests, acceptance.failures, acceptance.errors]}


def check(observed: dict, expect: dict) -> list[str]:
    return [f"{k}: expected {v}, observed {observed.get(k)}" for k, v in expect.items()
            if observed.get(k) != v]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    ev.check_frozen(ev.load_manifest(), ev.current_frozen_hashes())

    rows, problems = [], []
    for task in load_tasks():
        short = task["id"].split("-")[0].lower()
        cases = [("baseline", None, (), {"acceptance": "fail", "regression": "pass", "structural": "pass"}),
                 ("reference", ROOT / task["reference_overlay"], (),
                  {"acceptance": "pass", "regression": "pass", "structural": "pass"})]
        for variant in VARIANTS.get(short, []):
            cases.append((variant["id"], ROOT / task["reference_overlay"], variant["edits"], variant["expect"]))
        for name, overlay, edits, expect in cases:
            snapshot = build(WORK / short / name, overlay, edits)
            observed = outcome(snapshot, task)
            failed = check(observed, expect)
            rows.append({"task": task["id"], "case": name, "expect": expect, "observed": observed,
                         "ok": not failed})
            problems += [f"{task['id']} {name}: {f}" for f in failed]
            print(f"{'ok ' if not failed else 'BAD'} {task['id']:<22} {name:<32} {observed}")

    report = {
        "schema": "coding-agent-gates/task-validation/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "command": "experiment/tools/validate_tasks.py",
        "environment": {"python": platform.python_version(), "platform": platform.platform(),
                        "import_linter": installed_import_linter_version()},
        "frozen_manifest_sha256": ev.sha256_bytes(ev.MANIFEST.read_bytes()),
        "cases": rows,
        "problems": problems,
    }
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"{len(rows) - len(problems)} of {len(rows)} cases as expected" if not problems
          else "\n".join(["PROBLEMS:"] + problems))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
