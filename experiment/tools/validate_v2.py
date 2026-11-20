#!/usr/bin/env python3
"""Validate the version 2 fixtures with known passing and failing cases.

    .venv/bin/python experiment/tools/validate_v2.py --out evidence/v2-fixture-validation-2026-11-20.json [--live-judge]

For each scenario, in disposable copies under ``.tmp/v2-validation/``:

- baseline: every step's acceptance test FAILS, the baseline tests pass, and
  the structural check passes only because the legacy edge is a reviewed
  exception (raw status ``violation``, accepted status ``pass``);
- reference: every step passes, the baseline tests pass, structural pass;
- each variant in ``experiment/v2/evaluator/reference/negatives.py`` gives
  exactly its declared step failures, regression and structural results.

It also checks that the development and evaluator contracts are identical,
and that the workspace history rebuilds the baseline exactly
(``prepare_v2.build_workspace`` with real Git into ``.tmp``). With
``--live-judge`` it asks the live Claude Haiku 5.5 judge about the bases and
the variants that declare a ``judge`` expectation, charging the shared spend
ledger, and records agreement with those authored expectations (a count, not
an accuracy rate: the same author wrote the cases). Exit 0 when every
deterministic expectation holds, 1 otherwise. Judge disagreements are
reported but do not fail validation.
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
TOOLS = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "experiment"), str(TOOLS)]

import prepare_v2  # noqa: E402
from evaluator import evaluate as ev  # noqa: E402
from evaluator import evaluate_v2 as ev2  # noqa: E402
from gates.sensor import installed_import_linter_version  # noqa: E402

def _load_negatives():
    import importlib.util
    path = ROOT / "experiment" / "v2" / "evaluator" / "reference" / "negatives.py"
    spec = importlib.util.spec_from_file_location("v2_negatives", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.JUDGE_BASES, module.VARIANTS


JUDGE_BASES, VARIANTS = _load_negatives()

WORK = ROOT / ".tmp" / "v2-validation"
V2 = ROOT / "experiment" / "v2"


def load_scenarios() -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted((V2 / "scenarios").glob("*.json"))]


def build(dest: Path, scenario_key: str, base: str, edits=()) -> Path:
    if dest.exists():
        shutil.rmtree(dest)  # only our own disposable copy under .tmp/v2-validation
    shutil.copytree(V2 / "baseline" / "src", dest / "src", ignore=shutil.ignore_patterns("__pycache__"))
    if base == "reference":
        shutil.copytree(V2 / "evaluator" / "reference" / scenario_key, dest, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("__pycache__"))
    for rel, old, new in edits:
        path = dest / rel
        text = path.read_text(encoding="utf-8")
        if text.count(old) != 1:
            raise SystemExit(f"variant edit does not apply exactly once to {rel}: {old[:60]!r}")
        path.write_text(text.replace(old, new), encoding="utf-8")
    return dest


def evaluate(snapshot: Path, scenario: dict, workdir: Path) -> dict:
    steps = {s["id"]: ev2.run_tests(snapshot, [ROOT / s["acceptance_test"]], ev2.acceptance_conftest(),
                                    workdir / s["id"]).status for s in scenario["steps"]}
    regression = ev2.run_tests(snapshot, ev2.regression_files(), ev2.regression_conftest(),
                               workdir / "regression").status
    struct = ev2.structural(snapshot)
    return {"steps": steps, "regression": regression, "structural": struct["status"],
            "structural_raw": struct["raw_status"], "violations": struct["violations"]}


def check(observed: dict, expect: dict, step_ids: list[str], base_steps: dict | None) -> list[str]:
    problems = []
    failing = set(expect.get("steps_failing", []))
    for sid in step_ids:
        if sid in failing:
            want = "fail"
        elif base_steps is not None:
            want = base_steps[sid]
        else:
            want = expect["steps"]
        if observed["steps"][sid] != want:
            problems.append(f"{sid}: expected {want}, got {observed['steps'][sid]}")
    for key in ("regression", "structural", "structural_raw"):
        if key in expect and observed[key] != expect[key]:
            problems.append(f"{key}: expected {expect[key]}, got {observed[key]}")
    return problems


def judge_case(snapshot: Path, label: str, ledger: Path) -> dict:
    import spend_ledger
    from gates.claude_cli_judge import ClaudeCliJudgeProvider
    from gates.result import SensorResult
    from gates.semantic import judge, load_context
    provider = ClaudeCliJudgeProvider(guard=spend_ledger.FileSpendGuard(ledger, kind="judge"),
                                      label=f"v2 fixture validation: {label}")
    struct = ev2.structural(snapshot)
    outcome = judge(SensorResult.from_dict({k: v for k, v in struct.items() if k != "raw_status"}),
                    load_context(snapshot), provider)
    return {"status": outcome.status, "reason": outcome.reason, "provider_failed": outcome.provider_failed,
            "findings": [f.__dict__ for f in outcome.findings], "calls": [c.to_json() for c in provider.calls]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--live-judge", action="store_true")
    parser.add_argument("--ledger", type=Path, default=ROOT / "experiment" / "runs" / "spend-ledger.json")
    args = parser.parse_args()
    cases, problems, judged = [], [], []

    dev = (V2 / "development.importlinter").read_bytes()
    if dev != (V2 / "evaluator" / ".importlinter").read_bytes():
        problems.append("development and evaluator contracts differ")

    history_dir = WORK / "history-check"
    if history_dir.exists():
        shutil.rmtree(history_dir)
    head = prepare_v2.build_workspace(history_dir / "workspace")
    rebuilt = ev.file_hashes(history_dir / "workspace", ("src/**", "tests/**"))
    expected = {rel: h for rel, h in ev.file_hashes(V2 / "baseline", ("src/**", "tests/**")).items()}
    history_ok = rebuilt == expected
    if not history_ok:
        problems.append(f"workspace history does not rebuild the baseline: {ev.compare_hashes(expected, rebuilt)}")
    cases.append({"case": "workspace-history", "ok": history_ok, "head": head,
                  "commits": prepare_v2.git_log(history_dir / "workspace")})

    for scenario in load_scenarios():
        key = scenario["id"].split("-")[0].lower()
        step_ids = [s["id"] for s in scenario["steps"]]
        bases = {}
        for base, expect in (("baseline", {"steps": "fail", "regression": "pass", "structural": "pass",
                                           "structural_raw": "violation"}),
                             ("reference", {"steps": "pass", "regression": "pass", "structural": "pass",
                                            "structural_raw": "violation"})):
            snap = build(WORK / scenario["id"] / base / "snapshot", key, base)
            observed = evaluate(snap, scenario, WORK / scenario["id"] / base / "eval")
            bases[base] = observed
            found = check(observed, expect, step_ids, None)
            problems += [f"{scenario['id']} {base}: {p}" for p in found]
            cases.append({"scenario": scenario["id"], "case": base, "expect": expect, "observed": observed,
                          "ok": not found})
            if args.live_judge:
                judged.append({"scenario": scenario["id"], "case": base, "expected": JUDGE_BASES[base],
                               **judge_case(snap, f"{scenario['id']} {base}", args.ledger)})
        for variant in VARIANTS[scenario["id"]]:
            snap = build(WORK / scenario["id"] / variant["id"] / "snapshot", key, variant["base"], variant["edits"])
            observed = evaluate(snap, scenario, WORK / scenario["id"] / variant["id"] / "eval")
            found = check(observed, variant["expect"], step_ids, bases[variant["base"]]["steps"])
            problems += [f"{scenario['id']} {variant['id']}: {p}" for p in found]
            cases.append({"scenario": scenario["id"], "case": variant["id"], "base": variant["base"],
                          "note": variant.get("note"), "expect": variant["expect"], "observed": observed,
                          "ok": not found})
            if args.live_judge and "judge" in variant["expect"]:
                judged.append({"scenario": scenario["id"], "case": variant["id"],
                               "expected": variant["expect"]["judge"],
                               **judge_case(snap, f"{scenario['id']} {variant['id']}", args.ledger)})

    out = {
        "schema": "coding-agent-gates/v2-fixture-validation/v1",
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "environment": {"python": platform.python_version(), "platform": platform.platform(),
                        "import_linter": installed_import_linter_version()},
        "command": "experiment/tools/validate_v2.py" + (" --live-judge" if args.live_judge else ""),
        "deterministic_cases": len(cases), "deterministic_ok": sum(1 for c in cases if c["ok"]),
        "problems": problems, "cases": cases,
        "judge": None if not args.live_judge else {
            "note": "authored expectations, not independent labels; agreement is a count",
            "agreed": sum(1 for j in judged if j["status"] == j["expected"]), "total": len(judged),
            "cases": judged},
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(f"{out['deterministic_ok']}/{out['deterministic_cases']} deterministic cases as declared")
    for p in problems:
        print("PROBLEM:", p)
    if out["judge"]:
        print(f"judge agreed with the authored expectation {out['judge']['agreed']}/{out['judge']['total']}")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
