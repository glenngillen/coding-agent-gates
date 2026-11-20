#!/usr/bin/env python3
"""Run the live Claude Haiku 5.5 judge once over the committed fixtures and
calibration set, and write the real verdicts, latency and cost to evidence/.

    .venv/bin/python experiment/tools/run_live_judge.py

The judge is Claude Haiku 5.5 called through the logged-in Claude Code CLI
(``gates.claude_cli_judge``); no API key is needed or read.

For each scenario in fixtures/scenarios.json, a disposable copy of the example
(under .tmp/live-judge/) gets the scenario's overlay; the real structural
sensor runs first and the judge is called only if it passes, exactly as in
``gates.semantic.judge``. Each case in experiment/calibration/*.json is judged
directly on its supplied controller source. Its authored label is recorded
next to the verdict; agreement is a count, not an accuracy rate (no
independent human labels exist).

Every call consults the shared spend ledger (experiment/runs/spend-ledger.json)
before starting and updates it afterwards, charging the CLI's reported
``total_cost_usd`` (an API-equivalent estimate; notional under a subscription
login). Each call reserves its worst-case cost (see ``gates.claude_cli_judge``)
and the ledger refuses it before launch if that would pass the cap. No
``claude`` CLI on PATH: exit 5 before any call and write nothing. Spend cap
reached, or a call whose usage or cost broke its bound: stop starting calls,
record the remaining cases as not run, exit 6. There is no synthetic fallback.
"""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "src"), str(Path(__file__).resolve().parent)]

import spend_ledger  # noqa: E402
from gates import claude_cli_judge as cj  # noqa: E402
from gates.semantic import (  # noqa: E402
    JudgeOutcome,
    SourceFile,
    build_request,
    judge,
    load_context,
    parse_verdict,
)
from gates.sensor import run_sensor  # noqa: E402

SKIP = {".venv", ".tmp", "__pycache__", ".hypothesis", ".pytest_cache", ".git", ".claude",
        "experiment", "evidence"}
EXIT_NO_CLI, EXIT_CAP = 5, 6


def scenario_copy(scenario: dict, work: Path) -> Path:
    dest = work / scenario["id"]
    if dest.exists():
        shutil.rmtree(dest)  # only ever our own disposable copy under .tmp/live-judge
    shutil.copytree(ROOT, dest, ignore=lambda _d, names: [n for n in names if n in SKIP])
    (dest / ".venv").symlink_to(ROOT / ".venv", target_is_directory=True)
    if scenario.get("overlay"):
        shutil.copytree(ROOT / scenario["overlay"], dest, dirs_exist_ok=True)
    return dest


