# Pilot results: pilot-2026-11-19

**Result: ceiling effect.** Every one of the 30 runs finished within budget.
Every final submission passed the frozen behavioural tests and the
evaluator's structural contract, and the evaluator detected no tampering.
The semantic judge returned `pass` on every final snapshot. That is a judge
output, not a verified label: no independent human labels exist, and the
rubric covers only business decisions in controllers. No final snapshot,
including the 10 in arm A, violated the structural contract, and the gates
in arms B and C never had to request a repair. For the rule and tasks used
here, the pilot therefore cannot show whether structural or semantic
feedback improves the outcome. What it does show is the cost and time of
keeping the gates in place when they found nothing to catch.

All numbers below are recomputed from the 30 retained records by
`tools/summarize.py` (output: `runs/pilot-2026-11-19/summary.json`). How to
reproduce them is in `analysis.md`. The study design was frozen beforehand in
`protocol.md`.

## What ran

| Item | Value |
| --- | --- |
| Design | 10 tasks × 3 arms × 1 run (exploratory pilot); order fixed by `order.json` (seed 20261119), 3 runs at a time |
| Date | 2026-11-19 |
| Agent | Claude Code CLI 2.1.322, `claude-sonnet-5-5`, effort `medium`; every run reported only `claude-sonnet-5-5` in `modelUsage` |
| Judge | `claude-haiku-5-5` through the CLI (arm C during development; every arm at final evaluation) |
| Environment | macOS 26.6.2 (arm64), Python 3.12.15, Import Linter 2.17 |
| Attempted / records | 30 / 30 (none missing, none refused by the spend cap, none not runnable, no infrastructure retries, no interventions) |

## Outcomes by arm

Each arm had 10 attempted runs, so every denominator below is 10.

