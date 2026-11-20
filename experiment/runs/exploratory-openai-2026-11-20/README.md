# Exploratory OpenAI probes, 2026-11-20

Exploratory probes through OpenAI's Codex CLI. **Not study data**: no protocol
was fixed in advance, there are two sessions per cell, and only scenario S1 was
run. `probes.json` records the 40 sessions and explains what was discarded.

## Files

- `codex_probe.py` runs the probes: one `codex exec` turn per step, in the same
  thread, with the instruction file delivered as `AGENTS.md`.
  - Arm A: guidance only.
  - Arm B: after each turn, an outer loop runs the import-contract sensor and
    hands its diagnostic back, up to 3 repair requests.
- `probe.py` holds the shared helpers: workspace preparation, the instruction
  variants and the controller-to-infrastructure import scan. It builds on
  `experiment/tools/` (`prepare_v2`, `run_study_v2`, `run_record`,
  `spend_ledger`).
- `huge.py` generates the large handbooks used by `probe.py`'s `huge*`
  variants. The OpenAI probes don't use those variants.
- `probes.json` holds the recorded sessions.

## Set up

1. Follow [Set up](../../../README.md#set-up) in the repository README. Every
   command below runs from the repository root, using its `.venv`.
2. Install the Codex CLI. The recorded run used `codex-cli 0.167.2`.
3. Sign in to the Codex CLI (`codex login`). The recorded run used a ChatGPT
   login. The probes start with `--ignore-user-config` and `--ignore-rules`,
   so your Codex settings don't affect them.

## Run

```sh
.venv/bin/python experiment/runs/exploratory-openai-2026-11-20/codex_probe.py \
  TAG MODEL SCENARIO REPEATS VARIANTS ARMS
```

- `TAG` names this batch of runs.
- `MODEL` is passed to `codex exec -m`.
- `SCENARIO` is a scenario id from the v2 study.
- `REPEATS` is the number of sessions per variant and arm.
- `VARIANTS` is a comma-separated list from `stated`, `one-line`, `unstated`,
  `shortcut` and `conflict`.
- `ARMS` is a comma-separated list from `A` and `B`.

To repeat the recorded grid (5 variants × 2 arms × 2 sessions, for each model):

```sh
for model in gpt-5.6-luna gpt-6.2-sol; do
  .venv/bin/python experiment/runs/exploratory-openai-2026-11-20/codex_probe.py \
    openai "$model" S1-customer-insights 2 \
    stated,one-line,unstated,shortcut,conflict A,B
done
```

Each session prints one JSON line. Up to three sessions run at once. Workspaces,
logs and a `probe-result.json` per session are written to `codex-runs/` beside
the script.

Each session makes real Codex requests under your account. Results will vary
from run to run and won't reproduce `probes.json` exactly.
