# Reproducing the follow-up study (version 2)

[`protocol-v2.md`](protocol-v2.md) is frozen: its hash is recorded in
[`v2/frozen-manifest.json`](v2/frozen-manifest.json), and the runner refuses to
start if any frozen file has changed. Its "Running it" block therefore still
shows the commands used for the retained study, `follow-up-v2-2026-11-20`. Don't
reuse that name to run the study again:

- `prepare_v2.py plan` refuses to overwrite an existing `order.json` and exits 1.
- `run_study_v2.py` skips every session that already has a `record.json`, so
  with the retained name it would start nothing.

There are two different things you might want to do. Recomputing the retained
results is free. Running fresh sessions spends real money.

## Recompute the retained results (free, no CLI calls)

This reads the 36 retained records in `runs/follow-up-v2-2026-11-20/` and
writes the summary somewhere else, so the committed `results-v2.md` stays as it
is. Run from `examples/coding-agent-gates/`:

```sh
.venv/bin/python experiment/tools/freeze.py --v2 --check
mkdir -p .tmp
.venv/bin/python experiment/tools/summarize_v2.py --study follow-up-v2-2026-11-20 \
    --out .tmp/results-v2-recompute.md
diff .tmp/results-v2-recompute.md experiment/results-v2.md && echo identical
```

`.tmp/` is gitignored both here and in a standalone copy of this example, so the
same commands work in either place.

## Run the study again (spends money)

Pick one new study name and use it in all three steps. The example below uses
`follow-up-v2-rerun-1`. If you've already used that name, choose another.

```sh
STUDY=follow-up-v2-rerun-1
.venv/bin/python experiment/tools/freeze.py --v2 --check
.venv/bin/python experiment/tools/prepare_v2.py plan --study "$STUDY"
.venv/bin/python experiment/tools/run_study_v2.py --study "$STUDY"
.venv/bin/python experiment/tools/summarize_v2.py --study "$STUDY" \
    --out "experiment/runs/$STUDY/results.md" --json "experiment/runs/$STUDY/summary.json"
```

- The plan is written to `experiment/runs/$STUDY/order.json`. It has the same
  36 sessions and frozen seed as the original, so the session order matches.
- Session workspaces go under `.tmp/runs/$STUDY/` and retained artifacts under
  `experiment/runs/$STUDY/`. Neither touches the frozen files or the retained
  `follow-up-v2-2026-11-20` records.
- Write the summary inside the new study directory, as shown. Don't write it to
  `experiment/results-v2.md`, which is the retained study's result.
- If a run is interrupted, run the same `run_study_v2.py --study "$STUDY"`
  command again. It resumes and only starts sessions that have no `record.json`
  yet.
- You need a logged-in `claude` CLI on `PATH`. Every session reserves its worst
  case in `experiment/runs/spend-ledger.json` before it starts. Once the shared
  US$100 cap would be passed, the remaining sessions are recorded as
  `not_started_cap`. The original study reported US$5.84 of agent spend and
  US$0.19 of judge spend (notional API-equivalent figures). A rerun costs about
  the same, but model behaviour and pricing may have changed since then.
- A rerun is a new study of the same frozen protocol. Report it on its own,
  with its own denominators, rather than pooling it with the 2026-11-20 records.
