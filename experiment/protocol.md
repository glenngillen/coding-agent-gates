# Study protocol: does architectural feedback help a coding agent?

**Frozen 2026-11-19, before any study run.** The frozen inputs are hashed in
`frozen-manifest.json`, and the evaluator refuses to run if any of them
changes (`tools/freeze.py --check`). Two harness checks ran before the freeze
on a non-study task (see "Harness checks"). They are not study data.

This protocol compares three kinds of development-time feedback at a single
gate placement. The pilot is exploratory: 30 runs, one per task and arm. It
can show what happened on these tasks, with this model, on this machine. It
cannot establish that one arm is better in general, and it fixes no expected
winner.

## Question

When a coding agent works on a legitimate feature that also offers an easy
architectural shortcut, what happens to its final submission under each
condition below?

1. **A.** Instruction only.
2. **B.** Instruction plus deterministic structural feedback.
3. **C.** Instruction plus deterministic structural feedback plus a narrow
   semantic judge.

The outcomes are behavioural acceptance, structural violations, the judge's
output, completion, repair effort, time and spend. Each one is recorded
separately (see "Measurements").

## Arms

All three arms use the same placement: the end of the agent's turn (a Claude
Code `Stop` hook). They get the same instruction, the same task text, the same
tools and the same budgets. The intended difference is the feedback.

| Arm | Development-time feedback | Stop hook (`arms.json`) |
| --- | --- | --- |
| A | None. The architecture evaluation stays hidden while the agent works. | none |
| B | The import-contract sensor runs on every Stop. A violation or checker error blocks the stop with the diagnostic, up to 3 repair requests. | `experiment_stop_hook.py` |
| C | B, and then, after a structural pass, the live Claude Haiku 5.5 judge checks the rubric. A semantic violation requests a repair from the same budget of 3. An abstention or a judge failure ends the loop without a pass. | `experiment_stop_hook.py --semantic` |

- **One instruction for every arm.** The instruction is `instruction.md`,
  installed as `CLAUDE.md` and passed with `--append-system-prompt-file`. It
  states the structural rule (controllers must not import
  `orders.infrastructure`) and the semantic rule (business decisions,
  including discount eligibility, belong in the application layer). Every arm
  receives the semantic rule. Only arm C gets judge feedback on it.
- **The rubric is narrower than the instruction.** The judge's rubric
  (`semantic/rubric.md`) covers pricing and discount decisions only. The
  instruction also asks for status-change rules and business limits to live
  in the application layer. No arm gets feedback on those, and the evaluator
  has no automated check for them.
- **The repair budget of 3 is a judgment call** (Decisions, 2026-11-19). It was
  not derived from data.
- **Arm C is never replaced by arm B.** If the judge cannot run (the CLI is
  missing, the ledger refuses the call, the call fails or times out), the run
  is recorded as not runnable. It is never silently treated as an arm B run.
  This holds even when the agent itself finished successfully and the final
  checks passed: the run never received arm C's feedback, so it is never an
  accepted outcome. Its agent usage, spend and artifacts stay in the record
  (`agent_started`, `agent_termination`).

## Workspace and isolation

Each run starts from an identical clean snapshot (`tools/prepare_run.py`):

- **A fresh Git repository** holding a copy of the baseline `src/orders`, its
  two test modules, a minimal `pyproject.toml`, `CLAUDE.md` and a `.venv` link
  to the example's pinned environment. The baseline is committed with a fixed
  identity and date, so the final diff is exact.
- **No gate code in the workspace.** The contract, the sensor, the rubric,
  the fixtures, the evaluator, the tasks and the experiment tooling all stay
  outside it. The hook (B and C) runs the development contract
  (`.importlinter`) from outside the workspace. The evaluator uses its own
  frozen copy (`evaluator/.importlinter`).
- **A fresh agent process for every run.** It runs with
  `--no-session-persistence` and `--setting-sources ""`, so no user, project or
  local settings or `CLAUDE.md` files are loaded. A per-run `--settings` file
  turns auto-memory off and installs the arm's hook (if it has one).
- **Machine-specific context excluded.** The building machine's enterprise
  MCP server is removed with `--disallowedTools mcp__infracost`, and skills
  with `--disable-slash-commands`. `--strict-mcp-config` is refused under an
  enterprise MCP configuration. A probe on 2026-11-19 confirmed that with these
  flags the agent sees the instruction and none of the building machine's
  `CLAUDE.md` or memory files. The harness check confirmed that only the six
  built-in tools remain.
