#!/usr/bin/env python3
"""Pre-freeze harness probes for the version 2 study (not study data).

    .venv/bin/python experiment/tools/probe_v2.py --out experiment/runs/probe-v2-2026-11-20/probes.json

Checks three things the version 2 protocol depends on, with Claude Haiku 5.5
and tiny budgets, every call charged to the shared spend ledger:

1. ``claude -p --input-format stream-json`` accepts several user messages in
   one process, emitting one ``result`` event per turn, when the driver waits
   for each result before sending the next message;
2. Stop and UserPromptSubmit hooks fire once per turn in that mode;
3. whether the workspace ``CLAUDE.md`` reaches the model with
   ``--setting-sources project`` and with ``--setting-sources ""`` (the
   pilot's setting, which is why the pilot also appended the instruction
   with ``--append-system-prompt-file``).

Each probe gets a scratch workspace under ``.tmp/probe-v2/`` holding only a
``CLAUDE.md`` with a marker word. The hook is a logger that records the event
name and returns nothing, so it does not influence the model.
"""

from __future__ import annotations

import argparse
import json
import secrets
import subprocess
import sys
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOLS = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / "src"), str(TOOLS)]

import spend_ledger  # noqa: E402

MODEL = "claude-haiku-5-5"
BUDGET = "0.20"
# One response at Haiku 5.5's documented limits and long-context rates
# (README, live-judge spend bound): US$1.32.
RESERVE = Decimal(BUDGET) + Decimal("1.32")
WORK = ROOT / ".tmp" / "probe-v2"

LOGGER = """import json, sys
event = json.load(sys.stdin)
with open(sys.argv[1], "a") as fh:
    fh.write(json.dumps({"hook_event_name": event.get("hook_event_name"),
                         "stop_hook_active": event.get("stop_hook_active")}) + "\\n")
"""

MESSAGES = (
    "Without using any tools, reply with only the marker word stated in your project "
    "instructions (CLAUDE.md). If you were given no project instructions, reply NONE.",
    "Reply with only the word DONE.",
)


def user_line(text: str) -> str:
    return json.dumps({"type": "user", "message": {"role": "user", "content": text}}) + "\n"


def probe(name: str, setting_sources: str, ledger: Path) -> dict:
    base = WORK / f"{name}-{secrets.token_hex(3)}"
    workspace = base / "workspace"
    workspace.mkdir(parents=True)
    marker = "MARKER-" + secrets.token_hex(3).upper()
    (workspace / "CLAUDE.md").write_text(f"# Project rules\n\nThe marker word is {marker}.\n")
    subprocess.run(["git", "init", "-q"], cwd=workspace, check=True)
    hook_log, logger = base / "hooks.jsonl", base / "logger.py"
    logger.write_text(LOGGER)
    hook = {"type": "command", "command": sys.executable, "args": [str(logger), str(hook_log)],
            "timeout": 30}
    settings = {"autoMemoryEnabled": False,
                "hooks": {"Stop": [{"hooks": [hook]}], "UserPromptSubmit": [{"hooks": [hook]}]}}
    settings_path = base / "settings.json"
    settings_path.write_text(json.dumps(settings))
    argv = ["claude", "-p", "--model", MODEL, "--input-format", "stream-json",
            "--output-format", "stream-json", "--verbose", "--no-session-persistence",
            "--setting-sources", setting_sources, "--settings", str(settings_path),
            "--tools", "Read", "--disallowedTools", "mcp__infracost", "--disable-slash-commands",
            "--permission-mode", "acceptEdits", "--max-budget-usd", BUDGET]
    guard = spend_ledger.FileSpendGuard(ledger, kind="agent")
    entry = guard.begin(f"probe-v2 {name} ({MODEL}, CLI)", RESERVE)
    proc = subprocess.Popen(argv, cwd=workspace, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True)
    assert proc.stdin is not None and proc.stdout is not None and proc.stderr is not None
    results, texts, start = [], [], time.monotonic()
    try:
        for message in MESSAGES:
            proc.stdin.write(user_line(message))
            proc.stdin.flush()
            for line in proc.stdout:
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if event.get("type") == "assistant":
                    for block in event.get("message", {}).get("content", []):
                        if block.get("type") == "text":
                            texts.append(block["text"])
                if event.get("type") == "result":
                    results.append({k: event.get(k) for k in
                                    ("subtype", "is_error", "num_turns", "total_cost_usd", "result")})
                    break
        proc.stdin.close()
        proc.wait(timeout=120)
    finally:
        if proc.poll() is None:
            proc.kill()
    cost = Decimal(str(results[-1]["total_cost_usd"])) if results and results[-1].get("total_cost_usd") is not None else None
    if cost is not None:
        guard.finish(entry, cost, {"results": len(results)}, note="probe; CLI-reported total_cost_usd")
    else:
        guard.fail(entry, None, note="probe; cost unknown, reservation kept")
    hooks = [json.loads(l) for l in hook_log.read_text().splitlines()] if hook_log.is_file() else []
    return {
        "probe": name, "setting_sources": setting_sources, "model": MODEL, "argv": argv[1:],
        "marker": marker, "results": results, "result_events": len(results),
        "first_reply": results[0]["result"] if results else None,
        "marker_in_first_reply": bool(results) and marker in (results[0]["result"] or ""),
        "hook_events": hooks, "exit_code": proc.returncode,
        "stderr_tail": proc.stderr.read()[-500:],
        "seconds": round(time.monotonic() - start, 1),
        "cost_usd": str(cost) if cost is not None else None,
        "cost_note": "total_cost_usd reported by the CLI for the whole process (cumulative over turns)",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, default=spend_ledger.DEFAULT_PATH)
    args = parser.parse_args()
    out = {"schema": "coding-agent-gates/probe-v2/v1", "evidence_kind": "real",
           "note": "pre-freeze harness probes; not study data",
           "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "claude_cli": subprocess.run(["claude", "--version"], capture_output=True, text=True).stdout.strip(),
           "probes": [probe("setting-sources-project", "project", args.ledger),
                      probe("setting-sources-empty", "", args.ledger)]}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=2) + "\n")
    for p in out["probes"]:
        print(p["probe"], "results:", p["result_events"], "marker:", p["marker_in_first_reply"],
              "hooks:", [h["hook_event_name"] for h in p["hook_events"]], "cost:", p["cost_usd"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
