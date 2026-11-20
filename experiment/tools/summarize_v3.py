#!/usr/bin/env python3
"""Write experiment/results-v3.md from the retained version 3 records.

    .venv/bin/python experiment/tools/summarize_v3.py --study NAME --out FILE [--json FILE]

Reads every ``experiment/runs/<study>/<run_id>/record.json`` and the plan, and
reports the counts fixed in ``protocol-v3.md`` ("Reporting rule") with the
frozen statistics in ``study_v2.py``. Descriptive only. Not frozen: it presents
records, it does not define outcomes.
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

GUIDANCE = ("stated", "one-line", "unstated")
GUIDANCE_LABEL = {"stated": "Rule stated", "one-line": "One-line hint", "unstated": "Rule unstated"}
ARM_LABEL = {"A": "no gate", "B": "gate"}
MODEL_LABEL = {"sonnet": "Sonnet 5.5", "haiku": "Haiku 5.5"}


def guidance_of(record: dict) -> str:
    return record["identity"]["guidance"]


def summarize(records: list[dict], plan: list[dict]) -> dict[str, Any]:
    ident = lambda r: r["identity"]  # noqa: E731
    by_ga = study_v2.summarize_cells(records, key=lambda r: (guidance_of(r), ident(r)["arm"]))
    by_gam = study_v2.summarize_cells(records, key=lambda r: (guidance_of(r), ident(r)["arm"], ident(r)["model_key"]))
    by_gas = study_v2.summarize_cells(records, key=lambda r: (guidance_of(r), ident(r)["arm"], ident(r)["scenario_id"]))
    groups: dict[tuple, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for r in records:
        for key in ((guidance_of(r), ident(r)["arm"]), (guidance_of(r), ident(r)["arm"], ident(r)["model_key"])):
            g = groups[key]
            if r["time"].get("session_s") is not None:
                g["session_s"].append(r["time"]["session_s"])
            if (c := s2.agent_cost(r)) is not None:
                g["agent_cost"].append(c)
            g["repair_requests"].append(r["repair"]["requests"] if r["repair"]["applicable"] else None)
            beh = r["outcome"].get("behavior") or {}
            g["all_accepted"].append(bool(beh.get("all_steps_accepted")))
            g["steps_accepted"].append(len(beh.get("steps_accepted") or []))
            g["tampering"].append(bool(r["outcome"].get("tampering_detected")))
            g["legacy_modified"].append(bool(r["outcome"].get("legacy_reports_modified")))
            g["persisting"].append(sum(1 for t in r["turns"] if t.get("persisting_violation")))
            g["slip_sessions_s"].append(r["time"].get("session_s") if any(t.get("slip") for t in r["turns"]) else None)
    slips = [{"run_id": ident(r)["run_id"], "guidance": guidance_of(r), "arm": ident(r)["arm"],
              "model_key": ident(r)["model_key"], "scenario_id": ident(r)["scenario_id"], "step": t["step"],
              "new_edges": t.get("new_edges"), "caught": t.get("caught"), "repaired": t.get("repaired"),
              "repair_requests": t.get("repair_requests"), "final_structural": r["outcome"].get("final_structural")}
             for r in records for t in r["turns"] if t.get("slip")]
    planned = {p["run_id"] for p in plan}
    recorded = {ident(r)["run_id"] for r in records}
    return {"by_ga": by_ga, "by_gam": by_gam, "by_gas": by_gas, "groups": groups, "slips": slips,
            "terminations": Counter(r["outcome"]["termination"] for r in records),
            "missing": sorted(planned - recorded), "extra": sorted(recorded - planned),
            "agent_cost": sum((c for r in records if (c := s2.agent_cost(r)) is not None), Decimal(0)),
            "judge_cost": sum((s2.judge_cost(r) for r in records), Decimal(0))}


def _rate(c: dict, k: str, n: str, lo: str, hi: str) -> str:
    return s2.rate(c[k], c[n], c.get(lo), c.get(hi))


def _row(label: str, c: dict | None, g: dict | None, gated: bool) -> str:
    if not c:
        return f"| {label} | no sessions | | | | | |"
    caught = f"{c['caught']}/{c['turn_slips']}" if gated else "n/a"
    repaired = f"{c['repaired']}/{c['turn_slips']}" if gated else "n/a"
    accepted = f"{sum(g['all_accepted'])}/{len(g['all_accepted'])}" if g else ""
    return (f"| {label} | {_rate(c, 'sessions_with_slip', 'sessions', 'session_slip_lower95', 'session_slip_upper95')} "
            f"| {c['turn_slips']}/{c['turns']} | {caught} | {repaired} "
            f"| {_rate(c, 'final_violations', 'final_known', 'final_violation_lower95', 'final_violation_upper95')} "
            f"| {accepted} |")


HEAD = ("| {first} | Sessions with a slip | Turn slips | Caught by the gate | Repaired in the turn "
        "| Final snapshot violates the rule | All four steps accepted |\n| --- | --- | --- | --- | --- | --- | --- |")


def render(study: str, records: list[dict], plan: list[dict], s: dict[str, Any]) -> str:
    env = next((r["identity"].get("environment") for r in records if r["identity"].get("environment")), {}) or {}
    lines = [
        "# Version 3 results: written-down rules, unwritten rules and the gate", "",
        f"Study `{study}`, protocol [`protocol-v3.md`](protocol-v3.md). Written by `tools/summarize_v3.py` from "
        f"{len(records)} retained records (`runs/{study}/`); {len(plan)} sessions were planned.", "",
        "Descriptive counts only. Rates are `k/n` with exact one-sided 95% bounds in brackets "
        "(an upper bound for a zero count; lower and upper otherwise). Session-level counts are primary; "
        "turns within a session are not independent.", "",
        "## Headline: guidance level × gate", "",
        "Pooled over both scenarios and both agent configurations.", "",
        HEAD.format(first="Guidance, arm"),
    ]
    for g in GUIDANCE:
        for arm in ("A", "B"):
            lines.append(_row(f"{GUIDANCE_LABEL[g]}, {ARM_LABEL[arm]}", s["by_ga"].get((g, arm)),
                              s["groups"].get((g, arm)), arm == "B"))
    lines += ["", "## By agent configuration", "", HEAD.format(first="Guidance, arm, agent")]
    for g in GUIDANCE:
        for arm in ("A", "B"):
            for m in ("sonnet", "haiku"):
                lines.append(_row(f"{GUIDANCE_LABEL[g]}, {ARM_LABEL[arm]}, {MODEL_LABEL[m]}",
                                  s["by_gam"].get((g, arm, m)), s["groups"].get((g, arm, m)), arm == "B"))
    lines += ["", "## By scenario", "", HEAD.format(first="Guidance, arm, scenario")]
    for g in GUIDANCE:
        for arm in ("A", "B"):
            for sc in sorted({k[2] for k in s["by_gas"]}):
                lines.append(_row(f"{GUIDANCE_LABEL[g]}, {ARM_LABEL[arm]}, {sc}", s["by_gas"].get((g, arm, sc)), None,
                                  arm == "B"))
    lines += ["", "## Time, spend and repair effort", "",
              "Session wall time and CLI-reported agent cost (API-equivalent, notional under a subscription login).", "",
              "| Guidance, arm, agent | Sessions | Median session time | Total agent cost | Repair requests "
              "| Turns ending with a carried-over violation |", "| --- | --- | --- | --- | --- | --- |"]
    for g in GUIDANCE:
        for arm in ("A", "B"):
            for m in ("sonnet", "haiku"):
                grp = s["groups"].get((g, arm, m))
                if not grp:
                    continue
                repairs = [x for x in grp["repair_requests"] if x is not None]
                lines.append(f"| {GUIDANCE_LABEL[g]}, {ARM_LABEL[arm]}, {MODEL_LABEL[m]} | {len(grp['all_accepted'])} "
                             f"| {s2.median(grp['session_s'])} | {s2.money(grp['agent_cost'])} "
                             f"| {sum(repairs) if arm == 'B' else 'n/a'} | {sum(grp['persisting'])} |")
    lines += ["", "## Every slip", ""]
    if s["slips"]:
        lines += ["| Session | Step | New forbidden imports | Caught | Repaired | Repair requests | Final snapshot |",
                  "| --- | --- | --- | --- | --- | --- | --- |"]
        for x in s["slips"]:
            edges = ", ".join(f"`{a.removeprefix('orders.')}` → `{b.removeprefix('orders.')}`" for a, b in (x["new_edges"] or []))
            show = lambda v: "n/a" if v is None else ("yes" if v else "no")  # noqa: E731
            lines.append(f"| `{x['run_id']}` | {x['step']} | {edges} | {show(x['caught'])} | {show(x['repaired'])} "
                         f"| {x['repair_requests'] if x['repair_requests'] is not None else 'n/a'} | {x['final_structural']} |")
    else:
        lines.append("None.")
    integrity = {k: sum(sum(grp[k]) for key, grp in s["groups"].items() if len(key) == 2)
                 for k in ("tampering", "legacy_modified")}
    lines += ["", "## Completeness and integrity", "",
              f"- Terminations: {', '.join(f'{k} {v}' for k, v in sorted(s['terminations'].items()))}.",
              f"- Planned sessions without a record: {len(s['missing'])}"
              + (f" ({', '.join(s['missing'])})" if s["missing"] else "") + ".",
              f"- Sessions with tampering detected: {integrity['tampering']}. "
              f"Sessions that modified the legacy reports controller: {integrity['legacy_modified']}.",
              f"- Reported spend: agent US${s['agent_cost']:.2f}, evaluation judge US${s['judge_cost']:.2f}.",
              f"- Environment: Claude Code {env.get('claude_cli', env.get('claude_version', 'see records'))}."
              if env else "- Environment: see the records.", ""]
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
        payload = {"by_guidance_arm": {"|".join(k): v for k, v in s["by_ga"].items()},
                   "by_guidance_arm_model": {"|".join(k): v for k, v in s["by_gam"].items()},
                   "by_guidance_arm_scenario": {"|".join(k): v for k, v in s["by_gas"].items()},
                   "time_and_spend": {"|".join(k): {"sessions": len(g["all_accepted"]),
                                                     "median_session_s": statistics.median(g["session_s"]) if g["session_s"] else None,
                                                     "agent_cost_usd": str(sum(g["agent_cost"], Decimal(0))),
                                                     "repair_requests": sum(x for x in g["repair_requests"] if x is not None)}
                                      for k, g in s["groups"].items()},
                   "slips": s["slips"], "terminations": dict(s["terminations"]), "missing": s["missing"]}
        args.json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {args.out} from {len(records)} records")
    return 0


if __name__ == "__main__":
    sys.exit(main())
