#!/usr/bin/env python3
"""Summarize a pilot from its retained run records. Every number traces to record.json files.

    .venv/bin/python experiment/tools/summarize.py --pilot pilot-2026-11-19 \\
        [--calibration evidence/live-judge-....json] [--out experiment/runs/<pilot>/summary.json]

Rules (experiment/analysis.md):

- Denominators are explicit: every attempted run counts, including runs the
  spend cap never started, runs that were not runnable, timeouts and errors.
- An accepted outcome is a run that completed within its budget, passed the
  frozen behavioural tests, passed the evaluator's structural contract and
  showed no tampering. The semantic judge's verdict is reported beside it,
  not folded in: it is a judge output without independent labels.
- Medians and spread (quartiles, min, max) for time, cost, token usage per
  category (agent, development judge, evaluation judge, each with observed
  and missing denominators) and repair cycles;
  censored repair loops are counted, never averaged as if finished.
- Total spend includes failed and unaccepted runs. Cost per accepted outcome
  is undefined (``None`` with a reason) when nothing was accepted.
- Judge false-positive/false-negative rates need independent human labels;
  without them they are reported as unavailable.
- Real and synthetic records are never mixed.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_record as rr  # noqa: E402

SCHEMA = "coding-agent-gates/pilot-summary/v1"
RATES_UNAVAILABLE = ("unavailable: false-positive and false-negative rates need independent human "
                     "labels, and none were supplied (Decisions, 2026-11-19)")


class MixedEvidence(ValueError):
    pass


def load_records(directory: Path) -> list[dict[str, Any]]:
    records = []
    for path in sorted(Path(directory).glob("*/record.json")):
        records.append(rr.loads(path.read_text(encoding="utf-8")))
    check_kinds(records)
    return records


def check_kinds(records: Iterable[Mapping[str, Any]]) -> str | None:
    kinds = {r.get("evidence_kind") for r in records}
    if len(kinds) > 1:
        raise MixedEvidence(f"refusing to mix evidence kinds {sorted(map(str, kinds))}")
    return next(iter(kinds), None)


def _dec(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        d = Decimal(str(value))
    except InvalidOperation:
        return None
    return d if d.is_finite() else None


def spread(values: Sequence[float | int | Decimal]) -> dict[str, Any]:
    """n, median, quartiles (linear interpolation), min and max. Empty input gives n=0 and Nones."""
    xs = sorted(Decimal(str(v)) for v in values)
    n = len(xs)
    if n == 0:
        return {"n": 0, "median": None, "q1": None, "q3": None, "min": None, "max": None}

    def q(p: Decimal) -> Decimal:
        pos = p * (n - 1)
        lo = int(pos)
        hi = min(lo + 1, n - 1)
        return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)

    def out(d: Decimal) -> str:
        return format(d.quantize(Decimal("0.0001")).normalize(), "f") if d != 0 else "0"

    return {"n": n, "median": out(q(Decimal("0.5"))), "q1": out(q(Decimal("0.25"))),
            "q3": out(q(Decimal("0.75"))), "min": out(xs[0]), "max": out(xs[-1])}


def accepted(record: Mapping[str, Any]) -> bool:
    """A not-runnable run (e.g. arm C with its development judge unavailable) is never
    accepted, whatever the agent and the final checks reported."""
    o = record["outcome"]
    return bool(o.get("termination") == "completed" and not o.get("not_runnable")
                and o.get("completed_within_budget") and o.get("behavior") == "pass"
                and o.get("structural") == "pass" and o.get("tampering_detected") is False)


def agent_started(record: Mapping[str, Any]) -> bool:
    """Whether the agent process ran. Records written before ``agent_started`` existed
    fall back to their termination."""
    o = record["outcome"]
    if "agent_started" in o:
        return bool(o["agent_started"])
    return o["termination"] not in ("not_started_cap", "not_runnable")


def run_spend(record: Mapping[str, Any]) -> tuple[Decimal, Decimal, bool]:
    """(known cost, charge held for unknown cost, whether anything is unknown) for one run,
    across the agent, the development judge and the evaluation judge, including retries."""
    known = held = Decimal(0)
    unknown = False

    def agent_part(ledger: Mapping[str, Any] | None, usage_cost: Any) -> None:
        nonlocal known, held, unknown
        cost = _dec(usage_cost)
        if cost is not None:
            known += cost
        elif ledger and ledger.get("agent_entry_id"):
            unknown = True
            held += _dec(ledger.get("charged_usd")) or Decimal(0)

    agent_part(record.get("ledger"), (record["usage"].get("agent") or {}).get("cost_usd"))
    for retry in record.get("infrastructure_retries") or []:
        led = retry.get("ledger") or {}
        agent_part(led, led.get("charged_usd") if led.get("cost_known") else None)
    def judge_parts(usage: Mapping[str, Any] | None) -> None:
        nonlocal known, held, unknown
        for key in ("development_judge", "evaluation_judge"):
            part = (usage or {}).get(key)
            if not part:
                continue
            known += _dec(part.get("known_cost_subtotal_usd")) or Decimal(0)
            if part.get("unknown_cost_calls"):
                unknown = True
                held += judge_held(part)

    judge_parts(record["usage"])
    for retry in record.get("infrastructure_retries") or []:
        judge_parts(retry.get("usage"))
    return known, held, unknown


def judge_held(part: Mapping[str, Any]) -> Decimal:
    """The ledger charge held for a judge part's unknown-cost calls.

    Records written by the current ``run_record.judge_usage`` carry it as
    ``unknown_cost_held_usd``. An older record without that field cannot say
    what was held; it contributes zero here and is counted separately by
    ``unrecorded_judge_holds`` so the omission stays visible."""
    return _dec(part.get("unknown_cost_held_usd")) or Decimal(0)


def unrecorded_judge_holds(record: Mapping[str, Any]) -> int:
    """Unknown-cost judge calls in one run (all attempts) whose held charge the record does not state."""
    n = 0
    parts = [record["usage"].get(k) for k in ("development_judge", "evaluation_judge")]
    for retry in record.get("infrastructure_retries") or []:
        parts += [(retry.get("usage") or {}).get(k) for k in ("development_judge", "evaluation_judge")]
    for part in parts:
        if not part or not part.get("unknown_cost_calls"):
            continue
        if "unknown_cost_held_usd" not in part:
            n += part["unknown_cost_calls"]
        else:
            n += part.get("unknown_cost_unrecorded_charge_calls") or 0
    return n


def agent_tokens(record: Mapping[str, Any]) -> dict[str, int | None]:
    """Per category, the run's agent tokens summed over every model the CLI reported,
    or None when the run reported no usage or any model lacks the category."""
    by_model = (record["usage"].get("agent") or {}).get("by_model")
    out: dict[str, int | None] = {}
    for key in rr.TOKEN_CATEGORIES:
        if not isinstance(by_model, Mapping) or not by_model:
            out[key] = None
            continue
        values = [m.get(key) if isinstance(m, Mapping) else None for m in by_model.values()]
        out[key] = None if any(type(v) is not int for v in values) else sum(values)
    return out


def judge_tokens(part: Mapping[str, Any] | None) -> dict[str, int | None] | None:
    """Per category, a judge part's tokens for one run; None for the whole part
    when the run started no judge calls of that kind (not applicable, not
    missing). A category is missing (None) when any started call did not report it.

    Records without ``tokens_missing_calls`` predate that field. Their sum is
    trusted only for a single started call, where presence proves that call
    reported it; otherwise the category is missing."""
    if not part or not part.get("started_calls"):
        return None
    tokens = part.get("tokens") or {}
    missing = part.get("tokens_missing_calls")
    out: dict[str, int | None] = {}
    for key in rr.TOKEN_CATEGORIES:
        value = tokens.get(key)
        if type(value) is not int:
            out[key] = None
        elif isinstance(missing, Mapping):
            out[key] = value if missing.get(key) == 0 else None
        else:
            out[key] = value if part.get("started_calls") == 1 else None
    return out


def token_distributions(per_run: Sequence[Mapping[str, int | None] | None]) -> dict[str, Any]:
    """Distribution per usage category with observed/missing denominators.

    ``per_run`` has one entry per started run; None means the source did not
    apply to that run (for example, no development judge in arm A or B)."""
    applicable = [r for r in per_run if r is not None]
    out: dict[str, Any] = {"started_runs": len(per_run), "applicable_runs": len(applicable)}
    for key in rr.TOKEN_CATEGORIES:
        observed = [r[key] for r in applicable if r.get(key) is not None]
        out[key] = {"observed_runs": len(observed), "missing_runs": len(applicable) - len(observed),
                    **spread(observed)}
    return out


def summarize_arm(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    outcomes = [r["outcome"] for r in records]
    count = lambda key: dict(sorted(Counter(str(o.get(key)) for o in outcomes).items()))  # noqa: E731
    started = [r for r in records if agent_started(r)]
    accepted_runs = [r for r in records if accepted(r)]
    repair = [r["repair"] for r in records if r["repair"].get("applicable")]
    converged = [p["cycles"] for p in repair if p.get("censored") is False and p.get("cycles") is not None]
    known = held = Decimal(0)
    unknown_runs = unrecorded_holds = 0
    for r in records:
        unrecorded_holds += unrecorded_judge_holds(r)
        k, h, u = run_spend(r)
        known, held = known + k, held + h
        unknown_runs += u
    total = known + held
    agent_costs = [_dec(r["usage"]["agent"].get("cost_usd")) for r in started]
    return {
        "attempted": len(records),
        "started": len(started),
        "termination": count("termination"),
        "completed_within_budget": sum(1 for o in outcomes if o.get("completed_within_budget")),
        "behavior": count("behavior"),
        "structural": count("structural"),
        "semantic_judge_output": count("semantic_judge"),
        "tampering_detected": sum(1 for o in outcomes if o.get("tampering_detected")),
        # Records written before the settings check existed have no field: not checked.
        "settings_file_check": dict(sorted(Counter(o.get("settings_file_check") or rr.SETTINGS_NOT_CHECKED
                                                   for o in outcomes).items())),
        "baseline_tests_modified": sum(1 for o in outcomes if o.get("baseline_tests_modified")),
        "gate_final_state": count("gate_final_state"),
        "not_runnable": sum(1 for o in outcomes if o.get("not_runnable")),
        "accepted": len(accepted_runs),
        "accepted_definition": "completed within budget AND behaviour pass AND structural pass AND no tampering",
        "repair_cycles": {"applicable_runs": len(repair), "converged_runs": len(converged),
                          "censored_runs": sum(1 for p in repair if p.get("censored")),
                          "converged_cycles": spread(converged),
                          "converged_with_zero_cycles": sum(1 for c in converged if c == 0)},
        "checker_invocations": {
            "sensor": sum(r["repair"]["checker_invocations"]["sensor"] for r in records),
            "development_judge_calls": sum(r["repair"]["checker_invocations"]["judge"] for r in records)},
        "time_s": {
            "attempt": spread([r["time"]["attempt_s"] for r in started if r["time"].get("attempt_s") is not None]),
            "model_api": spread([r["time"]["model_api_s"] for r in started if r["time"].get("model_api_s") is not None]),
            "check_sensor": spread([r["time"]["check_sensor_s"] for r in started
                                    if r["time"].get("check_sensor_s") is not None]),
            "check_judge": spread([r["time"]["check_judge_s"] for r in started
                                   if r["time"].get("check_judge_s") is not None]),
        },
        "agent_cost_usd": spread([c for c in agent_costs if c is not None]),
        "agent_usage_missing_runs": sum(1 for c in agent_costs if c is None),
        "usage_tokens": {
            "note": ("per started run and category; missing usage stays missing (counted in "
                     "missing_runs), never zero; judge sources apply only to runs that started a call"),
            "agent": token_distributions([agent_tokens(r) for r in started]),
            "development_judge": token_distributions(
                [judge_tokens(r["usage"].get("development_judge")) for r in started]),
            "evaluation_judge": token_distributions(
                [judge_tokens(r["usage"].get("evaluation_judge")) for r in started]),
        },
        "agent_turns": spread([r["usage"]["agent"]["num_turns"] for r in started
                               if r["usage"]["agent"].get("num_turns") is not None]),
        "spend_usd": {
            "known": str(known), "held_for_unknown_cost": str(held), "total_charged": str(total),
            "runs_with_unknown_cost": unknown_runs,
            "judge_unknown_cost_calls_without_recorded_hold": unrecorded_holds,
            "includes": "every attempt (failed, unaccepted and retried runs), development and evaluation judge calls",
        },
        "cost_per_accepted_outcome_usd": (str((total / len(accepted_runs)).quantize(Decimal("0.0001")))
                                          if accepted_runs else None),
        "cost_per_accepted_outcome_note": None if accepted_runs else
        "undefined: zero accepted outcomes",
    }


def paired(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    by_task: dict[str, dict[str, Any]] = {}
    for r in records:
        ident, o = r["identity"], r["outcome"]
        by_task.setdefault(ident["task_id"], {})[ident["arm"]] = {
            "termination": o["termination"], "behavior": o["behavior"], "structural": o["structural"],
            "semantic_judge": o["semantic_judge"], "gate_final_state": o["gate_final_state"],
            "accepted": accepted(r), "repair_cycles": r["repair"].get("cycles"),
            "position_in_task": ident.get("position_in_task")}
    return [{"task_id": t, "arms": dict(sorted(a.items()))} for t, a in sorted(by_task.items())]


def judge_section(records: Sequence[Mapping[str, Any]], calibration: Mapping[str, Any] | None) -> dict[str, Any]:
    final = Counter((r["identity"]["arm"], str(r["outcome"]["semantic_judge"])) for r in records)
    provider_failed = 0
    disagreements = []
    for r in records:
        ev_path = r["artifacts"].get("evaluation")
        evaluation = None
        if ev_path and (ROOT / ev_path).is_file():
            evaluation = json.loads((ROOT / ev_path).read_text(encoding="utf-8"))
        if evaluation and (evaluation.get("semantic_judge") or {}).get("provider_failed"):
            provider_failed += 1
        dev = r["usage"].get("development_judge")
        if r["identity"]["arm"] == "C" and dev is not None and evaluation:
            events_path = r["artifacts"].get("hook_events")
            last_dev = None
            if events_path and (ROOT / events_path).is_file():
                events, _ = rr.parse_events((ROOT / events_path).read_text().splitlines())
                sem = [e["semantic"]["status"] for e in events if isinstance(e.get("semantic"), Mapping)]
                last_dev = sem[-1] if sem else None
            final_status = (evaluation.get("semantic_judge") or {}).get("status")
            if last_dev and final_status and last_dev != final_status:
                disagreements.append({"run_id": r["identity"]["run_id"], "development_last": last_dev,
                                      "evaluation": final_status})
    cal = None
    if calibration:
        rows = [x for x in calibration.get("results", []) if x.get("kind") == "calibration"]
        agree = Counter((x.get("authored_label"), (x.get("outcome") or {}).get("status")) for x in rows)
        cal = {"source": calibration.get("_source"), "cases": len(rows),
               "authored_label_vs_judge": {f"{a} -> {b}": n for (a, b), n in sorted(agree.items())},
               "agreements": sum(n for (a, b), n in agree.items() if a == b),
               "note": "agreement with authored labels is a count, not an accuracy rate"}
    return {
        "final_snapshot_judge_output_by_arm": {f"{a}:{s}": n for (a, s), n in sorted(final.items())},
        "evaluation_judge_provider_failures": provider_failed,
        "arm_c_development_vs_evaluation_disagreements": disagreements,
        "calibration": cal,
        "false_positive_rate": None, "false_negative_rate": None, "rates_note": RATES_UNAVAILABLE,
    }


def summarize(records: Sequence[Mapping[str, Any]], *, pilot: str, calibration: Mapping[str, Any] | None = None,
              plan_size: int | None = None) -> dict[str, Any]:
    kind = check_kinds(records)
    arms = sorted({r["identity"]["arm"] for r in records})
    return {
        "schema": SCHEMA,
        "pilot": pilot,
        "evidence_kind": kind,
        "planned_runs": plan_size,
        "records": len(records),
        "missing_records": (plan_size - len(records)) if plan_size is not None else None,
        "by_arm": {a: summarize_arm([r for r in records if r["identity"]["arm"] == a]) for a in arms},
        "paired_by_task": paired(records),
        "judge": judge_section(records, calibration),
        "models": sorted({m for r in records for m in (r["identity"].get("agent_models_reported") or [])}),
        "environments": sorted({json.dumps(r["identity"].get("environment"), sort_keys=True) for r in records}),
        "limits": [
            "one run per task and arm (10 x 3 x 1): exploratory, not a powered comparison",
            "one agent model, one effort level, one CLI version, one machine",
            "semantic outcomes are judge outputs without independent labels",
            "the rubric covers controller business decisions only; instructed rules outside it are not checked",
            "tamper detection compared the external --settings file only where settings_file_check is not "
            "'not_checked'",
            "costs are the CLI's API-equivalent estimates, notional under a subscription login",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pilot", required=True)
    parser.add_argument("--calibration", type=Path, default=None, help="live-judge evidence JSON with calibration cases")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    directory = ROOT / "experiment" / "runs" / args.pilot
    records = load_records(directory)
    plan_path = directory / "order.json"
    plan_size = len(json.loads(plan_path.read_text())["runs"]) if plan_path.is_file() else None
    calibration = None
    if args.calibration:
        calibration = json.loads(args.calibration.read_text())
        calibration["_source"] = args.calibration.resolve().relative_to(ROOT).as_posix()
    summary = summarize(records, pilot=args.pilot, calibration=calibration, plan_size=plan_size)
    text = json.dumps(summary, indent=2) + "\n"
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
