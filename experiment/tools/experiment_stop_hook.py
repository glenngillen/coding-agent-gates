#!/usr/bin/env python3
"""Stop-hook entrypoint for the experiment's arms B and C.

Installed by experiment/tools/prepare_run.py through the run's ``--settings``
file; it lives outside the agent's workspace, and so do the contract and the
gate code it runs. It wraps ``gates.stop_hook.handle_event``, the adapter the
article describes, with two experiment-only additions:

- the sensor checks ``--workspace`` against this example's development
  contract (``.importlinter`` at the example root), not a file inside the
  workspace;
- every Stop is appended to ``--events`` (JSON lines): sensor status and
  duration, semantic status and duration, judge calls with their reported
  usage and cost, and the decision returned. The run collector derives repair
  cycles, checker invocations and check time from this log.

With ``--semantic`` (arm C) a structurally passing candidate is judged by the
live Claude Haiku 5.5 judge through the Claude Code CLI, charged to the shared
spend ledger (``--ledger``). A judge that cannot run is logged with
``provider_failed: true``; the collector then records the run as not runnable
rather than treating it as arm B.

The version 2 study (experiment/protocol-v2.md) passes ``--contract`` (its own
contract outside the workspace) and ``--reviewed-exceptions``: an ignored
import whose exact ``ignore_imports`` entry is listed there is accepted
(``study_v2.accept_reviewed_exceptions``); the log keeps the raw status as
``sensor.raw_status``. Without these options the hook behaves exactly as it
did in the pilot.

Like integrations/claude_stop_hook.py it always exits 0 with JSON output, so
a failure can never become Claude Code's blocking exit 2 or fall to its
``onFailure`` policy outside the repair budget.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "src"), str(Path(__file__).resolve().parent)]

DEVELOPMENT_CONTRACT = ROOT / ".importlinter"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _unresolved(detail: str) -> str:
    return json.dumps({"systemMessage": (
        f"Architecture gate UNRESOLVED: {detail} The check did not produce a result, so this "
        "candidate has not passed it.")})


def _append(path: Path, event: dict) -> None:
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(event) + "\n")


def main(argv=None, *, stdin=None, stdout=None, clock=time.monotonic) -> int:
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--max-repairs", type=int, default=3)
    parser.add_argument("--semantic", action="store_true")
    parser.add_argument("--ledger", type=Path, default=None)
    parser.add_argument("--contract", type=Path, default=None)
    parser.add_argument("--reviewed-exceptions", type=Path, default=None)
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        print(_unresolved("the experiment hook was configured with invalid arguments."), file=stdout)
        return 0

    raw = stdin.read()
    event: dict = {"at": _now(), "run_id": args.run_id, "semantic_enabled": args.semantic}
    try:
        parsed = json.loads(raw)
        event["hook_event_name"] = parsed.get("hook_event_name")
        event["stop_hook_active"] = parsed.get("stop_hook_active")
    except Exception:  # noqa: BLE001 - malformed input is handled by handle_event below
        event["hook_event_name"] = None

    try:
        from gates.semantic import judge, load_context
        from gates.sensor import run_sensor
        from gates.stop_hook import FileStateStore, handle_event

        last = {}
        reviewed = None
        if args.reviewed_exceptions is not None:
            import study_v2
            reviewed = study_v2.parse_reviewed(json.loads(args.reviewed_exceptions.read_text(encoding="utf-8")))

        def sensor():
            start = clock()
            result = run_sensor(args.workspace, config=args.contract or DEVELOPMENT_CONTRACT)
            raw_status = result.status.value
            if reviewed is not None:
                result = study_v2.accept_reviewed_exceptions(result, reviewed)
            event["sensor"] = {"status": result.status.value, "seconds": round(clock() - start, 3),
                               "fingerprint": result.fingerprint,
                               "violations": result.to_dict()["violations"], "error": result.error}
            if reviewed is not None:
                event["sensor"]["raw_status"] = raw_status
            last["result"] = result
            return result

        run_semantic = None
        if args.semantic:
            import spend_ledger
            from gates.claude_cli_judge import ClaudeCliJudgeProvider

            provider = ClaudeCliJudgeProvider(
                guard=spend_ledger.FileSpendGuard(args.ledger or spend_ledger.DEFAULT_PATH, kind="judge"),
                label=f"{args.run_id} development judge")

            def run_semantic():
                start = clock()
                outcome = judge(last["result"], load_context(args.workspace), provider)
                event["semantic"] = {
                    "status": outcome.status, "reason": outcome.reason,
                    "provider_failed": outcome.provider_failed,
                    "findings": [f.__dict__ for f in outcome.findings],
                    "seconds": round(clock() - start, 3),
                    "calls": [c.to_json() for c in provider.calls],
                }
                return outcome

        outcome = handle_event(raw, run_sensor=sensor, store=FileStateStore(args.state_dir),
                               max_repairs=args.max_repairs, run_semantic=run_semantic)
    except Exception as exc:  # noqa: BLE001 - never crash into Claude Code's onFailure policy
        event["adapter_error"] = repr(exc)
        text = _unresolved(f"the experiment hook failed ({exc!r}).")
        event["decision"] = "allow"
        event["output"] = json.loads(text)
        _safe_append(args.events, event)
        print(text, file=stdout)
        return 0

    payload = json.loads(outcome.stdout) if outcome.stdout else {}
    event["decision"] = "block" if payload.get("decision") == "block" else "allow"
    event["output"] = payload
    _safe_append(args.events, event)
    if outcome.stdout:
        print(outcome.stdout, file=stdout)
    return 0


def _safe_append(path: Path, event: dict) -> None:
    try:
        _append(path, event)
    except OSError:
        pass  # the hook's answer matters more than its log; a gap shows as a missing event


if __name__ == "__main__":
    sys.exit(main())
