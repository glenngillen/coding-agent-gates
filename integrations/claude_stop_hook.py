#!/usr/bin/env python3
"""Claude Code hook entrypoint for the architecture gate (Stop + UserPromptSubmit).

Configured in .claude/settings.json (see integrations/claude-code-settings.json):

    .venv/bin/python integrations/claude_stop_hook.py [--max-repairs N]

Reads the hook event JSON on stdin, runs the canonical sensor on Stop, and
prints the hook's JSON decision on stdout. State lives in
.claude/architecture-gate/ (one file per session). To clear it:

    .venv/bin/python integrations/claude_stop_hook.py --reset

When run as a hook this script always exits 0 with JSON output. Exit code 2
would be a *blocking* decision and a crash would fall to the settings'
``onFailure`` policy; both happen outside the adapter's repair budget. So bad
arguments, a missing ``gates`` package or any unexpected exception end the
turn with an UNRESOLVED warning instead of asking Claude for another repair.
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = ROOT / ".claude" / "architecture-gate"


def _unresolved(detail: str) -> str:
    return json.dumps({"systemMessage": (
        f"Architecture gate UNRESOLVED: {detail} The architecture check did not "
        "produce a result, so this candidate has not passed it. Do not treat it as "
        "complete; run integrations/check_architecture.py, or rely on the CI check "
        "before merging."
    )})


def load_adapter():
    """Import the adapter lazily so an import failure can be reported, not crash."""
    sys.path.insert(0, str(ROOT / "src"))
    from gates.sensor import run_sensor
    from gates.stop_hook import DEFAULT_MAX_REPAIRS, FileStateStore, handle_event

    return handle_event, FileStateStore, DEFAULT_MAX_REPAIRS, run_sensor


class _ArgumentError(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message):  # argparse would exit 2: a blocking Stop decision
        raise _ArgumentError(message)


def _positive_int(text: str) -> int:
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return value


def main(argv=None, *, stdin=None, stdout=None, stderr=None,
         load_adapter=load_adapter, state_dir=STATE_DIR, sensor=None) -> int:
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    parser = _Parser(description="Claude Code hook entrypoint for the architecture gate.")
    parser.add_argument("--max-repairs", type=_positive_int, default=None)
    parser.add_argument("--reset", action="store_true", help="delete all session state and exit")
    try:
        args = parser.parse_args(argv)
    except _ArgumentError as exc:
        print(_unresolved(f"the hook was configured with invalid arguments ({exc})."), file=stdout)
        return 0

    try:
        handle_event, store_class, default_max, run_sensor = load_adapter()
        store = store_class(state_dir)
        if args.reset:
            try:
                removed = store.reset_all()
            except OSError as exc:  # a human ran this; tell them it failed
                print(f"Could not reset {state_dir}: {exc}", file=stderr)
                return 1
            print(f"Removed {removed} session state file(s) from {state_dir}", file=stdout)
            return 0
        check = sensor or run_sensor
        outcome = handle_event(
            stdin.read(),
            run_sensor=lambda: check(ROOT),
            store=store,
            max_repairs=args.max_repairs or default_max,
        )
    except Exception as exc:  # never crash into Claude Code's onFailure policy
        print(_unresolved(f"the hook adapter failed ({exc!r})."), file=stdout)
        return 0

    if outcome.stdout:
        print(outcome.stdout, file=stdout)
    if outcome.stderr:
        print(outcome.stderr, file=stderr)
    return outcome.exit_code


if __name__ == "__main__":
    sys.exit(main())
