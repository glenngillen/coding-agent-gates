# Analysis: from retained records to reported numbers

Every number reported about the pilot must be reproducible from the files in
`runs/<pilot>/` and the ledger. This page explains how to get those numbers
and what they can and cannot support. The rules come from `protocol.md`
("Reporting rules").

## Commands

From the example root, with the pinned environment:

```sh
# 1. The frozen criteria are unchanged (exit 1 otherwise).
.venv/bin/python experiment/tools/freeze.py --check

# 2. The acceptance tests still separate the baseline, the references and the negative variants.
.venv/bin/python experiment/tools/validate_tasks.py

# 3. Rebuild the summary from the retained records (the calibration file is optional).
.venv/bin/python experiment/tools/summarize.py --pilot pilot-2026-11-19 \
    --calibration evidence/live-judge-20261119-calibration.json \
    --out experiment/runs/pilot-2026-11-19/summary.json
```

The summarizer reads only `runs/<pilot>/*/record.json` (plus each record's
retained evaluation and hook log for the judge section). It refuses to mix
`real` and `synthetic-test` records. Unit tests build synthetic records in
memory only. No synthetic record is stored under `runs/`.

## Definitions

- **Attempted run.** Each entry in `order.json`. Every one gets a record,
  including runs the spend cap never started (`not_started_cap`) and runs
  that were not runnable. `missing_records` must be 0.
- **Started run.** An attempted run whose agent process started
  (`outcome.agent_started`). A not-runnable arm C run whose agent ran but whose
  development judge was unavailable is started, but never completed within
  budget or accepted.
- **Completed within budget.** Termination `completed`: the CLI reported
  success inside its budget and the wall-clock limit.
- **Behaviour pass.** The frozen acceptance test and the frozen regression
  test both passed on the final snapshot. A pytest error is `error`, never
  `fail` or `pass`.
- **Structural pass.** The evaluator's frozen contract passed on the final
  snapshot. `checker_error` means the snapshot was not checked.
- **Accepted outcome.** Completed within budget, behaviour pass, structural
  pass, and no tampering. The judge's verdict is reported next to it and is
  not part of it, because without independent labels it is an output, not a
  measurement of correctness.
- **Tampering.** The evaluator's comparison of the workspace instruction and
  configuration and the out-of-workspace gate files with their preparation
  hashes. For runs recorded after the pilot it also includes the external
  `--settings` file (`settings_file_check`: `changed`, `missing` or
  `unreadable` is tampering). The summary counts `settings_file_check` by
  value. In pilot-2026-11-19 every run is `not_checked`: a run that edited
  or deleted its settings file would not have been detected.
- **Repair cycles.** The number of Stop-hook blocks in arms B and C. A run
  whose gate did not end in a pass is censored. Its cycle count is a lower
  bound and is never averaged with converged runs. Arm A has no repair
  cycles; that is a different thing from zero.
- **Spend.**
  - Agent cost: the CLI's reported `total_cost_usd`.
  - Judge cost: each call's reported cost.
  - When a cost is unknown, the ledger keeps the reservation as the charge.
    This applies to agent runs and to judge calls from development and
    evaluation alike. The summary adds those charges to
    `held_for_unknown_cost` (and so to `total_charged`) and counts the runs
    affected. A judge call records its own ledger charge; one that cannot
    state it is counted in `judge_unknown_cost_calls_without_recorded_hold`
    rather than guessed.
  - Total spend includes failed, unaccepted, not-runnable and retried runs,
    plus judge calls from development and evaluation. A retried attempt's
    judge usage (and any unknown-cost holds) is read from its
    `infrastructure_retries[].usage`.

  These figures are API-equivalent list-price estimates, notional under a
  subscription login, not invoices.
- **Cost per accepted outcome.** Total charged spend divided by accepted
  outcomes. It is undefined (`null` with a note) when there are none.
  Optional currency conversion needs dated, category-specific rates, and any
  compute or CI cost must be reported separately. The pilot reports neither.

- **Token usage.** `usage_tokens` gives, per arm, a distribution (median,
  quartiles, range) for each category (`input_tokens`, `output_tokens`,
  `cache_read_input_tokens`, `cache_creation_input_tokens`) and for each
  source separately: the agent, the development judge and the evaluation
  judge. Each category states `observed_runs` and `missing_runs` out of
  `applicable_runs`. A source applies to a started run only if the run made
  a call of that kind (arms A and B make no development judge calls). A run
  whose source did not report a category is missing for that category,
  never zero. An agent category is missing when any model the CLI reported
  lacks it. A judge category is missing when any started call lacks it.

## Reading the summary

- **By arm.** Read the termination, behaviour, structure, judge-output and
  gate-state counts with their denominators (`attempted`, `started`). Read
  medians with their quartiles and range. With one run per cell, a difference
  of one or two runs between arms is within what run-to-run variation could
  produce. Describe it; do not infer from it.
- **Paired by task.** Each task's three arms side by side. This is the most
  informative view in a 10-task pilot.
  - If arm A's final snapshot never violates the structural rule, there is a
    ceiling effect: the pilot cannot show whether structural feedback
    improves the outcome on that rule.
  - If arm A violates the rule and B does not, that is one observed paired
    difference, not an effect size.
- **Judge.** Final-snapshot judge outputs by arm, abstentions, evaluation
  provider failures, and disagreements between arm C's last development
  verdict and the evaluation verdict. Calibration agreement with the authored
  labels is a count. False-positive and false-negative rates are `null`: they
  need independent human labels (`adjudication.md`), and none were supplied.

## What the pilot cannot support

- **A claim that one arm is generally better.** It has one model, one effort
  level, one CLI version, ten tasks written by one author, and one run per
  cell.
- **Judge accuracy figures.** There are no independent labels.
- **Cost or time savings beyond these runs.** Prompt caching and concurrency
  affect both (see `protocol.md`, "Threats").
- **Claims about merge blocking.** Final snapshots are synthetic final
  submissions; nothing was merged.

## Open questions

- Should a statistical comparison be attempted?
  - evidence: The pilot has one run per cell (30 runs). Paired differences on ten tasks cannot separate an arm's effect from run-to-run variation.
  - options: Report descriptive paired outcomes only (current); collect at least three repeats per cell under the frozen protocol before any inferential test.
  - location: analysis.md / Reading the summary