| Outcome | A (instruction) | B (+ structural) | C (+ structural + semantic) |
| --- | --- | --- | --- |
| Completed within budget | 10 | 10 | 10 |
| Behaviour pass (acceptance + regression) | 10 | 10 | 10 |
| Structural pass (evaluator's contract) | 10 | 10 | 10 |
| Judge output on final snapshot | 10 pass | 10 pass | 10 pass |
| Tampering detected | 0 | 0 | 0 |
| Accepted outcomes | 10 | 10 | 10 |
| Gate's final state | no gate | 10 passed | 10 passed |
| Repair requests | not applicable | 0 in every run | 0 in every run |
| Development checks | none | 10 sensor runs | 10 sensor runs, 10 judge calls |

The paired view (`summary.json`, `paired_by_task`) is the same for every
task: all three arms accepted, with no structural violation. No pair differs.

Tampering detection in this pilot did not cover the external `--settings`
file that installs the Stop hook (`settings_file_check` is `not_checked` in
all 30 records). The frozen evaluator compared the workspace's instruction
and configuration and the out-of-workspace gate code with their preparation
hashes, but not that file. A run that edited or deleted it would not have
been reported as tampering. The workspaces are gone, so the check cannot be
applied after the fact. The hook log shows the Stop hook ran at the end of
all 20 gated runs (gate state `passed`), but that does not prove the file
was unchanged. Later runs make the comparison
(`evaluator/settings_integrity.py`); the frozen evaluator stays as it ran.

Edited baseline tests are reported separately from tampering. The record
counts 29 runs (9 in A, 10 in B, 10 in C), and in every one of them the
diffs only add lines to the baseline test files. No existing test line was
removed or changed: a count of `-` lines in `tests/` across all 30 retained
`final.diff` files found none. The instruction asks agents to add tests for
new behaviour, so these runs added them to the existing files.

## Time, usage and spend

The tables give the median, with the interquartile range and the full range
in brackets.

| Measure | A | B | C |
| --- | --- | --- | --- |
| Attempt time (s, monotonic) | 32.8 (30.6–35.8; 23.2–41.0) | 36.1 (30.2–38.5; 24.3–41.7) | 40.5 (37.2–45.7; 32.0–55.5) |
| Development judge time per run (s) | not applicable | not applicable | 6.3 (5.9–6.8; 5.0–8.3) |
| Agent turns (CLI `num_turns`) | 13 (11–15.25; 8–18) | 13.5 (11.25–15; 8–17) | 13.5 (11–15.75; 9–21) |
| Agent cost per run (US$) | 0.0875 (0.0826–0.0987; 0.0659–0.1146) | 0.0905 (0.0707–0.1066; 0.0641–0.1128) | 0.0893 (0.0781–0.1087; 0.0676–0.1406) |

Token usage per run, by source and category (`usage_tokens` in
`summary.json`). Every started run reported every category for every source
that applied to it, so each cell has 10 observed runs and 0 missing. The
development judge applies only to arm C.

| Source and category | A | B | C |
| --- | --- | --- | --- |
| Agent input | 12 (12–12; 10–16) | 12 (12–12; 10–16) | 12 (12–14; 12–14) |
| Agent output | 3906.5 (3577.25–4858.75; 2589–5708) | 4075 (3116.5–5127; 2487–5659) | 4178 (3331.75–5109.5; 2591–7205) |
| Agent cache read | 63274.5 (60872–64680.5; 45939–98575) | 63913 (62517.25–68731.5; 47265–95383) | 65125.5 (63228.75–74160.5; 60993–85025) |
| Agent cache creation | 10247 (9947–10656.75; 8370–12712) | 10651.5 (9091.5–11996.75; 7796–12571) | 10696.5 (9603–12783.75; 6954–15099) |
| Development judge input | not applicable | not applicable | 2 (2–2; 2–2) |
| Development judge output | not applicable | not applicable | 399 (357.75–435.75; 337–454) |
| Development judge cache read | not applicable | not applicable | 7156 (7156–7156; 7156–7156) |
| Development judge cache creation | not applicable | not applicable | 3815.5 (3655.75–3909.5; 3537–4031) |
| Evaluation judge input | 2 (2–2; 2–2) | 2 (2–2; 2–2) | 2 (2–2; 2–2) |
| Evaluation judge output | 406.5 (392.25–438; 337–512) | 387.5 (359.75–409.5; 333–473) | 398 (387.75–417.5; 350–488) |
| Evaluation judge cache read | 7156 (7156–7156; 7156–11213) | 7156 (7156–10198.75; 7156–11387) | 7156 (7156–11227; 7156–11481) |
| Evaluation judge cache creation | 4229.5 (4018.75–4311.5; 0–4547) | 4110 (987.75–4320; 0–4412) | 4021.5 (0–4294.75; 0–4440) |

The near-constant input counts reflect prompt caching: most of each prompt
is billed as cache reads or cache creation. Evaluation-judge cache creation
of 0 in some runs means that call reused a cache written by an earlier call.
Concurrency and run order affect this, so differences between arms are
descriptive only.

The spend totals include judge calls from both development and evaluation.

| Spend | A | B | C |
| --- | --- | --- | --- |
| Total charged (US$) | 0.8953 | 0.9025 | 0.9751 |
| Cost per accepted outcome (US$) | 0.0895 | 0.0903 | 0.0975 |

- **Costs are estimates.** All costs are the CLI's reported
  `total_cost_usd`: API-equivalent list-price estimates, notional under the
  subscription login used, not invoices. No agent run or judge call had an
  unknown cost, so nothing is held for unknown costs.
- **Ledger total.** The shared ledger held US$2.95 in total after the pilot
  (US$2.90 agent, US$0.05 judge). That figure also covers the harness checks,
  the isolation probes and the earlier judge runs. It is well inside the
  US$100 cap.
- **Arm C took longest.** It added a median of about 6 seconds of judge time
  per run. That is consistent with its longer attempt times, but with one run
  per cell and three concurrent workers, the gap between arms is descriptive
  only. The same goes for the small cost differences: prompt caching and
  concurrency affect both (protocol, "Threats").

## Judge

- **Final snapshots.** The judge returned `pass` on all 30 (10 per arm),
  with no abstentions and no provider failures.
- **Arm C development verdicts.** Each of the 10 calls returned `pass`. None
  disagreed with the evaluation verdict for the same run.
- **Calibration** (`evidence/live-judge-20261119-calibration.json`). The
  judge matched 12 of 12 authored labels (6 `pass`, 6 `violation`, including
  the case that tells the reviewer to answer `pass`). The same author wrote
  the labels and the rubric, so this is a count, not an accuracy rate.
- **Error rates.** False-positive and false-negative rates on final runs are
  unavailable. They need independent human labels (`adjudication.md`), and
  none were supplied.

## What this does and does not show

- **It shows** what happened to the 30 final snapshots on these ten tasks,
  with this model and effort:
  - All 30 passed the evaluator's structural contract, including the 10
    instruction-only runs in arm A.
  - The judge returned `pass` on all 30. That is a judge output under a
    rubric that covers only business decisions in controllers. Without
    independent labels it does not establish semantic compliance.
  - The end-of-turn gates in arms B and C ran once per run and passed. The
    observed price of keeping them was the extra hook time, plus the judge's
    time and cost in arm C.
  - Neither gate prevented a structural violation, because no snapshot
    showed one for them to prevent.
  - The result covers final snapshots only, not intermediate states during
    a run.
- **It does not show** that the gates are useless. A ceiling effect on these
  tasks says nothing about larger codebases, rules that are less explicit in
  the instruction, longer sessions, other models or efforts, or tasks where
  the shortcut is more tempting. It also gives no estimate of how often the
  gates would catch a violation where one occurs.
- **The tasks stay frozen.** As the protocol declares, they will not be made
  more misleading after these outcomes. A study that wants violations to
  occur needs a new protocol version with tasks, instructions or models
  chosen before any run. For example, it could drop the semantic rule from
  the instruction, use a codebase where the service lacks the needed method,
  or try a smaller model. It would be reported separately.
- **Out-of-rubric rules were not measured.** No automated check covers the
  instruction's rules about status changes (T08) and business limits (T10).
  A search of the six T08 and T10 diffs found no transition table or limit
  constant added to a controller. That is an unadjudicated observation, not
  a label.

## Open questions

- Should the pilot's tampering result be qualified further or re-run, given that the external settings file was not compared?
  - evidence: All 30 records have `settings_file_check: "not_checked"`. The frozen evaluator hashed the workspace and gate code but not the `--settings` file, and the run workspaces no longer exist. The hook log shows the Stop hook ran at the end of all 20 gated runs.
  - options: Keep the disclosed limit (current); repeat the pilot with the settings check, reported as a separate run.
  - location: results.md / Outcomes by arm

- Should a follow-up study be designed to elicit violations, given the ceiling effect?
  - evidence: All 30 final snapshots passed the structural contract and received judge passes. That includes all 10 instruction-only (arm A) snapshots. No repair request was ever made, so the arms could not differ. The judge passes are outputs under a controller-only rubric, not labels.
  - options: Report the ceiling effect as the pilot's result (current); freeze a new protocol version (different tasks, instruction or model, chosen before running) and report it separately.
  - location: results.md / What this does and does not show