- **The same tools and permissions in every arm.** The tools are `Bash`,
  `Read`, `Edit`, `Write`, `Glob` and `Grep`. The permission mode is
  `acceptEdits` with `--permission-prompts none`. `Bash` is allowed only for
  `.venv/bin/python -m pytest`, `ls`, `git status` and `git diff`. Anything
  else is denied automatically, and no person answers prompts.

## Fixed configuration

| Item | Value |
| --- | --- |
| Agent | Claude Code CLI 2.1.322, `--model claude-sonnet-5-5`, `--effort medium`, stream-json output |
| Judge | `claude-haiku-5-5` through `gates.claude_cli_judge` (rubric `semantic/rubric.md`) |
| Per-run spend cap | `--max-budget-usd 2.50` (checked by the CLI after each response) |
| Per-run wall clock | 1,500 s, measured with `time.monotonic()`; then the process group is terminated |
| Repair budget | 3 repair requests per run (one user turn) |
| Judge timeout | 180 s per call; hook timeout 330 s (C) or 150 s (B) |
| Seeds | Not supported by the CLI; none set. Runs are not deterministic. |
| Shared spend cap | US$100 across all judge and agent usage (`runs/spend-ledger.json`) |
| Concurrency | 3 runs at a time, taken from the frozen order |

Model identity is pinned by ID. The models overview describes dateless IDs as
pinned snapshots. Each record also stores the models the CLI reports in
`modelUsage`.

## Tasks

There are ten feature requests in the order service (`tasks/*.json`). Each is
a legitimate feature with a plausible shortcut:

1. T01 lookup
2. T02 filtering
3. T03 totals
4. T04 discounts
5. T05 cancellation
6. T06 pagination
7. T07 bulk retrieval
8. T08 status updates
9. T09 audit history
10. T10 validation

The agent receives only the `request` text plus the frozen suffix in
`arms.json`. The `plausible_shortcuts` field is for readers and is never shown
to the agent.

- **Acceptance tests.** `evaluator/acceptance/test_<task>.py` holds each
  task's frozen acceptance test. It is run together with the baseline's frozen
  behaviour test (`tests/unit/orders/test_order_behaviour.py`) as a
  regression check.
- **Validation before the freeze.** `tools/validate_tasks.py` checks every
  acceptance test against three things: the baseline (must fail), a reference
  implementation (`evaluator/reference/<task>/`, must pass) and declared
  negative variants (`evaluator/reference/negatives.py`). The variants include
  behaviour-preserving direct imports that must pass behaviour and fail
  structure. The output is in `evidence/task-validation-2026-11-19.json`.
- **Same author.** The building agent wrote the tasks, the references and
  the acceptance tests. That is a threat to validity (see "Threats").

## Run order

`tools/prepare_run.py plan --pilot pilot-2026-11-19 --seed 20261119` writes
`runs/pilot-2026-11-19/order.json` before the first run. Tasks keep their
frozen order. The three arms are shuffled within each task with
`random.Random(20261119)`. With 3 workers, the three arms of a task usually run
at the same time, so they see similar API conditions. Each record stores the
run's sequence number and its position within the task.

## Stopping rules and caps

- **The spend ledger before every run.** Every agent run reserves
  `max-budget-usd` plus one Sonnet 5.5 response at its documented limits and
  highest rates (1M context × US$4/MTok + 128K output × US$10/MTok = US$5.28),
  so each run reserves US$7.78. Every judge call reserves its own bound (see
  `gates/claude_cli_judge.py`). The CLI's reported `total_cost_usd` then
  replaces the reservation. It is an API-equivalent estimate, notional under a
  subscription login.
- **The cap.** If the ledger refuses a run, no further runs start. That run
  and every later one are recorded with termination `not_started_cap`
  (censored). Nothing is dropped.
- **Ends within a run.** A run ends when the agent finishes, when the CLI's
  budget is exhausted (`budget_exhausted`), at the wall-clock limit
  (`wall_timeout`) or on a CLI error (`cli_error`). The hook ends its own loop
  when the repair budget is exhausted (gate state `unresolved`).
