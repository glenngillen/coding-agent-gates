#!/usr/bin/env python3
"""Write experiment/results-v2.md from the retained version 2 session records.

    .venv/bin/python experiment/tools/summarize_v2.py --study follow-up-v2-2026-11-20 \
        --out experiment/results-v2.md [--json experiment/runs/<study>/summary.json]

Reads every ``experiment/runs/<study>/<run_id>/record.json``, the plan
(``order.json``) and the shared spend ledger. All counts and bounds come from
``study_v2`` (frozen in ``v2/frozen-manifest.json``), so this file only
presents them: denominators, slip counts with exact one-sided 95% bounds,
catches and repairs, final outcomes, repair effort, time and notional spend.
Nothing is typed in by hand; rerunning it regenerates the same document.
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
sys.path[:0] = [str(ROOT / "src"), str(TOOLS)]

import study_v2  # noqa: E402

ARM_LABELS = {"A": "A: instruction only", "B": "B: + structural gate", "C": "C: + structural + semantic gate"}


def load_records(study_dir: Path) -> list[dict[str, Any]]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(study_dir.glob("*/record.json"))]


def pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x * 100:.0f}%"


def rate(k: int, n: int, lo: float | None, hi: float | None) -> str:
    if n == 0:
        return "0/0 (no known outcomes)"
    if k == 0:
        return f"0/{n} (upper 95% bound {pct(hi)})"
    return f"{k}/{n} (95% bounds {pct(lo)} to {pct(hi)})"


def money(values: list[Decimal]) -> str:
    return f"US${sum(values, Decimal(0)):.2f}"


def median(values: list[float]) -> str:
    return f"{statistics.median(values):.0f} s" if values else "n/a"


def agent_cost(record: dict) -> Decimal | None:
    value = ((record.get("usage") or {}).get("agent") or {}).get("cost_usd")
    return Decimal(value) if value is not None else None


def judge_cost(record: dict) -> Decimal:
    total = Decimal(0)
    for part in ("development", "evaluation"):
        value = (((record.get("usage") or {}).get("judge") or {}).get(part) or {}).get("cost_usd")
        if value is not None:
            total += Decimal(str(value))
    return total


def summarize(records: list[dict], plan: list[dict], ledger: dict) -> dict[str, Any]:
    by_cell = study_v2.summarize_cells(records)
    by_arm_model = study_v2.summarize_cells(
        records, key=lambda r: (r["identity"]["arm"], r["identity"]["model_key"]))
    by_arm = study_v2.summarize_cells(records, key=lambda r: (r["identity"]["arm"],))
    terminations = Counter(r["outcome"]["termination"] for r in records)
    planned = {p["run_id"] for p in plan}
    recorded = {r["identity"]["run_id"] for r in records}
    groups: dict[tuple, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for r in records:
        g = groups[(r["identity"]["arm"], r["identity"]["model_key"])]
        if r["time"].get("session_s") is not None:
            g["session_s"].append(r["time"]["session_s"])
        if (c := agent_cost(r)) is not None:
            g["agent_cost"].append(c)
        g["judge_cost"].append(judge_cost(r))
        g["repair_requests"].append(r["repair"]["requests"] if r["repair"]["applicable"] else None)
        beh = (r["outcome"].get("behavior") or {})
        g["steps_accepted"].append(len(beh.get("steps_accepted") or []))
        g["all_accepted"].append(bool(beh.get("all_steps_accepted")))
        g["tampering"].append(bool(r["outcome"].get("tampering_detected")))
        g["legacy_modified"].append(bool(r["outcome"].get("legacy_reports_modified")))
        g["judge_final"].append(r["outcome"].get("semantic_judge"))
        g["persisting"].append(sum(1 for t in r["turns"] if t.get("persisting_violation")))
    slips = [{"run_id": r["identity"]["run_id"], "step": t["step"], "new_edges": t.get("new_edges"),
              "caught": t.get("caught"), "repaired": t.get("repaired"),
              "repair_requests": t.get("repair_requests"), "end_structural": t.get("end_structural"),
              "final_structural": r["outcome"].get("final_structural")}
             for r in records for t in r["turns"] if t.get("slip")]
    semantic = []
    judged = 0
    for r in records:
        path = (r.get("artifacts") or {}).get("hook_events")
        events = []
        if path and (ROOT / path).is_file():
            events = [json.loads(l) for l in (ROOT / path).read_text(encoding="utf-8").splitlines() if l.strip()]
        turn = 0
        for e in events:
            if e.get("hook_event_name") == "UserPromptSubmit":
                turn += 1
            sem = e.get("semantic") or {}
            judged += bool(sem.get("status"))
            if e.get("hook_event_name") == "Stop" and sem.get("status") == "violation":
                semantic.append({"run_id": r["identity"]["run_id"], "stage": "development", "step": turn,
                                 "paths": sorted({f.get("path") for f in sem.get("findings") or []}),
                                 "blocked": e.get("decision") == "block"})
        if r["outcome"].get("semantic_judge") == "violation":
            ev_path = (r.get("artifacts") or {}).get("evaluation")
            findings = []
            if ev_path and (ROOT / ev_path).is_file():
                findings = (json.loads((ROOT / ev_path).read_text())["semantic_judge"] or {}).get("findings") or []
            semantic.append({"run_id": r["identity"]["run_id"], "stage": "final evaluation", "step": None,
                             "paths": sorted({f.get("path") for f in findings}), "blocked": None})
    legacy_removed = sorted(r["identity"]["run_id"] for r in records
                            if r["outcome"].get("final_structural_raw") == "pass")
    return {"judged": judged, "semantic": semantic, "legacy_removed": legacy_removed, "by_cell": by_cell, "by_arm_model": by_arm_model, "by_arm": by_arm, "terminations": terminations,
            "missing": sorted(planned - recorded), "groups": groups, "slips": slips,
            "ledger": {k: ledger.get(k) for k in ("cap_usd", "committed_usd", "remaining_usd",
                                                   "committed_by_kind_usd")}}


def render(study: str, records: list[dict], plan: list[dict], s: dict[str, Any]) -> str:
    env = next((r["identity"].get("environment") for r in records if r["identity"].get("environment")), {}) or {}
    started = sorted(r["identity"]["started_at"] for r in records if r["identity"].get("started_at"))
    finished = sorted(r["identity"]["finished_at"] for r in records if r["identity"].get("finished_at"))
    L: list[str] = []
    add = L.append
    add("# Follow-up study (version 2): results")
    add("")
    add(f"Generated by `experiment/tools/summarize_v2.py --study {study}` from the {len(records)} retained "
        f"records in `experiment/runs/{study}/`. Every number below is computed from those records "
        "with the frozen statistics in `experiment/tools/study_v2.py`; the protocol is "
        "[`protocol-v2.md`](protocol-v2.md). Descriptive only: no significance tests.")
    add("")
    add("## What ran")
    add("")
    add(f"- Planned sessions: {len(plan)} (2 scenarios × 3 arms × 2 agent configurations × 3 repeats, "
        "4 dependent steps each). Records: "
        f"{len(records)}. Missing records: {', '.join(s['missing']) if s['missing'] else 'none'}.")
    add(f"- Terminations: " + ", ".join(f"{k} {v}" for k, v in sorted(s["terminations"].items())) + ".")
    if started:
        add(f"- First session started {started[0]}; last finished {finished[-1] if finished else 'n/a'} (UTC).")
    add(f"- Environment: Claude Code CLI {env.get('claude_cli')}, Python {env.get('python')}, "
        f"Import Linter {env.get('import_linter')}, {env.get('platform')}.")
    all_agent = [c for r in records if (c := agent_cost(r)) is not None]
    add(f"- Total reported spend: {money(all_agent)} agent, {money([judge_cost(r) for r in records])} judge.")
    add("- After the freeze, while the sessions ran, a one-call probe from a workspace inside the worktree "
        "asked the agent to list its instruction files; it named only the workspace `CLAUDE.md` "
        "(`runs/probe-v2-2026-11-20/parent-memory-check.json`; a model self-report).")
    add("- Known issue: the building environment sets `GIT_AUTHOR_*`/`GIT_COMMITTER_*`, which override the "
        "fictional identity `prepare_v2.py` passes with `git -c`, so the workspace history carried a real "
        "author name and email. One retained transcript (a harness check) showed it after `git log`; it was "
        "redacted to `<redacted author>`. The frozen preparation script was not changed after the run.")
    add("- Agents: `claude-sonnet-5-5` at medium effort and `claude-haiku-5-5` at the CLI default effort. "
        "The architecture rule was only in the workspace `CLAUDE.md`. A legacy controller already broke it.")
    add("")
    add("## Slips: how often the first candidate added a forbidden import")
    add("")
    add("A *turn slip* is a first candidate completion that adds a controller-to-infrastructure import edge "
        "not present at the start of the turn. A *session slip* is at least one turn slip in the session. "
        "Bounds are exact one-sided 95% bounds. Turn-level bounds treat the turns of one session as "
        "independent, which they are not; sessions are the primary unit.")
    add("")
    add("| Arm | Agent | Sessions with a slip | Turns with a slip | Slips caught | Caught slips repaired | Final structural violations |")
    add("| --- | --- | --- | --- | --- | --- | --- |")
    for (arm, model), c in sorted(s["by_arm_model"].items()):
        caught = f"{c['caught']}/{c['turn_slips']}" if arm != "A" else "no gate"
        repaired = f"{c['repaired']}/{c['caught']}" if arm != "A" else "no gate"
        add(f"| {ARM_LABELS[arm]} | {model} | "
            f"{rate(c['sessions_with_slip'], c['sessions'], c['session_slip_lower95'], c['session_slip_upper95'])} | "
            f"{rate(c['turn_slips'], c['turns'], c['turn_slip_lower95'], c['turn_slip_upper95'])} | {caught} | "
            f"{repaired} | "
            f"{rate(c['final_violations'], c['final_known'], c['final_violation_lower95'], c['final_violation_upper95'])} |")
    add("")
    add("Pooled across both agent configurations and scenarios:")
    add("")
    add("| Arm | Sessions with a slip | Turns with a slip | Final structural violations |")
    add("| --- | --- | --- | --- |")
    for (arm,), c in sorted(s["by_arm"].items()):
        add(f"| {ARM_LABELS[arm]} | "
            f"{rate(c['sessions_with_slip'], c['sessions'], c['session_slip_lower95'], c['session_slip_upper95'])} | "
            f"{rate(c['turn_slips'], c['turns'], c['turn_slip_lower95'], c['turn_slip_upper95'])} | "
            f"{rate(c['final_violations'], c['final_known'], c['final_violation_lower95'], c['final_violation_upper95'])} |")
    add("")
    unknown = {k: (c["sessions_unknown"], c["turns_unknown"], c["not_started"], c["judge_unavailable"])
               for k, c in s["by_arm_model"].items()}
    if any(any(v) for v in unknown.values()):
        add("Sessions or turns without a known slip outcome (excluded from the denominators above):")
        add("")
        for (arm, model), (su, tu, ns, ju) in sorted(unknown.items()):
            if su or tu or ns or ju:
                add(f"- {arm}/{model}: {su} session(s) unknown, {tu} turn(s) unknown or censored, "
                    f"{ns} not started, {ju} judge unavailable.")
        add("")
    add("### Per cell")
    add("")
    add("Each cell is one scenario, arm and agent configuration. Bounds are exact one-sided 95% bounds for "
        "that cell alone; with three sessions per cell they are wide. As above, turn-level bounds treat the "
        "dependent turns of one session as independent, which they are not; sessions are the primary unit.")
    add("")
    add("| Scenario | Arm | Agent | Sessions with a slip | Turns with a slip | Final structural violations |")
    add("| --- | --- | --- | --- | --- | --- |")
    for (scen, arm, model), c in sorted(s["by_cell"].items()):
        add(f"| {scen} | {arm} | {model} | "
            f"{rate(c['sessions_with_slip'], c['sessions'], c['session_slip_lower95'], c['session_slip_upper95'])} | "
            f"{rate(c['turn_slips'], c['turns'], c['turn_slip_lower95'], c['turn_slip_upper95'])} | "
            f"{rate(c['final_violations'], c['final_known'], c['final_violation_lower95'], c['final_violation_upper95'])} |")
    add("")
    add("### Every slip")
    add("")
    if not s["slips"]:
        add("No turn slipped in any session.")
    else:
        add("| Session | Step | New edges | Caught | Repaired | Repair requests | Turn-end structural | Final structural |")
        add("| --- | --- | --- | --- | --- | --- | --- | --- |")
        for x in s["slips"]:
            edges = "; ".join(f"`{a} -> {b}`" for a, b in (x["new_edges"] or []))
            add(f"| {x['run_id']} | {x['step']} | {edges} | {x['caught']} | {x['repaired']} | "
                f"{x['repair_requests']} | {x['end_structural']} | {x['final_structural']} |")
    add("")
    add("## Semantic findings and the legacy controller")
    add("")
    if not s["semantic"]:
        add("The judge returned no `violation` at any stage.")
    else:
        dev = sum(1 for x in s["semantic"] if x["stage"] == "development")
        add(f"Arm C's gate judged {s['judged']} structurally passing candidates and returned `violation` "
            f"for {dev}. Every judge `violation`, during development and on final snapshots (all arms), "
            "is listed below. These are judge outputs, not labels.")
        add("")
        add("| Session | Stage | Step | Files cited | Gate blocked |")
        add("| --- | --- | --- | --- | --- |")
        for x in s["semantic"]:
            add(f"| {x['run_id']} | {x['stage']} | {x['step'] or ''} | "
                + ", ".join(f"`{p}`" for p in x["paths"]) + f" | {'' if x['blocked'] is None else x['blocked']} |")
    add("")
    add(f"Sessions whose final snapshot no longer contained the legacy `reports.py` repository import "
        f"(raw structural status `pass`): {len(s['legacy_removed'])} of {len(records)}"
        + (f" ({', '.join(s['legacy_removed'])})." if s["legacy_removed"] else "."))
    add("")
    add("## Behaviour, effort, time and spend")
    add("")
    add("| Arm | Agent | Sessions | All 4 steps accepted | Steps accepted (of 4, median) | Repair requests (total) | Median session time | Agent spend | Judge spend | Tampering flagged | `reports.py` modified | Final judge outputs |")
    add("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for (arm, model), g in sorted(s["groups"].items()):
        n = len(g["all_accepted"])
        reqs = [x for x in g["repair_requests"] if x is not None]
        judges = Counter(x or "none" for x in g["judge_final"])
        add(f"| {arm} | {model} | {n} | {sum(g['all_accepted'])}/{n} | "
            f"{statistics.median(g['steps_accepted']) if g['steps_accepted'] else 'n/a'} | "
            f"{sum(reqs) if reqs else 'no gate'} | {median(g['session_s'])} | {money(g['agent_cost'])} | "
            f"{money(g['judge_cost'])} | {sum(g['tampering'])}/{n} | {sum(g['legacy_modified'])}/{n} | "
            + ", ".join(f"{k} {v}" for k, v in sorted(judges.items())) + " |")
    add("")
    add("Spend is the Claude Code CLI's reported `total_cost_usd` (API-equivalent list price), notional "
        "under a subscription login and not an invoice. Judge outputs are not labels: no human labels exist.")
    led = s["ledger"]
    add("")
    add(f"Shared ledger after these sessions: US${Decimal(led['committed_usd']):.2f} committed of the "
        f"US${led['cap_usd']} cap (US${Decimal(led['remaining_usd']):.2f} remaining), including the pilot.")
    add("")
    add("## Reading these results")
    add("")
    total_slips = sum(c["turn_slips"] for c in s["by_arm"].values())
    if total_slips == 0:
        add("No first candidate added a forbidden import in any session: a ceiling effect, as in the pilot. "
            "The upper bounds above are the most these sessions can say about the slip rate under these "
            "conditions. They do not show that guidance is safe in longer sessions or larger codebases.")
    else:
        add("Slips occurred. The counts and bounds above describe these two scenarios, these two agent "
            "configurations and these sample sizes only; with three repeats per cell, differences between "
            "arms or agents are not established by these counts.")
    add("")
    add("## Open questions")
    add("")
    add("- Would longer sessions or a larger codebase change the slip rate?")
    add("  - evidence: These sessions had four steps in a 23-module codebase. Neither length nor size was varied, so no trend can be read from them.")
    add("  - options: Treat these counts as covering only these conditions; run a later study with longer sessions or larger codebases under a new frozen protocol and budget.")
    add("  - location: results-v2.md / Reading these results")
    add("")
    return "\n".join(L)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--study", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args()
    study_dir = ROOT / "experiment" / "runs" / args.study
    records = load_records(study_dir)
    plan = json.loads((study_dir / "order.json").read_text())["runs"]
    ledger = json.loads((ROOT / "experiment" / "runs" / "spend-ledger.json").read_text())
    s = summarize(records, plan, ledger)
    args.out.write_text(render(args.study, records, plan, s), encoding="utf-8")
    if args.json:
        payload = {"by_cell": {"|".join(k): v for k, v in s["by_cell"].items()},
                   "by_arm_model": {"|".join(k): v for k, v in s["by_arm_model"].items()},
                   "by_arm": {"|".join(k): v for k, v in s["by_arm"].items()},
                   "terminations": dict(s["terminations"]), "missing": s["missing"], "slips": s["slips"],
                   "ledger": s["ledger"]}
        args.json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {args.out} from {len(records)} records")
    return 0


if __name__ == "__main__":
    sys.exit(main())
