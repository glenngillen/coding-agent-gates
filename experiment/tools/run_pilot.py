#!/usr/bin/env python3
"""Run the frozen pilot (or a harness check) and collect one record per attempted run.

    .venv/bin/python experiment/tools/run_pilot.py --pilot pilot-2026-11-19 [--workers 3]
    .venv/bin/python experiment/tools/run_pilot.py --harness-check harness-check-2026-11-19

For every entry in ``experiment/runs/<pilot>/order.json`` (written beforehand
by ``prepare_run.py plan``) that has no record yet, in plan order:

1. Reserve the run's worst case in the shared spend ledger. If the ledger
   refuses (the US$100 cap would be passed), record the run as
   ``not_started_cap`` and start no further runs; remaining runs are recorded
   the same way. Nothing is dropped.
2. Prepare the isolated workspace for the run's arm (``prepare_run.prepare``).
3. Run the agent: one fresh ``claude -p`` process (stream-json output), the
   prompt on stdin, wall-clock timeout from ``arms.json``. No human
   intervention. The CLI's ``--max-budget-usd`` caps the run's spend.
4. Charge the ledger the CLI's reported ``total_cost_usd`` (or keep the
   reservation when the cost is unknown).
5. Collect the final diff, the redacted transcript and the hook log, compare
   the external ``--settings`` file with its preparation hash
   (``evaluator/settings_integrity.py``, added after pilot-2026-11-19), then
   evaluate the final snapshot with the independent evaluator (including the
   live judge, charged to the same ledger).
6. Write ``record.json`` (``run_record.build_record``) next to the retained
   artifacts in ``experiment/runs/<pilot>/<run_id>/``.

An attempt that fails for an infrastructure reason (the CLI produced no
result at all, without a timeout) is retried once in a fresh workspace; the
failed attempt's artifacts, reason, agent ledger entry and judge usage
(development and evaluation, with unknown-cost holds) stay in
``infrastructure_retries`` and count towards total spend.

Agent reservation: ``--max-budget-usd`` plus one response at Claude Sonnet
5.5's documented limits (1M context, 128K output; models overview retrieved
2026-11-19) and its highest rates (US$4/MTok 1-hour cache write, US$10/MTok
output; pricing page retrieved 2026-11-19, no long-context premium):
US$5.28. The CLI checks its budget after each response, so one response is
the documented overshoot.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import platform
import secrets
import shutil
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
TOOLS = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "experiment"), str(TOOLS)]

import prepare_run as pr  # noqa: E402
import run_record as rr  # noqa: E402
import spend_ledger  # noqa: E402
from evaluator import evaluate as ev  # noqa: E402
from evaluator import settings_integrity as si  # noqa: E402
from gates.claude_cli_judge import ClaudeCliJudgeProvider  # noqa: E402
from gates.sensor import installed_import_linter_version  # noqa: E402

# Claude Sonnet 5.5: 1M x US$4/MTok + 128K x US$10/MTok (sources.md T20).
AGENT_RESPONSE_USD_MAX = Decimal("4.00") + Decimal("1.28")
HARNESS_TASK = {
    "id": "H00-harness-check",
    "request": ("This is a harness check, not a feature. Add this exact line directly below the "
                "existing imports in src/orders/controllers/orders.py:\n\n"
                "from orders.infrastructure.repository import InMemoryOrderRepository  # harness check\n\n"
                "Then finish. If a check reports a problem after you finish, fix it."),
    "acceptance_test": None,
}
LOCK = threading.Lock()
STOP = threading.Event()


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def environment() -> dict[str, Any]:
    try:
        cli = subprocess.run(["claude", "--version"], capture_output=True, text=True, timeout=30).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        cli = None
    return {"claude_cli": cli, "python": platform.python_version(), "platform": platform.platform(),
            "import_linter": installed_import_linter_version()}


def reservation(arms: dict[str, Any]) -> Decimal:
    return Decimal(arms["agent"]["max_budget_usd"]) + AGENT_RESPONSE_USD_MAX


def run_agent(prepared: dict[str, Any], timeout_s: float) -> dict[str, Any]:
    base = Path(prepared["paths"]["base"])
    out_path, err_path = base / "transcript.raw.jsonl", base / "cli-stderr.txt"
    started_at, start = now(), time.monotonic()
    timed_out = False
    with open(out_path, "w") as out, open(err_path, "w") as err:
        proc = subprocess.Popen(prepared["agent_argv"], cwd=prepared["paths"]["workspace"],
                                stdin=subprocess.PIPE, stdout=out, stderr=err, text=True,
                                start_new_session=True)
        try:
            proc.communicate(prepared["prompt"], timeout=timeout_s)
        except subprocess.TimeoutExpired:
            timed_out = True
            for sig in (signal.SIGTERM, signal.SIGKILL):
                try:
                    os.killpg(proc.pid, sig)
                except ProcessLookupError:
                    break
                try:
                    proc.wait(timeout=15)
                    break
                except subprocess.TimeoutExpired:
                    continue
    attempt_s = round(time.monotonic() - start, 3)
    events, result, bad = rr.parse_stream(out_path.read_text(encoding="utf-8", errors="replace").splitlines())
    return {"result": result, "events": events, "bad_lines": bad, "timed_out": timed_out,
            "exit_code": proc.returncode, "attempt_s": attempt_s, "started_at": started_at,
            "finished_at": now(), "transcript": out_path, "stderr": err_path}


def final_diff(workspace: Path, baseline: str) -> str:
    def git(*args):
        return subprocess.run(["git", *pr.GIT_IDENTITY, *args], cwd=workspace, capture_output=True,
                              text=True, check=True).stdout
    git("add", "-A")
    return git("diff", "--cached", "--binary", baseline)


def redactions(prepared: dict[str, Any]) -> dict[str, str]:
    reps = {str(ROOT): "<example>", str(Path(prepared["paths"]["base"])): "<run>",
            str(Path.home()): "<home>"}
    real = {str(Path(k).resolve()): v for k, v in reps.items()}
    return {**reps, **real}


def retain_text(dest: Path, text: str, reps: dict[str, str]) -> str:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(rr.redact(text, reps), encoding="utf-8")
    return dest.relative_to(ROOT).as_posix()


def retain_jsonl(dest: Path, objs: list[dict], reps: dict[str, str]) -> str:
    text = "".join(json.dumps(rr.compact(rr.sanitize_event(o))) + "\n" for o in objs)
    return retain_text(dest, text, reps)


def attempt_cell(task: dict, entry: dict, arms: dict, pilot: str, attempt: int, ledger_path: Path,
                 evaluate: bool) -> dict[str, Any]:
    """One attempt: ledger, prepare, run, charge, collect artifacts. Returns raw collection data."""
    rid = entry["run_id"]
    retained = pr.RUNS_DIR / pilot / rid / (f"attempt-{attempt}" if attempt > 1 else "")
    guard = spend_ledger.FileSpendGuard(ledger_path, kind="agent")
    entry_id = guard.begin(f"{pilot} {rid} attempt {attempt} ({arms['agent']['model']}, CLI)",
                           reservation(arms))
    ledger = {"agent_entry_id": entry_id, "reserved_usd": str(reservation(arms))}
    try:
        prepared = pr.prepare(task, entry["arm"], entry["repeat"], pilot=pilot, arms=arms, plan_entry=entry,
                              work_dir=pr.WORK_DIR / f"attempt-{attempt}", ledger=ledger_path)
    except pr.NotRunnable as exc:
        guard.fail(entry_id, Decimal(0), note=f"not runnable, nothing started: {exc}")
        return {"not_runnable": str(exc), "ledger": {**ledger, "charged_usd": "0", "status": "failed"}}
    run = run_agent(prepared, float(arms["agent"]["wall_timeout_s"]))
    usage = rr.agent_usage(run["result"])
    cost = Decimal(usage["cost_usd"]) if usage["cost_usd"] is not None else None
    if cost is not None and rr.termination(run["result"], timed_out=run["timed_out"],
                                           exit_code=run["exit_code"]) == "completed":
        guard.finish(entry_id, cost, usage, note=rr.COST_BASIS)
        status = "finished"
    else:
        guard.fail(entry_id, cost, usage, note="run did not complete normally; " + rr.COST_BASIS)
        status = "failed"
    ledger.update({"charged_usd": str(cost) if cost is not None else ledger["reserved_usd"],
                   "cost_known": cost is not None, "status": status})

    reps = redactions(prepared)
    workspace = Path(prepared["paths"]["workspace"])
    diff = final_diff(workspace, prepared["baseline_commit"])
    events_path = Path(prepared["paths"]["hook_events"])
    hook_lines = events_path.read_text(encoding="utf-8").splitlines() if events_path.is_file() else []
    hook_events, bad_hook = rr.parse_events(hook_lines)
    artifacts = {
        "prepared": retain_text(retained / "prepared.json", json.dumps(prepared, indent=2) + "\n", reps),
        "transcript": retain_jsonl(retained / "transcript.jsonl", run["events"], reps),
        "cli_stderr": retain_text(retained / "cli-stderr.txt", run["stderr"].read_text(errors="replace"), reps),
        "hook_events": retain_jsonl(retained / "hook-events.jsonl", hook_events, reps) if hook_events else None,
        "final_diff": retain_text(retained / "final.diff", diff, reps),
    }
    # The frozen evaluator does not look at the external --settings file that
    # installs the Stop hook; compare it with its preparation hash here.
    settings_check = si.check_settings(prepared.get("settings_sha256"), prepared["paths"].get("settings"))
    evaluation = None
    if evaluate and task.get("acceptance_test"):
        provider = ClaudeCliJudgeProvider(guard=spend_ledger.FileSpendGuard(ledger_path, kind="judge"),
                                          label=f"{pilot} {rid} evaluation judge")
        evaluation = ev.evaluate_snapshot(workspace, task, prepared, workdir=Path(prepared["paths"]["base"]) / "evaluation",
                                          gate_paths=pr.gate_paths(), judge_provider=provider)
        artifacts["evaluation"] = retain_text(retained / "evaluation.json",
                                              json.dumps(evaluation, indent=2) + "\n", reps)
    return {"prepared": prepared, "run": run, "hook_events": hook_events, "bad_hook_lines": bad_hook,
            "evaluation": evaluation, "artifacts": artifacts, "ledger": ledger,
            "settings_integrity": rr.redact_json(settings_check, reps)}


def run_cell(task: dict, entry: dict, arms: dict, pilot: str, ledger_path: Path, env: dict,
             evaluate: bool = True) -> dict[str, Any]:
    rid = entry["run_id"]
    record_path = pr.RUNS_DIR / pilot / rid / "record.json"
    retries: list[dict] = []
    blind = secrets.token_hex(6)
    for attempt in (1, 2):
        if STOP.is_set():
            data = {"not_started": "an earlier run was refused by the spend cap; no new runs start"}
        else:
            try:
                data = attempt_cell(task, entry, arms, pilot, attempt, ledger_path, evaluate)
            except spend_ledger.SpendCapExceeded as exc:
                STOP.set()
                data = {"not_started": f"spend ledger refused the run: {exc}"}
        if "not_started" in data or "not_runnable" in data:
            prepared = {"pilot": pilot, "run_id": rid, "task_id": task["id"], "arm": entry["arm"],
                        "repeat": entry["repeat"], "plan": entry, "agent_config": arms["agent"],
                        "settings": {"hooks": {}} if arms["arms"][entry["arm"]]["stop_hook"] else {},
                        "_not_started": "not_started" in data}
            record = rr.build_record(
                evidence_kind="real", prepared=prepared, result=None, timed_out=False, exit_code=None,
                attempt_s=None, events=[], evaluation=None, started_at=None, finished_at=None,
                environment=env, ledger=data.get("ledger"), artifacts={}, infrastructure_retries=retries,
                blind_id=blind, not_runnable=data.get("not_runnable"),
                notes=[data.get("not_started") or data.get("not_runnable")])
            break
        run = data["run"]
        term = rr.termination(run["result"], timed_out=run["timed_out"], exit_code=run["exit_code"])
        infra_failure = term == "cli_error" and run["result"] is None
        if infra_failure and attempt == 1:
            retries.append({"attempt": 1, "reason": "no result event from the CLI (infrastructure failure)",
                            "exit_code": run["exit_code"], "artifacts": data["artifacts"],
                            "ledger": data["ledger"],
                            # The failed attempt was evaluated (and may have run its
                            # development judge) before the retry was decided; keep
                            # that judge usage and its ledger holds in the spend.
                            "usage": rr.attempt_judge_usage(
                                bool((data["prepared"].get("settings") or {}).get("hooks")),
                                data["hook_events"], data["evaluation"])})
            continue
        notes = []
        if run["bad_lines"]:
            notes.append(f"{len(run['bad_lines'])} unparseable transcript line(s)")
        if data["bad_hook_lines"]:
            notes.append(f"{data['bad_hook_lines']} unparseable hook log line(s)")
        record = rr.build_record(
            evidence_kind="real", prepared=data["prepared"], result=run["result"], timed_out=run["timed_out"],
            exit_code=run["exit_code"], attempt_s=run["attempt_s"], events=data["hook_events"],
            evaluation=data["evaluation"], started_at=run["started_at"], finished_at=run["finished_at"],
            environment=env, ledger=data["ledger"],
            artifacts={**data["artifacts"], "record": (record_path.relative_to(ROOT).as_posix())},
            infrastructure_retries=retries, blind_id=blind, notes=notes,
            settings_integrity=data["settings_integrity"])
        break
    record_path.parent.mkdir(parents=True, exist_ok=True)
    record_path.write_text(rr.dumps(record), encoding="utf-8")
    o = record["outcome"]
    with LOCK:
        print(f"{rid:<30} {o['termination']:<16} behavior={o['behavior']} structural={o['structural']} "
              f"judge={o['semantic_judge']} gate={o['gate_final_state']} "
              f"cost={record['usage']['agent'].get('cost_usd')}", flush=True)
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--pilot")
    group.add_argument("--harness-check", metavar="NAME")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--ledger", type=Path, default=spend_ledger.DEFAULT_PATH)
    args = parser.parse_args()
    if shutil.which("claude") is None:
        print("NOT RUN: the claude CLI is not on PATH")
        return 5
    arms = pr.load_arms()
    env = environment()
    if args.harness_check:
        # Not study data: checks that the hook protocol works in -p mode.
        name = args.harness_check
        for arm in ("B", "C"):
            entry = {"sequence": None, "task_id": HARNESS_TASK["id"], "arm": arm, "repeat": 1,
                     "position_in_task": None, "run_id": pr.run_id(HARNESS_TASK["id"], arm, 1)}
            run_cell(HARNESS_TASK, entry, arms, name, args.ledger, env, evaluate=False)
        return 0

    ev.check_frozen(ev.load_manifest(), ev.current_frozen_hashes())
    plan = json.loads((pr.RUNS_DIR / args.pilot / "order.json").read_text())["runs"]
    tasks = {t["id"]: t for t in pr.load_tasks()}
    todo = [e for e in plan if not (pr.RUNS_DIR / args.pilot / e["run_id"] / "record.json").exists()]
    print(f"{len(todo)} of {len(plan)} runs to do; workers={args.workers}", flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(run_cell, tasks[e["task_id"]], e, arms, args.pilot, args.ledger, env)
                   for e in todo]
        for f in futures:
            f.result()
    return 6 if STOP.is_set() else 0


if __name__ == "__main__":
    sys.exit(main())
