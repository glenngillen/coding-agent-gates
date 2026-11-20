#!/usr/bin/env python3
"""Write experiment/results-v5.md from the retained version 5 records.

    .venv/bin/python experiment/tools/summarize_v5.py --study NAME --out FILE [--json FILE]

Reports the counts fixed in ``protocol-v5.md`` with the frozen statistics in
``study_v2.py``: per condition x arm x agent, and pooled over agents.
Descriptive only. Not frozen.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
TOOLS = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "experiment"), str(TOOLS)]

import study_v2  # noqa: E402
import summarize_v2 as s2  # noqa: E402

CONDITIONS = ("stated", "one-line", "stated+shortcut", "stated+conflict")
LABEL = {"stated": "Rule stated", "one-line": "One-line hint", "stated+shortcut": "Rule stated, shortcut requested",
         "stated+conflict": "Rule stated, contradictory nested file"}
ARM = {"A": "no gate", "B": "gate"}
MODELS = ("haiku45", "haiku")
MODEL = {"haiku45": "Haiku 4.5", "haiku": "Haiku 5.5"}


def summarize(records: list[dict], plan: list[dict]) -> dict[str, Any]:
    ident = lambda r: r["identity"]  # noqa: E731
    cells = study_v2.summarize_cells(records, key=lambda r: (ident(r)["guidance"], ident(r)["arm"], ident(r)["model_key"]))
    extra: dict[tuple, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for r in records:
        g = extra[(ident(r)["guidance"], ident(r)["arm"], ident(r)["model_key"])]
        beh = r["outcome"].get("behavior") or {}
        g["all_accepted"].append(bool(beh.get("all_steps_accepted")))
        g["steps_accepted"].append(len(beh.get("steps_accepted") or []))
        g["repairs"].append(r["repair"]["requests"] if r["repair"]["applicable"] else None)
        g["judge"].append(r["outcome"].get("semantic_judge"))
        g["termination"].append(r["outcome"]["termination"])
        g["tampering"].append(bool(r["outcome"].get("tampering_detected")))
        if r["time"].get("session_s") is not None:
            g["time"].append(r["time"]["session_s"])
        if (c := s2.agent_cost(r)) is not None:
            g["cost"].append(c)
    slips = [{"run_id": ident(r)["run_id"], "step": t["step"], "new_edges": t.get("new_edges"), "caught": t.get("caught"),
              "repaired": t.get("repaired"), "repair_requests": t.get("repair_requests"),
              "final_structural": r["outcome"].get("final_structural")}
             for r in records for t in r["turns"] if t.get("slip")]
    planned, recorded = {p["run_id"] for p in plan}, {ident(r)["run_id"] for r in records}
    return {"cells": cells, "extra": extra, "slips": slips,
            "terminations": Counter(r["outcome"]["termination"] for r in records),
            "missing": sorted(planned - recorded),
            "models_reported": Counter(m for r in records for m in ident(r).get("agent_models_reported") or []),
            "agent_cost": sum((c for r in records if (c := s2.agent_cost(r)) is not None), Decimal(0)),
            "judge_cost": sum((s2.judge_cost(r) for r in records), Decimal(0))}


def render(study: str, records: list[dict], plan: list[dict], s: dict[str, Any]) -> str:
    lines = [
        "# Version 5 results: a stated rule on an older model, with and without the gate", "",
        f"Study `{study}`, protocol [`protocol-v5.md`](protocol-v5.md). Written by `tools/summarize_v5.py` from "
        f"{len(records)} retained records (`runs/{study}/`); {len(plan)} sessions were planned.", "",
        "Descriptive counts only. Rates are `k/n` with exact one-sided 95% bounds in brackets. Six sessions per row "
        "(two scenarios, three repeats). Costs are CLI-reported and API-equivalent.", ""]
    for m in MODELS:
        lines += [f"## {MODEL[m]}", "",
                  "| Condition, arm | Sessions with a slip | Turn slips | Caught | Repaired in the turn "
                  "| Final snapshot violates the rule | All four steps accepted | Repair requests |",
                  "| --- | --- | --- | --- | --- | --- | --- | --- |"]
        for cond in CONDITIONS:
            for arm in ("A", "B"):
                c, g = s["cells"].get((cond, arm, m)), s["extra"].get((cond, arm, m))
                label = f"{LABEL[cond]}, {ARM[arm]}"
                if not c:
                    lines.append(f"| {label} | no sessions | | | | | | |")
                    continue
                gated = arm == "B"
                repairs = sum(x for x in g["repairs"] if x is not None)
                lines.append(
                    f"| {label} | {s2.rate(c['sessions_with_slip'], c['sessions'], c['session_slip_lower95'], c['session_slip_upper95'])} "
                    f"| {c['turn_slips']}/{c['turns']} | {f'''{c['caught']}/{c['turn_slips']}''' if gated else 'n/a'} "
                    f"| {f'''{c['repaired']}/{c['turn_slips']}''' if gated else 'n/a'} "
                    f"| {s2.rate(c['final_violations'], c['final_known'], c['final_violation_lower95'], c['final_violation_upper95'])} "
                    f"| {sum(g['all_accepted'])}/{len(g['all_accepted'])} | {repairs if gated else 'n/a'} |")
        lines.append("")
    lines += ["## Time, cost and the judge's verdict", "",
              "| Condition, arm, agent | Sessions | Median session time | Mean agent cost per session "
              "| Acceptance steps passed | Judge: violation / pass / not evaluated |", "| --- | --- | --- | --- | --- | --- |"]
    for m in MODELS:
        for cond in CONDITIONS:
            for arm in ("A", "B"):
                g = s["extra"].get((cond, arm, m))
                if not g:
                    continue
                mean = sum(g["cost"], Decimal(0)) / len(g["cost"]) if g["cost"] else None
                v = Counter(g["judge"])
                lines.append(f"| {LABEL[cond]}, {ARM[arm]}, {MODEL[m]} | {len(g['judge'])} | {s2.median(g['time'])} "
                             f"| {'n/a' if mean is None else f'US${mean:.3f}'} | {sum(g['steps_accepted'])}/{4 * len(g['judge'])} "
                             f"| {v['violation']} / {v['pass']} / {v['not_evaluated']} |")
    lines += ["", "## Every slip", ""]
    if s["slips"]:
        lines += ["| Session | Step | New forbidden imports | Caught | Repaired | Repair requests | Final snapshot |",
                  "| --- | --- | --- | --- | --- | --- | --- |"]
        show = lambda v: "n/a" if v is None else ("yes" if v else "no")  # noqa: E731
        for x in s["slips"]:
            edges = ", ".join(f"`{a.removeprefix('orders.')}` → `{b.removeprefix('orders.')}`" for a, b in (x["new_edges"] or []))
            lines.append(f"| `{x['run_id']}` | {x['step']} | {edges} | {show(x['caught'])} | {show(x['repaired'])} "
                         f"| {x['repair_requests'] if x['repair_requests'] is not None else 'n/a'} | {x['final_structural']} |")
    else:
        lines.append("None.")
    tamper = sum(sum(g["tampering"]) for g in s["extra"].values())
    lines += ["", "## Completeness and integrity", "",
              f"- Terminations: {', '.join(f'{k} {v}' for k, v in sorted(s['terminations'].items()))}.",
              f"- Planned sessions without a record: {len(s['missing'])}" + (f" ({', '.join(s['missing'])})" if s["missing"] else "") + ".",
              f"- Models reported by the CLI: {', '.join(f'{k} ({v} sessions)' for k, v in sorted(s['models_reported'].items()))}.",
              f"- Sessions with tampering detected: {tamper}.",
              f"- Reported spend: agent US${s['agent_cost']:.2f}, evaluation judge US${s['judge_cost']:.2f}.", ""]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--study", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args()
    study_dir = ROOT / "experiment" / "runs" / args.study
    records = s2.load_records(study_dir)
    plan = json.loads((study_dir / "order.json").read_text())["runs"]
    s = summarize(records, plan)
    args.out.write_text(render(args.study, records, plan, s), encoding="utf-8")
    if args.json:
        payload = {"cells": {"|".join(k): v for k, v in s["cells"].items()},
                   "extra": {"|".join(k): {"all_accepted": sum(g["all_accepted"]), "sessions": len(g["judge"]),
                                           "steps_accepted": sum(g["steps_accepted"]),
                                           "repair_requests": sum(x for x in g["repairs"] if x is not None),
                                           "median_session_s": statistics.median(g["time"]) if g["time"] else None,
                                           "mean_cost_usd": str(sum(g["cost"], Decimal(0)) / len(g["cost"])) if g["cost"] else None,
                                           "judge": {str(k): v for k, v in Counter(g["judge"]).items()}} for k, g in s["extra"].items()},
                   "slips": s["slips"], "terminations": dict(s["terminations"]), "missing": s["missing"]}
        args.json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {args.out} from {len(records)} records")
    return 0


if __name__ == "__main__":
    sys.exit(main())
