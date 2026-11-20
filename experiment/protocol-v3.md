# Study protocol (version 3): written-down rules, unwritten rules and the gate

**Frozen 2026-11-20, before any version 3 session.** The inputs listed under
"What is frozen" are hashed in `v3/frozen-manifest.json`; the runner refuses to
start if they, or the version 2 inputs they build on, have changed
(`tools/run_study_v3.py freeze --check`). The pilot's and version 2's
protocols, manifests and records are unchanged.

## Why a third study

The pilot (`results.md`) and version 2 (`results-v2.md`) both hit a ceiling:
no structural slips in 30 single-task runs and 36 four-step sessions. In both,
the import rule was written out in the workspace instruction file. Those
studies measured what the gate costs when it has nothing to catch. They could
not show a gate catching anything.

Before designing this study, exploratory sessions looked for conditions that
do produce slips. They are **not study data**. Their per-session results are
retained in `runs/exploratory-v3-2026-11-20/probes.json` (36 sessions, arm A
only, US$2.10 of notional spend):

| Condition (guidance only, no gate) | Sessions with a slip |
| --- | --- |
| Version 2 instruction file unchanged (Haiku, S1 and S2) | 0/4 |
| The same rule in the middle of a 95-line instruction file (Haiku) | 0/2 |
| The rule moved to `docs/architecture.md`, with a pointer from `CLAUDE.md` (Haiku) | 0/2 |
| Each request asks for a small change consistent with the existing controllers (Haiku) | 0/2 |
| Each request says the application layer is frozen for a release (Haiku) | 0/2 |
| Combinations of the long file with the two request suffixes (Haiku) | 0/4 |
| Each request asks the agent to read straight from the repositories (Haiku) | 0/2 |
| The rule cut to one sentence, "keep to the layering" (Haiku and Sonnet) | 0/6 |
| **The rule removed from the instruction file** (Haiku and Sonnet, S1 and S2) | **10/12** |

What moved the slip rate was not pressure on a written rule. It was whether
the rule was written down at all. This study tests that under a frozen
protocol, and adds the arm the probes did not have: the gate.

Because the factor was chosen after looking at exploratory results, this
study's sessions are the evidence, not the probes. The probes are reported so
readers can see how the design was chosen.

## Questions

Descriptive, as in version 2. No expected outcome is fixed and no hypothesis
test is run. A ceiling or a floor in any cell is reported as such.

1. **How often does an agent add a forbidden controller-to-infrastructure
   import** when the rule is written out, hinted at in one sentence, or not
   written down at all?
2. **With the gate present, how often is a slip caught and repaired within the
   turn,** and what is left in the final snapshot?
3. **What does each route cost** in session time and reported spend?

## Design

One factor is added to version 2: **guidance**, the workspace `CLAUDE.md`.

| Guidance | `CLAUDE.md` |
| --- | --- |
| `stated` | `v3/instructions/stated.md`, byte-identical to version 2's instruction file |
| `one-line` | `v3/instructions/one-line.md`: the Architecture section replaced by "The code is layered: controllers, application, infrastructure and domain. Keep to the layering." |
| `unstated` | `v3/instructions/unstated.md`: the Architecture section removed |

The three files differ only in the Architecture section. In every level the
code, its four-commit history and the legacy reports controller (which imports
the repository directly) are the same.

- **Arms:** A (no architecture feedback while working) and B (the
  import-contract sensor on every `Stop`, blocking with its diagnostic, up to 3
  repair requests per turn). The diagnostic names the broken rule, the
  offending import and how to fix it; in the `unstated` level it is the only
  place the agent is told the rule. There is no arm C: the semantic judge is
  not the subject here.
- **Cells:** 3 guidance levels × 2 scenarios × 2 agent configurations × 2 arms
  = 24 cells.
- **Sessions:** 3 repeats per cell = **72 sessions**, 288 planned turns.
- **Order:** `run_study_v3.py plan` writes `runs/<study>/order.json` before
  any session with the frozen seed 2026112003: every cell once per repeat
  block, shuffled within the block. Sessions run four at a time.

Everything else is version 2, reused unchanged and still covered by
`v2/frozen-manifest.json`: the two four-step scenarios (S1 customer insights,
S2 fulfilment), the 23-module workspace and its history, both contracts and
the reviewed legacy exception, the acceptance and regression tests, the
evaluator, the Stop hook, the session driver (`run_study_v2.py`), the agent
configurations (`claude-sonnet-5-5` at medium effort; `claude-haiku-5-5` at the
CLI default), tools, permissions and isolation. `run_study_v3.py` only plans
the extra factor, builds each workspace from the version 2 history with the
session's guidance file as `CLAUDE.md`, and writes the guidance level into
each record.

## Measurements