- **Infrastructure retries.** If the CLI produces no result at all and the
  run did not time out, the cell is retried once in a fresh workspace. The
  failed attempt stays in the record's `infrastructure_retries`, with its
  artifacts, its agent ledger charge and the usage of any judge calls it made
  (development and evaluation, including unknown-cost holds). All of it counts
  towards total spend. There are no other retries.
- **No human interventions.** None are permitted. Any that happen are
  recorded in `interventions`.
- **No stopping for results.** The pilot does not stop early because of
  interim results. A changed frozen manifest stops evaluation.

## Independent evaluation

The evaluator (`evaluator/evaluate.py`, run by `tools/run_pilot.py` after
each run) reads only the final snapshot and the run's preparation record.

1. **Behaviour.** It copies the frozen acceptance test and the regression
   test into a fresh directory and runs them against the snapshot's `src`
   only. A guard fails every test if `orders` is imported from anywhere else.
2. **Structure.** It runs the sensor with the evaluator's frozen contract.
   Edits to the workspace or to the development contract cannot change this
   result.
3. **Semantics.** It asks the live judge about the snapshot's controllers, in
   every arm (the judge is skipped after a structural violation). The result
   is recorded as a judge output. The semantic label is always `null`: no
   independent human labels will be supplied (Decisions, 2026-11-19).
4. **Tampering.** It compares the workspace's instruction and configuration
   and every out-of-workspace gate file with the hashes recorded at
   preparation. Added workspace settings count as tampering. Edited or deleted
   baseline tests are reported separately.

   *Amendment, 2026-11-19, after pilot-2026-11-19.* The frozen evaluator did
   not compare the external `--settings` file that installs the Stop hook, so
   the pilot's tampering check could not see a run that edited or deleted it.
   Later runs compare that file with its preparation hash
   (`evaluator/settings_integrity.py`, `settings-integrity/v1`): a changed,
   deleted or unreadable file counts as tampering. `evaluate.py` and the
   frozen manifest are unchanged, and the pilot's records say
   `settings_file_check: "not_checked"`.

A final snapshot is a synthetic final submission. Nothing is merged, and no
record may describe a merge as attempted or blocked.

## Measurements

`run-record.schema.json` defines every field. `run-record.template.json` is an
unpopulated template. Each attempted run gets
`runs/<pilot>/<run_id>/record.json`, which records:

- **Identity.** Run, task, arm, sequence, blind id, baseline and final tree
  hashes, prompt/task/instruction/arms/settings hashes, frozen-manifest hash,
  requested and reported models, CLI, Python and Import Linter versions, and
  timestamps.
- **Outcome.** Termination, completion within budget, behaviour, structure,
  judge output, tampering, edited baseline tests, the gate's final state and
  not-runnable reasons. Each is a separate field.
- **Repair effort.** Repair requests (Stop-hook blocks) and checker
  invocations (sensor runs and judge calls, counted separately). A loop that
  did not converge is `censored`, never zero. Arm A's repair effort is "not
  applicable".
- **Usage.** Per-model agent token categories and the reported cost, plus
  development-judge and evaluation-judge usage, each separately. Missing
  usage stays missing.
- **Time.** Monotonic time for the attempt, the CLI-reported duration and API
  time, sensor time and judge time. CI queue time does not apply at this
  placement.
- **Artifacts.** Each run keeps a redacted, truncated transcript, the hook
  log, the final diff, the evaluation, CLI stderr and the preparation record.
  Local absolute paths are replaced and secret-shaped strings removed.

The pilot ledger (`runs/spend-ledger.json`) holds every charge, including the
harness checks and probes.

## Pilot and optional designs

- **Pilot (this protocol).** 10 tasks × 3 arms × 1 run = 30 runs, within the
  shared US$100 cap. One run per cell is exploratory.
- **Optional repeats.** If budget remains after the pilot, each cell may be
  repeated at least three times under this same frozen protocol. That needs a
  new plan file with `--repeats` and a declared budget. The pilot does not run
  them. Expanding to 20 tasks would need new frozen tasks and a declared
  budget.
