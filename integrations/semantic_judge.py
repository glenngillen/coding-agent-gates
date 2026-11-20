#!/usr/bin/env python3
"""Offline demonstration of the semantic stage, using a SYNTHETIC provider.

    .venv/bin/python integrations/semantic_judge.py --synthetic violation-discount-in-controller

Runs the real structural sensor first. Only if it passes does it build the
judge request from the controller modules and hand it to a provider that
returns a hand-written response from semantic/synthetic-responses.json. No
model is called; the output demonstrates the adapter's outcome handling, not
any judge's accuracy. The live Claude Haiku 5.5 provider is
``gates.claude_cli_judge.ClaudeCliJudgeProvider``, run over the fixtures by
experiment/tools/run_live_judge.py.

Exit status: 0 pass, 1 violation, 3 inconclusive, 4 not evaluated
(structural check failed).
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gates.result import format_diagnostic  # noqa: E402
from gates.semantic import format_outcome, judge, load_context  # noqa: E402
from gates.sensor import run_sensor  # noqa: E402

EXIT = {"pass": 0, "violation": 1, "inconclusive": 3, "not_evaluated": 4}


def main() -> int:
    responses = json.loads((ROOT / "semantic" / "synthetic-responses.json").read_text())
    by_id = {r["id"]: r["response"] for r in responses["responses"]}
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--synthetic", required=True, choices=sorted(by_id))
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--show-request", action="store_true", help="print the judge request")
    args = parser.parse_args()

    structural = run_sensor(args.root)
    print(format_diagnostic(structural).splitlines()[0])

    def synthetic_provider(request):
        if args.show_request:
            print("--- instructions ---\n" + request.instructions)
            print("--- payload (data) ---\n" + request.payload)
        return by_id[args.synthetic]

    outcome = judge(structural, load_context(args.root), synthetic_provider)
    print(f"[synthetic provider: {args.synthetic}; not a model output]")
    print(format_outcome(outcome))
    return EXIT[outcome.status]


if __name__ == "__main__":
    sys.exit(main())