def calibration_cases() -> tuple[list[dict], list[str]]:
    cases, sources = [], []
    for path in sorted((ROOT / "experiment" / "calibration").glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        sources.append(path.relative_to(ROOT).as_posix())
        for case in data.get("cases", []):
            cases.append({**case, "source": path.relative_to(ROOT).as_posix()})
    return cases, sources


def outcome_json(outcome) -> dict:
    return {
        "status": outcome.status, "reason": outcome.reason,
        "findings": [f.__dict__ for f in outcome.findings], "raw_response": outcome.raw_response,
    }


def summarize_costs(calls: list[dict]) -> dict:
    """Aggregate per-call cost records without passing off a subtotal as a total.

    A call *started* when the ledger accepted its reservation (``ledger_entry_id``
    set); a call the ledger refused never reached the API and costs nothing. A
    started call whose usage is unknown (API failure, malformed usage) has
    ``cost_usd`` None: its real cost is unknown, its reservation stays held in
    the ledger, and the complete total is unavailable (None) while any exist.
    """
    started = [c for c in calls if c.get("ledger_entry_id")]
    known = [c for c in started if c.get("cost_usd") is not None]
    unknown = [c for c in started if c.get("cost_usd") is None]
    subtotal = sum((Decimal(c["cost_usd"]) for c in known), Decimal(0))
    held = sum((Decimal(c["reservation_usd"]) for c in unknown), Decimal(0))
    return {
        "started_calls": len(started),
        "ledger_refused_calls": len(calls) - len(started),
        "known_cost_calls": len(known),
        "unknown_cost_calls": len(unknown),
        "known_cost_subtotal_usd": str(subtotal),
        "unknown_cost_reserved_usd": str(held),
        "total_cost_usd": None if unknown else str(subtotal),
        "total_cost_note": (
            f"unavailable: {len(unknown)} started call(s) have unknown cost; "
            f"known-cost subtotal is a lower bound, ledger still holds US${held} "
            "in reservations for them" if unknown else "complete: every started call has a cost"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ledger", type=Path, default=spend_ledger.DEFAULT_PATH)
    parser.add_argument("--out", type=Path, default=None, help="evidence JSON path")
    args = parser.parse_args()

    cli_path = shutil.which(cj.CLI)
    if cli_path is None:
        print(f"NOT RUN: the {cj.CLI!r} CLI is not on PATH. No call was made and no evidence "
              "was written.", file=sys.stderr)
        return EXIT_NO_CLI
    cli_version = subprocess.run([cli_path, "--version"], capture_output=True, text=True,
                                 timeout=30, check=False).stdout.strip()

    guard = spend_ledger.FileSpendGuard(args.ledger, "judge")
    started = datetime.now(timezone.utc)
    work = ROOT / ".tmp" / "live-judge"
    work.mkdir(parents=True, exist_ok=True)
    judge_cwd = work / "judge-cwd"  # empty directory: no project files near the CLI
    judge_cwd.mkdir(exist_ok=True)
    results, cap_reached, bound_broken = [], False, False

    def call(label: str, fn) -> dict:
        nonlocal cap_reached, bound_broken
        if cap_reached or bound_broken:
            why = ("ledger refused an earlier call in this run" if cap_reached else
                   "an earlier call broke its spend bound in this run")
            return {"judge_called": False, "not_run": why}
        provider = cj.ClaudeCliJudgeProvider(guard, label=label, cwd=str(judge_cwd))
        outcome = fn(provider)
        last = provider.calls[-1] if provider.calls else None
        if last and last.ledger_entry_id is None and (last.error or "").startswith("not started:"):
            cap_reached = True  # the ledger refused (cap) or was unusable: start nothing more
        if any(c.bound_exceeded for c in provider.calls):
            bound_broken = True  # the bound's assumptions failed: start nothing more
        return {"judge_called": any(c.ledger_entry_id for c in provider.calls),
                "outcome": outcome_json(outcome), "calls": [c.to_json() for c in provider.calls]}

    for scenario in json.loads((ROOT / "fixtures" / "scenarios.json").read_text())["scenarios"]:
        copy = scenario_copy(scenario, work)
        structural = run_sensor(copy)
        files = load_context(copy)
        entry = {"kind": "fixture", "id": scenario["id"], "structural": structural.status.value,
                 "expected_structural": scenario["expected_status"], "teaches": scenario["teaches"]}
        entry.update(call(f"fixture:{scenario['id']}", lambda p: judge(structural, files, p)))
        results.append(entry)

    cases, calibration_sources = calibration_cases()
    for case in cases:
        files = tuple(SourceFile(f["path"], f["text"]) for f in case["files"])
        entry = {"kind": "calibration", "id": case["id"], "source": case["source"],
                 "authored_label": case.get("label")}

        def run_case(p, files=files):
            try:
                return parse_verdict(p(build_request(files)), files)
            except Exception as exc:  # noqa: BLE001 - any failure is inconclusive, as in judge()
                return JudgeOutcome("inconclusive", f"provider error: {exc}")

        entry.update(call(f"calibration:{case['id']}", run_case))
        results.append(entry)

    calls = [c for r in results for c in r.get("calls", [])]
    durations = [c["duration_ms"] for c in calls if c.get("duration_ms") is not None]
    walls = [c["wall_s"] for c in calls if c.get("wall_s") is not None]
    evidence = {
        "schema": "coding-agent-gates/live-judge-run/v1",
        "started_at": started.isoformat(timespec="seconds"),
        "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": cj.MODEL,
        "transport": "Claude Code CLI, logged-in session (no API key read)",
        "command": cj.command(cj.MODEL, "<rubric instructions from semantic/rubric.md>",
                              "<per-call budget: call_bound().budget_usd>"),  # type: ignore[arg-type]
        "child_env_added": cj.CHILD_ENV,
        "spend_bound": {
            "method": "reservation = budget + one response; one response priced at the model's "
                      "documented context window and maximum output at the highest Haiku 5.5 "
                      "rates; budget = expected normal call (payload + framing allowance + "
                      "output cap) at the same rates",
            "model_context_window_tokens": cj.MODEL_CONTEXT_WINDOW_TOKENS,
            "model_max_output_tokens": cj.MODEL_MAX_OUTPUT_TOKENS,
            "response_usd_max": str(cj.RESPONSE_USD_MAX),
            "max_input_bytes": cj.MAX_INPUT_BYTES,
            "budget_framing_allowance_tokens": cj.FRAMING_ALLOWANCE_TOKENS,
            "budget_max_output_tokens": cj.MAX_OUTPUT_TOKENS,
            "input_usd_per_mtok_max": str(cj.INPUT_USD_PER_TOKEN_MAX * 1_000_000),
            "output_usd_per_mtok_max": str(cj.OUTPUT_USD_PER_TOKEN_MAX * 1_000_000),
        },
        "timeout_s": cj.TIMEOUT_S,
        "cost_basis": cj.COST_BASIS,
        "environment": {"python": platform.python_version(), "platform": platform.platform(),
                        "claude_cli": cli_version},
        "calibration_sources": calibration_sources or None,
        "calibration_note": None if cases else
            "no calibration set is committed under experiment/calibration/ yet; fixtures only",
        "summary": {
            **summarize_costs(calls),
            "cli_duration_ms": ({"min": min(durations), "max": max(durations)}
                                if durations else None),
            "wall_s": {"min": min(walls), "max": max(walls)} if walls else None,
            "spend_cap_reached": cap_reached,
            "spend_bound_broken": bound_broken,
            "ledger": str(args.ledger.relative_to(ROOT) if args.ledger.is_relative_to(ROOT)
                          else args.ledger),
        },
        "results": results,
    }
    out = args.out or ROOT / "evidence" / f"live-judge-{started:%Y%m%d}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    for r in results:
        status = r.get("outcome", {}).get("status", r.get("not_run"))
        cost = ",".join("US$" + (c.get("cost_usd") or "?") for c in r.get("calls", []))
        print(f"{r['kind']:<11} {r['id']:<28} {status:<14} {cost or 'judge not called'}")
    cost_summary = evidence["summary"]
    print(f"cost: {cost_summary['total_cost_note']}; known-cost subtotal "
          f"US${cost_summary['known_cost_subtotal_usd']}")
    print(f"wrote {out.relative_to(ROOT) if out.is_relative_to(ROOT) else out}")
    return EXIT_CAP if cap_reached or bound_broken else 0


if __name__ == "__main__":
    sys.exit(main())