- **Optional placement study.** This is a separate study with arm B and these
  tasks held fixed, comparing three placements:
  - **Stop hook:** feedback goes to the agent in-session.
  - **Pre-commit:** the agent is told to commit when done. A rejected commit's
    output is the feedback, and the agent must commit again.
  - **CI:** the agent submits by pushing. A harness retrieves the failed
    check's diagnostic and starts a new agent turn with it.

  Each placement uses the same repair budget and the same spend and time caps.
  CI queue time counts as part of the CI placement's elapsed time. It needs
  its own frozen protocol and is not run here.

## Reporting rules (declared before any run)

- **Report every attempted run.** That includes `not_started_cap`,
  not-runnable runs, timeouts, CLI errors and retries, each with its
  denominator.
- **Report null, negative and incomplete results as they are.**
  - If no arm differs, the comparison is inconclusive.
  - If B or C does worse, or costs more without improving final acceptance,
    report that.
  - If the cap cuts the pilot short, report the incomplete set.
- **Ceiling effect.** If the agent never takes the structural shortcut in arm
  A, report a ceiling effect for that rule: the pilot cannot show whether
  structural feedback helps. The tasks will not be made more misleading after
  the outcomes are seen.
- **No post-hoc tailoring.** Tasks, acceptance tests, the instruction, the
  arms and the rubric stay frozen. Any change after the first study run needs
  a new protocol version, and earlier runs stay reported under the old one.
- **Semantic outcomes are judge outputs.** Without independent labels, the
  judge's false-positive and false-negative rates on final runs are
  unavailable. Agreement with the authored calibration labels is a count.
- **Keep claims inside the pilot.** Conclusions cover these ten tasks, this
  model and effort, this CLI version, this machine and one run per cell.

## Threats that narrow or invalidate comparisons

- **Model alias drift.** The model is pinned by ID, and the reported
  `modelUsage` is recorded. If a run reports a different or additional model,
  the comparison for that run is not like-for-like and is reported as such.
- **Cached context.** Prompt caching can make later or concurrent runs
  cheaper and faster through shared prefixes. Cache read and write tokens are
  recorded per run. Cost and time comparisons between arms are descriptive
  only.
- **Changed order.** Arm order is randomized within each task and recorded.
  Position effects are not modelled with one run per cell.
- **Hidden retries.** The CLI retries some API errors internally. Those
  retries are not visible except as elapsed time. Harness-level retries are
  recorded.
- **Differing check timing.** Arms B and C spend time in the hook (sensor,
  and the judge in C), which adds wall time and turns. That is part of what is
  measured, not noise to subtract, but it means time is not a pure
  agent-effort measure.
- **Same author.** The tasks, the acceptance tests, the references, the
  calibration labels and the rubric were written by one author (the building
  agent). The tasks could unintentionally favour one arm.
- **The judge in the evaluation.** The evaluation uses the same judge model
  that arm C used during development. Its final verdicts on arm C snapshots
  are not independent of arm C's feedback.
- **Concurrency.** Concurrent runs share rate limits and machine load. That
  affects time more than outcomes.
- **Small sample.** One run per cell cannot separate the effect of an arm
  from run-to-run variation.

## Harness checks

These ran before the freeze, on the non-study task `H00-harness-check`, and
are not study data:

- **`runs/harness-check-2026-11-19/`.** Arms B and C showed that the Stop
  hook's block decision continues the conversation in `-p` mode, that the
  agent repairs, and that arm C's judge runs after the structural pass. The
  agent's tool list included the machine's enterprise MCP tools, which led to
  the exclusion flags above.
- **`runs/harness-check-2026-11-19b/`.** Arm B was rerun with the exclusions.
  Only the six built-in tools remained.

## Open questions

- Is Claude Sonnet 5.5 at medium effort the right agent configuration for the article's readers?
  - evidence: The decisions name the Claude Code CLI as the agent but no model. Sonnet 5.5 was chosen before any study run, as the current everyday coding model, at the effort the model guidance suggests starting from for agentic coding. Its cost fits 30 runs inside the cap.
  - options: Keep it and state it (current); repeat the pilot under a new protocol version with another model or effort, reported separately.
  - location: protocol.md / Fixed configuration
- Should the pilot be repeated with at least three runs per cell?
  - evidence: One run per cell is exploratory. The remaining cap after the pilot is recorded in the ledger.
  - options: Stop at the pilot (current); run repeats under this frozen protocol with a declared budget.
  - location: protocol.md / Pilot and optional designs
