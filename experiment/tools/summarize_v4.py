#!/usr/bin/env python3
"""Write experiment/results-v4.md from the retained version 4 records.

    .venv/bin/python experiment/tools/summarize_v4.py --study NAME --out FILE [--json FILE]

Version 3's tables with version 4's guidance levels, preceded by the primary
outcome fixed in ``protocol-v4.md``: cost and time per session, and the
evaluation judge's verdicts on the final controllers. Not frozen.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOLS = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "experiment"), str(TOOLS)]

import summarize_v2 as s2  # noqa: E402
import summarize_v3 as s3  # noqa: E402

GUIDANCE = ("one-line", "handbook")
LABEL = {"one-line": "Lean prompt", "handbook": "Large handbook"}


def cost_table(records: list[dict]) -> tuple[list[str], dict]:
    groups: dict[tuple, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for r in records:
        i = r["identity"]
        for key in ((i["guidance"], i["arm"], i["model_key"]), (i["guidance"], i["arm"], "all")):
            g = groups[key]
            if (c := s2.agent_cost(r)) is not None:
                g["cost"].append(c)
            if r["time"].get("session_s") is not None:
                g["time"].append(r["time"]["session_s"])
            g["judge"].append(r["outcome"].get("semantic_judge"))
    lines = ["| Guidance, arm, agent | Sessions | Mean agent cost per session | Total agent cost | Median session time "
             "| Judge: violation / pass / not evaluated |", "| --- | --- | --- | --- | --- | --- |"]
    payload = {}
    for g in GUIDANCE:
        for arm in ("A", "B"):
            for m in ("sonnet", "haiku"):
                grp = groups.get((g, arm, m))
                if not grp:
                    continue
                n = len(grp["judge"])
                mean = sum(grp["cost"], Decimal(0)) / len(grp["cost"]) if grp["cost"] else None
                verdicts = Counter(grp["judge"])
                lines.append(f"| {LABEL[g]}, {s3.ARM_LABEL[arm]}, {s3.MODEL_LABEL[m]} | {n} "
                             f"| {'n/a' if mean is None else f'US${mean:.3f}'} | {s2.money(grp['cost'])} "
                             f"| {s2.median(grp['time'])} "
                             f"| {verdicts['violation']} / {verdicts['pass']} / {verdicts['not_evaluated']} |")
                payload["|".join((g, arm, m))] = {
                    "sessions": n, "mean_cost_usd": None if mean is None else str(mean),
                    "total_cost_usd": str(sum(grp["cost"], Decimal(0))),
                    "median_session_s": statistics.median(grp["time"]) if grp["time"] else None,
                    "judge": dict(verdicts)}
    return lines, payload


def render(study: str, records: list[dict], plan: list[dict]) -> tuple[str, dict]:
    s3.GUIDANCE, s3.GUIDANCE_LABEL = GUIDANCE, LABEL
    s = s3.summarize(records, plan)
    body = s3.render(study, records, plan, s).splitlines()
    head_end = body.index("## Headline: guidance level × gate")
    table, payload = cost_table(records)
    top = ["# Version 4 results: a lean prompt with a gate, or a large handbook?", "",
           f"Study `{study}`, protocol [`protocol-v4.md`](protocol-v4.md). Written by `tools/summarize_v4.py` from "
           f"{len(records)} retained records (`runs/{study}/`); {len(plan)} sessions were planned.", "",
           "Descriptive counts only. Costs are CLI-reported, API-equivalent and notional under a subscription login. "
           "Rates are `k/n` with exact one-sided 95% bounds. Judge verdicts are model outputs, not human labels.", "",
           "## Primary outcome: cost, time and the judge's verdict on the final controllers", "", *table, ""]
    return "\n".join(top + body[head_end:]) + "\n", {"cost": payload, "summary": s}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--study", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args()
    study_dir = ROOT / "experiment" / "runs" / args.study
    records = s2.load_records(study_dir)
    plan = json.loads((study_dir / "order.json").read_text())["runs"]
    text, data = render(args.study, records, plan)
    args.out.write_text(text, encoding="utf-8")
    if args.json:
        s = data["summary"]
        args.json.write_text(json.dumps({"cost": data["cost"],
                                         "by_guidance_arm": {"|".join(k): v for k, v in s["by_ga"].items()},
                                         "slips": s["slips"], "terminations": dict(s["terminations"]),
                                         "missing": s["missing"]}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {args.out} from {len(records)} records")
    return 0


if __name__ == "__main__":
    sys.exit(main())