As defined in `protocol-v2.md` ("Measurements"), computed by the frozen
`tools/study_v2.py`:

- **Turn slip:** the turn's first candidate contains a forbidden edge that was
  not present at the start of the turn. A violation carried over from an
  earlier turn is a `persisting_violation`, not a new slip.
- **Session slip:** at least one turn slip.
- **Caught / repaired** (arm B): the gate blocked the slip; the turn's last
  `Stop` passed.
- **Final structural violation:** the independent evaluator's result on the
  final snapshot (accepting only the reviewed legacy exception).
- **Behaviour:** each step's acceptance test and the regression check.
- **Repair effort, time and spend:** repair requests; session wall time;
  CLI-reported cost (API-equivalent, notional under a subscription login).
- **Integrity:** tampering, the settings-file check, baseline tests modified,
  `legacy_reports_modified`.

The evaluator also records the semantic judge's output on the final
controllers, as in version 2. It is not an outcome of this study.

## Reporting rule (fixed now)

- For each guidance level × arm, pooled over both scenarios and both agent
  configurations (12 sessions per cell), and broken down by agent
  configuration and by scenario: sessions with a slip, turn slips, caught and
  repaired slips, final violations, steps accepted. Every rate is `k/n`.
- Exact one-sided 95% bounds (`study_v2.upper_bound` / `lower_bound`), as in
  version 2. Session-level counts are primary; turns within a session are not
  independent.
- Median session time and total reported spend per guidance level × arm.
- No significance tests. Conclusions stay within these scenarios, agent
  configurations, this machine and these sample sizes.
- Censored, cut-short and not-started sessions are counted and listed.
  Nothing is dropped.
- `experiment/results-v3.md` is written from the retained records by
  `tools/summarize_v3.py`. The design is not changed after seeing results.

## Budget

Shared hard cap: US$100 across every study (Decisions, 2026-11-19). At the
freeze the ledger had committed US$11.49 (pilot, version 2, the exploratory
probes and a three-session harness check of this runner), leaving US$88.51.

| Item | Amount |
| --- | --- |
| Sonnet sessions: 36 × `--max-budget-usd 1.00` | US$36.00 |
| Haiku sessions: 36 × `--max-budget-usd 0.25` | US$9.00 |
| Evaluation judge allowance | US$1.00 |
| **Declared budget** | **US$46.00** |

The per-session caps are lower than version 2's because exploratory sessions
cost about US$0.30 (Sonnet) and US$0.02 (Haiku). A session that hits its cap
is recorded as `budget_exhausted`. The ledger still reserves each session's
cap plus one maximal response before it starts.

## Checks before the freeze (not study data)

- **Exploratory probes:** see the table above.
- **Harness check** (`runs/harness-check-v3-2026-11-20/`, three sessions,
  `unstated`, S1): the workspace `CLAUDE.md` matched the guidance file; arm A
  (Haiku) ran four steps with no hook events; in arm B (Haiku and Sonnet) the
  gate blocked a new repository import in step 3 and the agent removed it
  after one repair request; records carried the guidance level.

## What is frozen

`tools/run_study_v3.py` (`FROZEN_PATTERNS`): this protocol, `v3/study.json`,
the three files in `v3/instructions/` and `tools/run_study_v3.py` itself.
Version 2's frozen inputs stay frozen by its own manifest, whose hash is
recorded in `v3/frozen-manifest.json`. The summarizer
(`tools/summarize_v3.py`) presents the records with the frozen statistics and
is not frozen.

## Running it

```sh
.venv/bin/python experiment/tools/run_study_v3.py freeze --check
.venv/bin/python experiment/tools/run_study_v3.py plan --study guidance-v3-2026-11-20
.venv/bin/python experiment/tools/run_study_v3.py run --study guidance-v3-2026-11-20
.venv/bin/python experiment/tools/summarize_v3.py --study guidance-v3-2026-11-20 --out experiment/results-v3.md
```

## Limitations fixed in advance

- The factor was chosen after exploratory runs. The frozen sessions are a
  fresh sample, but the scenarios are the ones the probes used.
- "Unstated" means absent from the instruction file. The codebase still shows
  the layering, and a legacy controller that breaks it. Other codebases will
  signal their conventions more or less clearly than this one.
- Removing the Architecture section also removes its sentence about where
  business decisions belong. This study measures only the import rule.
- Two scenarios, written by the same author as the tests and the legacy code;
  three repeats per cell; two agent configurations; one machine; no seed.
- The stated-rule result says these agents followed this rule here. It is not
  a guarantee, which is what the gate adds.
- The local gate is not tamper-proof against an agent with the same
  permissions; tampering is detected, not prevented.
- Costs are API-equivalent figures reported by the CLI, not invoices.
