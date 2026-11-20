#!/usr/bin/env python3
"""Write or check experiment/frozen-manifest.json: the hashes of every frozen criterion.

    .venv/bin/python experiment/tools/freeze.py --check   # exit 1 if anything changed
    .venv/bin/python experiment/tools/freeze.py --write   # only before the first run
    .venv/bin/python experiment/tools/freeze.py --v2 --check|--write   # the version 2 study

The frozen files are listed in ``evaluator.evaluate.FROZEN_PATTERNS``: the
instruction, the arms, the tasks, the evaluator, its contract and acceptance
tests, the regression test and the semantic rubric. The evaluator refuses to
evaluate when they differ from the manifest. Rewriting the manifest after a
run has started changes the study; the protocol requires recording why.

With ``--v2`` the patterns are ``evaluator.evaluate_v2.FROZEN_PATTERNS`` and the
manifest is ``experiment/v2/frozen-manifest.json``. ``--v2 --write`` refuses to
overwrite an existing v2 manifest: version 2 is frozen once, before any run.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "experiment"))

from evaluator import evaluate as ev  # noqa: E402
from evaluator import evaluate_v2 as ev2  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--write", action="store_true")
    group.add_argument("--check", action="store_true")
    parser.add_argument("--note", default="", help="why the manifest is being (re)written")
    parser.add_argument("--v2", action="store_true", help="the version 2 study's manifest")
    args = parser.parse_args()
    path = ev2.MANIFEST if args.v2 else ev.MANIFEST
    patterns = ev2.FROZEN_PATTERNS if args.v2 else ev.FROZEN_PATTERNS
    current = ev2.current_frozen_hashes() if args.v2 else ev.current_frozen_hashes()
    if args.check:
        try:
            ev.check_frozen(ev.load_manifest(path), current)
        except (ev.FrozenCriteriaChanged, OSError, ValueError) as exc:
            print(f"NOT FROZEN: {exc}")
            return 1
        print(f"frozen: {len(current)} files match {path.relative_to(ROOT)}")
        return 0
    if args.v2 and path.exists():
        print(f"refusing to overwrite {path.relative_to(ROOT)}: version 2 is frozen once, before any run")
        return 1
    manifest = {
        "schema": "coding-agent-gates/frozen-manifest/v1",
        "written_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "note": args.note,
        "patterns": list(patterns),
        "files": current,
        "tree_sha256": ev.tree_hash(current),
    }
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {path.relative_to(ROOT)} ({len(current)} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
