"""Command-line interface for the canonical sensor.

Exit status: 0 pass, 1 violation, 3 checker error (rules not checked).
Usage errors exit 2 (argparse). Every gate placement runs this same command.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from gates.cache import ResultCache
from gates.result import SensorResult, format_diagnostic
from gates.sensor import run_sensor

EXAMPLE_ROOT = Path(__file__).resolve().parents[2]


def main(
    argv: Sequence[str] | None = None,
    *,
    sensor: Callable[..., SensorResult] = run_sensor,
    out=None,
) -> int:
    out = out or sys.stdout
    parser = argparse.ArgumentParser(
        prog="check_architecture",
        description="Check the order service's architecture contracts (full package).",
    )
    parser.add_argument("--root", type=Path, default=EXAMPLE_ROOT,
                        help="example root containing .importlinter and src/ (default: this example)")
    parser.add_argument("--json", action="store_true", help="print the full result as JSON")
    parser.add_argument("--cache-dir", type=Path, default=None,
                        help="reuse results for an identical snapshot (off by default)")
    args = parser.parse_args(argv)

    cache = ResultCache(args.cache_dir) if args.cache_dir else None
    result = sensor(args.root, cache=cache)
    print(result.to_json() if args.json else format_diagnostic(result), file=out)
    if not args.json and result.raw_output and result.status.value != "pass":
        print("\n--- lint-imports output ---\n" + result.raw_output.strip(), file=out)
    return result.status.exit_code
