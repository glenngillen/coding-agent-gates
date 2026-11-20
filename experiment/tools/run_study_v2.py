#!/usr/bin/env python3
"""Run the frozen version 2 study and collect one record per planned session.

    .venv/bin/python experiment/tools/run_study_v2.py --study follow-up-v2-2026-11-20 [--workers 3]

For every entry of ``experiment/runs/<study>/order.json`` (written beforehand
by ``prepare_v2.py plan``) without a record, in plan order:

1. Reserve the session's worst case in the shared spend ledger: the model's
   ``max_budget_usd`` plus one response at its documented limits. If the
   ledger refuses (the US$100 cap would be passed), the session is recorded
   as ``not_started_cap`` and no further sessions start. Nothing is dropped.
2. Prepare the workspace (``prepare_v2.prepare``).
3. Run one ``claude -p --input-format stream-json`` process and send the
   scenario's steps as successive user messages, each only after the previous
   turn's ``result`` event. At each turn end, copy ``src/`` and ``tests/`` to a
   turn snapshot. If a turn ends with an error (for example the budget), no
   further steps are sent; the unsent steps are censored. The wall-clock
   timeout covers the whole session.
4. Charge the ledger the last ``result`` event's ``total_cost_usd`` (the CLI
   reports it cumulatively for the process; probe-v2-2026-11-20), or keep the
   reservation when no cost was reported.
5. Check the external ``--settings`` file against its preparation hash
   (``evaluator/settings_integrity.py``), evaluate each turn snapshot's
   structure and the final snapshot fully (``evaluator/evaluate_v2.py``,
   including the live judge, charged to the same ledger), derive per-turn
   outcomes (``study_v2.turn_outcomes``) and write ``record.json`` beside the
   retained artifacts in ``experiment/runs/<study>/<run_id>/``.

A session with no ``result`` event at all and no timeout (an infrastructure
failure) is retried once in a fresh workspace. The failed attempt's artifacts
and ledger entry stay in ``infrastructure_retries`` and count towards spend.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import queue
import secrets
import shutil
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
TOOLS = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "experiment"), str(TOOLS)]

import prepare_v2 as pv  # noqa: E402
import run_pilot  # noqa: E402
import run_record as rr  # noqa: E402
import spend_ledger  # noqa: E402
import study_v2  # noqa: E402
from evaluator import evaluate as ev  # noqa: E402
from evaluator import evaluate_v2 as ev2  # noqa: E402
from evaluator import settings_integrity as si  # noqa: E402

SCHEMA = "coding-agent-gates/run-record-v2/v1"
# Not study data: checks the multi-turn hook protocol and turn snapshots before the freeze.
HARNESS_SCENARIO = {
    "id": "H00-harness-check-v2",
    "steps": [
        {"id": "h-step1", "acceptance_test": None,
         "request": ("This is a harness check, not a feature. Create the file "
                     "src/orders/controllers/harness_check.py containing exactly this line:\n\n"
                     "from orders.infrastructure.repository import InMemoryOrderRepository  # harness check\n\n"
                     "Then finish. If a check reports a problem after you finish, fix it.")},
        {"id": "h-step2", "acceptance_test": None,
         "request": "This is the second harness-check turn. Reply with only the word DONE."},
    ],
}
LOCK = threading.Lock()
STOP = threading.Event()


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def reservation(study: dict[str, Any], model_key: str) -> Decimal:
    m = study["models"][model_key]
    return Decimal(m["max_budget_usd"]) + Decimal(m["response_reserve_usd"])


def user_line(text: str) -> str:
    return json.dumps({"type": "user", "message": {"role": "user", "content": text}}) + "\n"


def drive_session(send: Callable[[str], None], next_event: Callable[[float], dict | None],
                  messages: Sequence[str], *, deadline: float, clock: Callable[[], float],
                  on_turn_end: Callable[[int, dict], None]) -> tuple[list[dict], bool, bool]:
    """Send one message per turn, waiting for each turn's ``result`` event.

    ``next_event(timeout)`` returns the next parsed event, ``None`` on timeout,
    or ``{"type": "_eof"}`` when the process closed its output. Returns
    (result events, timed out, output ended early).
    """
    results: list[dict] = []
    for index, message in enumerate(messages):
        send(user_line(message))
        while True:
            remaining = deadline - clock()
            if remaining <= 0:
                return results, True, False
            event = next_event(remaining)
            if event is None:
                return results, True, False
            if event.get("type") == "_eof":
                return results, False, True
            if event.get("type") == "result":
                results.append(event)
                on_turn_end(index, event)
                break
        if results[-1].get("subtype") != "success" or results[-1].get("is_error"):
            break  # an errored turn (for example the budget) ends the session
    return results, False, False


def session_termination(results: list[dict], n_steps: int, *, timed_out: bool, exit_code: int | None) -> str:
    if timed_out:
        return "wall_timeout"
    if not results:
        return "cli_error"
    if any(r.get("subtype") == "error_max_budget_usd" for r in results):
        return "budget_exhausted"
    if len(results) == n_steps and all(r.get("subtype") == "success" and r.get("is_error") is False
                                       for r in results) and exit_code == 0:
        return "completed"
    return "cli_error"


def turn_costs(results: list[dict]) -> list[str | None]:
    """Per-turn cost from the cumulative ``total_cost_usd`` values."""
    out, previous = [], Decimal(0)
    for r in results:
        value = r.get("total_cost_usd")
        if value is None:
            out.append(None)
            continue
        current = Decimal(str(value))
        out.append(str(current - previous))
        previous = current
    return out


def build_record(*, prepared: dict[str, Any], study: dict[str, Any], scenario: dict[str, Any],
                 results: list[dict], timed_out: bool, exit_code: int | None, session_s: float | None,
                 turn_statuses: list[str | None], hook_events: list[dict], evaluation: dict | None,
                 turn_edges: list[list[tuple[str, str]] | None] | None = None,
                 settings_check: dict | None, environment: dict, ledger: dict | None, artifacts: dict,
                 retries: list, blind_id: str, started_at: str | None, finished_at: str | None,
                 history: list[str] | None, notes: list[str], models_reported: list[str],
                 not_started: str | None = None) -> dict[str, Any]:
    n = len(scenario["steps"])
    hook = study["arms"][prepared["arm"]]["stop_hook"]
    gated = hook is not None
    semantic_arm = bool(hook and hook.get("semantic"))
    turns = study_v2.turn_outcomes(gated=gated, n_steps=n, turn_results=results,
                                   end_statuses=turn_statuses, events=hook_events,
                                   end_edges=turn_edges if turn_edges is not None else [None] * len(turn_statuses))
    for turn, cost in zip(turns, turn_costs(results) + [None] * (n - len(results))):
        index = turn["step"] - 1
        turn["duration_s"] = round(results[index]["duration_ms"] / 1000, 3) if (
            index < len(results) and isinstance(results[index].get("duration_ms"), (int, float))) else None
        turn["cost_usd"] = cost
    final_struct = (evaluation or {}).get("structural") or {}
    tampering = (evaluation or {}).get("tampering") or {}
    settings_detected = (settings_check or {}).get("detected")
    termination = "not_started_cap" if not_started else session_termination(
        results, n, timed_out=timed_out, exit_code=exit_code)
    dev_calls = [c for e in hook_events for c in ((e.get("semantic") or {}).get("calls") or [])]
    eval_calls = (evaluation or {}).get("semantic_judge_calls") or []
    m = study["models"][prepared["model_key"]]
    return {
        "schema": SCHEMA,
        "evidence_kind": "real",
        "identity": {
            "study": prepared["study"], "run_id": prepared["run_id"], "scenario_id": prepared["scenario_id"],
            "arm": prepared["arm"], "model_key": prepared["model_key"], "agent_model_requested": m["model"],
            "agent_models_reported": models_reported, "agent_effort": m.get("effort"),
            "repeat": prepared["repeat"], "sequence": (prepared.get("plan") or {}).get("sequence"),
            "blind_id": blind_id, "baseline_commit": prepared.get("baseline_commit"),
            "workspace_history": history, "baseline_tree_sha256": prepared.get("workspace_tree_sha256"),
            "messages_sha256": prepared.get("messages_sha256"), "scenario_sha256": prepared.get("scenario_sha256"),
            "instruction_sha256": prepared.get("instruction_sha256"), "study_sha256": prepared.get("study_sha256"),
            "settings_sha256": prepared.get("settings_sha256"),
            "frozen_manifest_sha256": (evaluation or {}).get("frozen_manifest_sha256"),
            "seed": "unsupported by the Claude Code CLI; not set", "session": study["agent"]["session"],
            "started_at": started_at, "finished_at": finished_at, "environment": environment,
        },
        "outcome": {
            "termination": termination,
            "steps_reached": sum(1 for t in turns if t["reached"]),
            "final_structural": final_struct.get("status"),
            "final_structural_raw": final_struct.get("raw_status"),
            "final_violations": final_struct.get("violations"),
            "behavior": None if evaluation is None else {
                "steps_accepted": evaluation["behavior"]["steps_accepted"],
                "all_steps_accepted": evaluation["behavior"]["all_steps_accepted"],
                "regression": evaluation["behavior"]["regression"]["status"]},
            "semantic_judge": ((evaluation or {}).get("semantic_judge") or {}).get("status"),
            "judge_unavailable": semantic_arm and rr.judge_unavailable(hook_events),
            "semantic_label": None,
            "semantic_label_note": ev.NO_LABEL_NOTE,
            "tampering_detected": None if evaluation is None and settings_check is None else bool(
                tampering.get("detected") or settings_detected),
            "settings_file_check": (settings_check or {}).get("status"),
            "legacy_reports_modified": tampering.get("legacy_reports_modified"),
            "baseline_tests_modified": tampering.get("baseline_tests_modified"),
            "submission": ev.SUBMISSION_NOTE,
        },
        "turns": turns,
        "repair": {"applicable": gated,
                   "requests": sum(t["repair_requests"] or 0 for t in turns) if gated else None,
                   "max_repairs_per_turn": study["max_repairs"]},
        "usage": {"agent": rr.agent_usage(results[-1] if results else None),
                  "judge": {"development": rr.judge_usage(dev_calls), "evaluation": rr.judge_usage(eval_calls)}},
        "time": {"session_s": session_s, "check_seconds": rr.check_seconds(hook_events)},
        "ledger": ledger, "settings_integrity": settings_check, "artifacts": artifacts,
        "infrastructure_retries": retries, "notes": [n for n in notes if n],
    }


# --- I/O -----------------------------------------------------------------------------

def snapshot_turn(workspace: Path, dest: Path) -> None:
    for part in ("src", "tests"):
        if (workspace / part).is_dir():
            shutil.copytree(workspace / part, dest / part, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))


def run_process(prepared: dict[str, Any], timeout_s: float) -> dict[str, Any]:
    base = Path(prepared["paths"]["base"])
    workspace = Path(prepared["paths"]["workspace"])
    turns_dir = Path(prepared["paths"]["turns"])
    out_path, err_path = base / "transcript.raw.jsonl", base / "cli-stderr.txt"
    events_q: queue.Queue = queue.Queue()
    started_at, start = now(), time.monotonic()
    with open(err_path, "w") as err:
        proc = subprocess.Popen(prepared["agent_argv"], cwd=workspace, stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=err, text=True, start_new_session=True)
        assert proc.stdin is not None and proc.stdout is not None

        def reader():
            with open(out_path, "w") as raw:
                for line in proc.stdout:
                    raw.write(line)
                    raw.flush()
                    try:
                        obj = json.loads(line)
                    except (json.JSONDecodeError, ValueError):
                        continue
                    if isinstance(obj, dict):
                        events_q.put(obj)
            events_q.put({"type": "_eof"})

        thread = threading.Thread(target=reader, daemon=True)
        thread.start()

        def next_event(timeout: float):
            try:
                return events_q.get(timeout=timeout)
            except queue.Empty:
                return None

        def send(line: str):
            try:
                proc.stdin.write(line)
                proc.stdin.flush()
            except (BrokenPipeError, OSError):
                pass

        results, timed_out, _ = drive_session(
            send, next_event, prepared["messages"], deadline=start + timeout_s, clock=time.monotonic,
            on_turn_end=lambda i, _e: snapshot_turn(workspace, turns_dir / f"turn-{i + 1}"))
        try:
            proc.stdin.close()
        except OSError:
            pass
        if not timed_out:
            try:
                proc.wait(timeout=max(5.0, start + timeout_s - time.monotonic()))
            except subprocess.TimeoutExpired:
                timed_out = True
        if proc.poll() is None:
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
        thread.join(timeout=15)
    events, _, bad = rr.parse_stream(out_path.read_text(encoding="utf-8", errors="replace").splitlines())
    return {"results": results, "events": events, "bad_lines": bad, "timed_out": timed_out,
            "exit_code": proc.returncode, "session_s": round(time.monotonic() - start, 3),
            "started_at": started_at, "finished_at": now(), "stderr": err_path}


def models_reported(events: list[dict]) -> list[str]:
    found = set()
    for e in events:
        if e.get("type") == "system" and e.get("subtype") == "init" and e.get("model"):
            found.add(e["model"])
        if e.get("type") == "result" and isinstance(e.get("modelUsage"), dict):
            found.update(e["modelUsage"])
    return sorted(found)


def attempt(scenario: dict, entry: dict, study: dict, study_name: str, attempt_no: int, ledger_path: Path,
            env: dict, evaluate: bool = True) -> dict[str, Any]:
    rid, model_key = entry["run_id"], entry["model_key"]
    retained = pv.RUNS_DIR / study_name / rid / (f"attempt-{attempt_no}" if attempt_no > 1 else "")
    guard = spend_ledger.FileSpendGuard(ledger_path, kind="agent")
    reserve = reservation(study, model_key)
    entry_id = guard.begin(f"{study_name} {rid} attempt {attempt_no} ({study['models'][model_key]['model']}, CLI)",
                           reserve)
    ledger = {"agent_entry_id": entry_id, "reserved_usd": str(reserve)}
    try:
        prepared = pv.prepare(scenario, entry, study=study, study_name=study_name,
                              work_dir=pv.WORK_DIR / f"attempt-{attempt_no}", ledger=ledger_path)
    except pv.NotRunnable as exc:
        guard.fail(entry_id, Decimal(0), note=f"not runnable, nothing started: {exc}")
        return {"not_runnable": str(exc), "ledger": {**ledger, "charged_usd": "0", "status": "failed"}}
    history = pv.git_log(Path(prepared["paths"]["workspace"]))
    run = run_process(prepared, float(study["agent"]["wall_timeout_s"]))
    last = run["results"][-1] if run["results"] else None
    usage = rr.agent_usage(last)
    cost = Decimal(usage["cost_usd"]) if usage["cost_usd"] is not None else None
    term = session_termination(run["results"], len(scenario["steps"]), timed_out=run["timed_out"],
                               exit_code=run["exit_code"])
    if cost is not None and term == "completed":
        guard.finish(entry_id, cost, usage, note=rr.COST_BASIS)
        status = "finished"
    else:
        guard.fail(entry_id, cost, usage, note=f"session ended {term}; " + rr.COST_BASIS)
        status = "failed"
    ledger.update({"charged_usd": str(cost) if cost is not None else ledger["reserved_usd"],
                   "cost_known": cost is not None, "status": status})

    reps = run_pilot.redactions(prepared)
    workspace = Path(prepared["paths"]["workspace"])
    diff = run_pilot.final_diff(workspace, prepared["baseline_commit"])
    events_path = Path(prepared["paths"]["hook_events"])
    hook_lines = events_path.read_text(encoding="utf-8").splitlines() if events_path.is_file() else []
    hook_events, bad_hook = rr.parse_events(hook_lines)
    turn_statuses, turn_structural, turn_edges = [], [], []
    for i in range(len(run["results"])):
        snap = Path(prepared["paths"]["turns"]) / f"turn-{i + 1}"
        struct = ev2.structural(snap)
        turn_statuses.append(struct["status"])
        turn_edges.append([(v["importer"], v["imported"]) for v in struct["violations"]]
                          if struct["status"] in ("pass", "violation") else None)
        turn_structural.append({"turn": i + 1, "status": struct["status"], "raw_status": struct["raw_status"],
                                "violations": struct["violations"], "error": struct["error"],
                                "fingerprint": struct["fingerprint"]})
    artifacts = {
        "prepared": run_pilot.retain_text(retained / "prepared.json", json.dumps(prepared, indent=2) + "\n", reps),
        "transcript": run_pilot.retain_jsonl(retained / "transcript.jsonl", run["events"], reps),
        "cli_stderr": run_pilot.retain_text(retained / "cli-stderr.txt",
                                            run["stderr"].read_text(errors="replace"), reps),
        "hook_events": run_pilot.retain_jsonl(retained / "hook-events.jsonl", hook_events, reps) if hook_events else None,
        "final_diff": run_pilot.retain_text(retained / "final.diff", diff, reps),
        "turn_structural": run_pilot.retain_text(retained / "turn-structural.json",
                                                 json.dumps(turn_structural, indent=2) + "\n", reps),
    }
    settings_check = si.check_settings(prepared.get("settings_sha256"), prepared["paths"].get("settings"))
    evaluation = None
    if evaluate:
        from gates.claude_cli_judge import ClaudeCliJudgeProvider
        provider = ClaudeCliJudgeProvider(guard=spend_ledger.FileSpendGuard(ledger_path, kind="judge"),
                                          label=f"{study_name} {rid} evaluation judge")
        evaluation = ev2.evaluate_session(workspace, scenario, prepared,
                                          workdir=Path(prepared["paths"]["base"]) / "evaluation",
                                          gate_paths=pv.gate_paths(), judge_provider=provider)
        artifacts["evaluation"] = run_pilot.retain_text(retained / "evaluation.json",
                                                        json.dumps(evaluation, indent=2) + "\n", reps)
    notes = []
    if run["bad_lines"]:
        notes.append(f"{len(run['bad_lines'])} unparseable transcript line(s)")
    if bad_hook:
        notes.append(f"{bad_hook} unparseable hook log line(s)")
    return {"prepared": prepared, "run": run, "hook_events": hook_events, "evaluation": evaluation,
            "artifacts": artifacts, "ledger": ledger, "settings_check": rr.redact_json(settings_check, reps),
            "turn_statuses": turn_statuses, "turn_edges": turn_edges, "history": history, "notes": notes,
            "models_reported": models_reported(run["events"])}


def run_session(scenario: dict, entry: dict, study: dict, study_name: str, ledger_path: Path,
                env: dict, evaluate: bool = True) -> dict[str, Any]:
    rid = entry["run_id"]
    record_path = pv.RUNS_DIR / study_name / rid / "record.json"
    retries: list[dict] = []
    blind = secrets.token_hex(6)
    placeholder = {"study": study_name, "run_id": rid, "scenario_id": scenario["id"], "arm": entry["arm"],
                   "model_key": entry["model_key"], "repeat": entry["repeat"], "plan": entry}
    for attempt_no in (1, 2):
        if STOP.is_set():
            data = {"not_started": "an earlier session was refused by the spend cap; no new sessions start"}
        else:
            try:
                data = attempt(scenario, entry, study, study_name, attempt_no, ledger_path, env, evaluate)
            except spend_ledger.SpendCapExceeded as exc:
                STOP.set()
                data = {"not_started": f"spend ledger refused the session: {exc}"}
        if "not_started" in data or "not_runnable" in data:
            record = build_record(
                prepared=placeholder, study=study, scenario=scenario, results=[], timed_out=False, exit_code=None,
                session_s=None, turn_statuses=[], hook_events=[], evaluation=None, settings_check=None,
                environment=env, ledger=data.get("ledger"), artifacts={}, retries=retries, blind_id=blind,
                started_at=None, finished_at=None, history=None, models_reported=[],
                notes=[data.get("not_started") or data.get("not_runnable")],
                not_started=data.get("not_started"))
            if "not_runnable" in data:
                record["outcome"]["termination"] = "not_runnable"
            break
        run = data["run"]
        if not run["results"] and not run["timed_out"] and attempt_no == 1:
            retries.append({"attempt": 1, "reason": "no result event from the CLI (infrastructure failure)",
                            "exit_code": run["exit_code"], "artifacts": data["artifacts"], "ledger": data["ledger"],
                            "evaluation_judge": rr.judge_usage((data["evaluation"] or {}).get("semantic_judge_calls") or [])})
            continue
        record = build_record(
            prepared=data["prepared"], study=study, scenario=scenario, results=run["results"],
            timed_out=run["timed_out"], exit_code=run["exit_code"], session_s=run["session_s"],
            turn_statuses=data["turn_statuses"], turn_edges=data["turn_edges"],
            hook_events=data["hook_events"], evaluation=data["evaluation"],
            settings_check=data["settings_check"], environment=env, ledger=data["ledger"],
            artifacts={**data["artifacts"], "record": record_path.relative_to(ROOT).as_posix()},
            retries=retries, blind_id=blind, started_at=run["started_at"], finished_at=run["finished_at"],
            history=data["history"], notes=data["notes"], models_reported=data["models_reported"])
        break
    record_path.parent.mkdir(parents=True, exist_ok=True)
    record_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    o = record["outcome"]
    slips = [t["slip"] for t in record["turns"]]
    with LOCK:
        print(f"{rid:<38} {o['termination']:<16} steps={o['steps_reached']} slips={slips} "
              f"final={o['final_structural']} accepted={(o['behavior'] or {}).get('steps_accepted')} "
              f"cost={record['usage']['agent'].get('cost_usd')}", flush=True)
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--study")
    group.add_argument("--harness-check", metavar="NAME")
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--ledger", type=Path, default=spend_ledger.DEFAULT_PATH)
    args = parser.parse_args()
    if shutil.which("claude") is None:
        print("NOT RUN: the claude CLI is not on PATH")
        return 5
    study = pv.load_study()
    if args.harness_check:
        env = run_pilot.environment()
        if (pv.RUNS_DIR / args.harness_check).exists():
            print(f"refusing to reuse an existing harness-check directory: {args.harness_check}")
            return 1
        for arm in ("A", "B", "C"):
            entry = {"sequence": None, "repeat": 1, "scenario_id": HARNESS_SCENARIO["id"], "arm": arm,
                     "model_key": "haiku", "run_id": study_v2.run_id(HARNESS_SCENARIO["id"], arm, "haiku", 1)}
            run_session(HARNESS_SCENARIO, entry, study, args.harness_check, args.ledger, env, evaluate=False)
        return 0
    ev.check_frozen(ev.load_manifest(ev2.MANIFEST), ev2.current_frozen_hashes())
    scenarios = pv.load_scenarios()
    env = run_pilot.environment()
    plan = json.loads((pv.RUNS_DIR / args.study / "order.json").read_text())["runs"]
    todo = [e for e in plan if not (pv.RUNS_DIR / args.study / e["run_id"] / "record.json").exists()]
    workers = args.workers or study["workers"]
    print(f"{len(todo)} of {len(plan)} sessions to do; workers={workers}", flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(run_session, scenarios[e["scenario_id"]], e, study, args.study, args.ledger, env)
                   for e in todo]
        for f in futures:
            f.result()
    return 6 if STOP.is_set() else 0


if __name__ == "__main__":
    sys.exit(main())
