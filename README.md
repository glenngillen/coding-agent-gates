# Coding agent gates: companion example

Companion code for the draft article *From prompt rules to failing tests: building sensors and gates for coding agents*. It contains a small Python order service, an architecture sensor built on [Import Linter](https://import-linter.readthedocs.io/en/stable/), and the same sensor wired in three places: a Claude Code Stop hook, a pre-commit hook and a CI job. It also contains an optional, offline semantic-judge boundary for the part of the rule that imports cannot show.

The architecture rule is adapted from Dasith Wijesiriwardena's API Days 2026 talk *Don't Waste Your Backpressure*: controllers do not talk to infrastructure repositories directly. His example was a layered .NET codebase. The Python service, the Import Linter contract and all three integrations here are our adaptation.

**Status.** The order service, sensor, fixtures, Stop-hook adapter, pre-commit configuration, CI workflow and semantic boundary are implemented and unit-tested. On 2026-11-19 the walkthrough below was run end to end in a scratch copy (macOS 26.6 on arm64, Python 3.12.15, Import Linter 2.17, pre-commit 4.7.0, Git 2.56.0). Its transcript is [`evidence/walkthrough-2026-11-19.txt`](evidence/walkthrough-2026-11-19.txt). The CI job was run as a **local simulation** of the workflow's own steps, not on GitHub ([Simulate CI locally](#simulate-ci-locally)). [What has and has not been exercised](#what-has-and-has-not-been-exercised) lists every integration and how it was run. One gap: `integrations/claude_stop_hook.py` has not yet run inside a real Claude Code conversation.

## Prerequisites

Required for the deterministic walkthrough:

- Python 3.12, matching `.python-version`. Python 3.11 also runs the example, but the CI simulation insists on the pinned 3.12, and Import Linter 2.16+ no longer supports Python 3.10.
- Git, and a POSIX shell. The commands below are for macOS or Linux. On Windows, use `.venv\Scripts\python.exe` in place of `.venv/bin/python`. Windows has not been exercised.
- Network access for the one-time dependency install. After that the walkthrough needs no network and no model access.

Optional (nothing in the walkthrough needs them):

- Claude Code, to try the Stop hook in a real session ([integrations/claude-code.md](integrations/claude-code.md)).
- A logged-in `claude` CLI, for the live semantic judge and the experiment. Both spend money.
- Bash, for [`integrations/simulate_ci.py`](#simulate-ci-locally).

## Set up

Clone the example's public repository and run every command in this README from its root:

```sh
git clone https://github.com/glenngillen/coding-agent-gates.git
cd coding-agent-gates
python3.12 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements.lock
.venv/bin/lint-imports --version     # import-linter 2.17
.venv/bin/pre-commit --version       # pre-commit 4.7.0
```

pre-commit and Claude Code read their configuration from the root of the Git repository, so the clone is already laid out the way both expect. The two integration guides, [Claude Code](integrations/claude-code.md#install) and [pre-commit](integrations/pre-commit.md#install), start from this setup.

If you start from a copy of these files that isn't a Git repository (a downloaded archive, say), make it one first: `git init -b main && git add -A && git commit -m "Baseline"` in that directory. Don't install the hooks into a larger repository that merely contains the example.

The install took about 11 seconds in the recorded run. That is one machine with a warm pip cache, not a benchmark.

`requirements.lock` pins every package (including transitive dependencies) with hashes. It is generated from the `dev` extra in `pyproject.toml`:

```sh
uv pip compile pyproject.toml --extra dev --generate-hashes --python-version 3.12 --universal -o requirements.lock
```

Re-add the three explanatory header lines at the top of the file after regenerating.

## Walkthrough: violation, diagnostic, repair

Every output below is copied from [`evidence/walkthrough-2026-11-19.txt`](evidence/walkthrough-2026-11-19.txt), which records each command, its full output and its exit status. One output in the transcript is out of date: in §8, the `ignore_imports` edit produced `ARCHITECTURE CHECK ERROR ... required rule not evaluated` (exit 3) from the sensor as it was then. The transcript is left as captured; the current sensor reports that edit as a violation needing review (exit 1), recorded in [`evidence/ignored-import-2026-11-20.txt`](evidence/ignored-import-2026-11-20.txt) and explained in [Who controls the rules](#who-controls-the-rules). Your durations will differ. The sensor's snapshot ids should match if your files and tool versions are byte-identical, because the fingerprint covers the checked source, the contract and the lint-imports version.

### 1. Baseline: tests and sensor pass

```console
$ .venv/bin/python -m pytest -q tests/unit/orders
22 passed
$ .venv/bin/python integrations/check_architecture.py
ARCHITECTURE CHECK PASSED (snapshot 470476b02ddd): Controllers must not import infrastructure repositories directly
[exit 0]
```

### 2. Make a behaviour-preserving shortcut

This is the kind of change a coding agent might make: the list endpoint reads straight from the repository instead of going through the application service. The fixture holds exactly that edit (plus the matching change to `wiring.py`, which constructs the controller):

```sh
cp fixtures/direct_import/src/orders/controllers/orders.py src/orders/controllers/orders.py
cp fixtures/direct_import/src/orders/wiring.py src/orders/wiring.py
```

The code lines that changed in the controller (the fixture also replaces the docstring):

```diff
+from orders.infrastructure.repository import InMemoryOrderRepository
-    def __init__(self, service: OrderService) -> None:
+    def __init__(self, service: OrderService, repository: InMemoryOrderRepository) -> None:
+        self._repository = repository
-        orders = self._service.list_for_customer(customer_id)
+        orders = self._repository.list_for_customer(customer_id)
```

The behavioural tests still pass (`22 passed`, exit 0). They can't see the difference, and that is the point.

### 3. Read the diagnostic

```console
$ .venv/bin/python integrations/check_architecture.py
ARCHITECTURE VIOLATION
Rule broken: Controllers must not import infrastructure repositories directly
  orders.controllers.orders -> orders.infrastructure.repository (line 16)
How to fix: Controllers may decode requests, call orders.application services and map responses. Route the data access through the application service (add a service method if needed) and remove the controller's import of orders.infrastructure.
Snapshot: 3ee1fecf56ac
Repair the code; do not edit .importlinter, the gates package or tests, and do not move code out of the checked package to make this pass.

--- lint-imports output ---
...
[exit 1]
```

It names the rule, the offending edge and its line, a repair hint, and the snapshot that was checked. lint-imports' own report follows it, unedited.

### 4. The same finding at the other placements

The same sensor, run against the same snapshot (`3ee1fecf56ac`) by the other two local placements:

- **pre-commit.** After `.venv/bin/pre-commit install`, `git add -A && git commit` prints `architecture contracts (full package)....Failed` and the same diagnostic. No commit is made (exit 1).
- **Stop-hook adapter.** Piping the synthetic Stop event into the entrypoint returns the block decision Claude Code would act on. This is the adapter run by hand, not a Claude conversation:

  ```console
  $ .venv/bin/python integrations/claude_stop_hook.py --max-repairs 3 < fixtures/hook-protocol/stop.json
  {"decision": "block", "reason": "ARCHITECTURE VIOLATION\nRule broken: ...\n\n(Architecture gate: repair request 1 of 3 this turn. Fix the code and finish again; the check reruns on the whole package.)"}
  ```

  `.claude/architecture-gate/<session-hash>.json` now records `"repairs_requested": 1`, `"outcome": "open"` and the violation's full fingerprint.

CI runs the same command on a clean copy. Its evidence comes from the [local simulation](#simulate-ci-locally).

### 5. Repair and rerun

Route the read back through the service. Here that means restoring the two files:

```console
$ git restore --staged --worktree src/orders
$ .venv/bin/python integrations/check_architecture.py
ARCHITECTURE CHECK PASSED (snapshot 470476b02ddd): Controllers must not import infrastructure repositories directly
[exit 0]
```

The Stop-hook adapter now allows the stop, and its `systemMessage` reports the pass. The behavioural tests still pass. The snapshot is back to the baseline's, and the hash of the `src/orders` files is identical to the baseline's (`714d9eb3…` in the transcript).

### 6. Safe reset

Everything above happens in your clone. To return it to the commit you started from (`<baseline-commit>` is that commit; for a fresh clone, `origin/main`):

```sh
git reset --hard <baseline-commit>      # drops commits and edits made after the baseline
git clean -fd -- src                    # removes untracked files you added under src/
.venv/bin/python integrations/claude_stop_hook.py --reset   # deletes .claude/architecture-gate/ state only
.venv/bin/pre-commit uninstall          # removes the Git hook from this repository
.venv/bin/python integrations/check_architecture.py         # expect PASSED (snapshot 470476b02ddd)
```

`git reset --hard` and `git clean` discard work. Run them only in this clone, never in a repository with changes you want to keep. Deleting the clone is also a complete reset.

## Check the architecture

```sh
.venv/bin/python integrations/check_architecture.py
```

On the baseline this prints `ARCHITECTURE CHECK PASSED (snapshot …)` and exits 0. This one command is the canonical sensor, and every gate placement runs it. It always analyses the whole `orders` package, never a list of changed files. It has three distinct results:

| Exit | Result | Meaning |
| --- | --- | --- |
| 0 | pass | lint-imports analysed the package, and every required rule was kept. |
| 1 | violation | A rule was broken. The output names the rule and each offending import, with its line. |
| 3 | checker error | The rules were **not checked**: a syntax error, invalid or missing configuration, a renamed or deleted contract, a missing `lint-imports`, a timeout or unrecognised output. Never a pass. |

lint-imports itself exits 1 both for broken contracts and for every tool failure observed, so the sensor classifies by parsing the report, not by exit code (`src/gates/linter_output.py`, `src/gates/sensor.py`). `--json` prints the full result, including the snapshot fingerprint: a SHA-256 over the checked source, the configuration and the tool version. `--cache-dir DIR` reuses a result only for an identical fingerprint.

## Layout

| Path | What it is |
| --- | --- |
| `src/orders/` | The order service: the agent-editable code under the contract. `controllers/` (request decoding, response mapping), `application/` (business policy, repository access), `infrastructure/` (in-memory repository), `domain.py`, `wiring.py` (composition root). |
| `.importlinter` | The contract. Controllers must not import infrastructure directly; indirect imports are allowed. |
| `src/gates/` | The sensor, adapters and semantic boundary. Kept outside the `orders` root package, so the contract governs the application code only. |
| `integrations/` | Entry points and guides: [`check_architecture.py`](integrations/check_architecture.py), the [local CI simulation](#simulate-ci-locally) (`simulate_ci.py`, logic in `src/gates/ci_simulation.py`), [Claude Code Stop hook](integrations/claude-code.md), [pre-commit](integrations/pre-commit.md), [CI](integrations/ci.md), and the offline [`semantic_judge.py`](integrations/semantic_judge.py). |
| `.pre-commit-config.yaml` | The pre-commit hook (see the pre-commit guide). |
| `experiment/` | The A/B/C study: the frozen [protocol](experiment/protocol.md), instruction, arms, ten tasks, the independent evaluator and its acceptance tests, the semantic calibration set, the [adjudication rubric](experiment/adjudication.md), [analysis instructions](experiment/analysis.md), the run-record schema and template, the tooling under `tools/` (spend ledger, live judge, preparation, pilot runner, collection, summaries) and the retained runs under `runs/`. See [The experiment](#the-experiment). |
| `semantic/` | The semantic rubric, the verdict JSON Schema and labelled synthetic judge responses. See [semantic/rubric.md](semantic/rubric.md). |
| `evidence/` | Captured outputs: the walkthrough transcript, the CI simulation records, the live-judge runs, the task validation and the sensor/Stop-hook outputs quoted by the article's animations (`animation-captures-2026-11-19.txt`). |
| `fixtures/` | Overlays copied onto *disposable copies* of the example, never onto `src/`. Listed with expected results in `fixtures/scenarios.json`. Also holds synthetic Claude Code hook inputs. |
| `tests/unit/` | Pure unit tests (the default `pytest` run). |
| `tests/integration/` | Real lint-imports, Git and pre-commit runs against disposable copies. CI only. |

## What the contract catches, and what it cannot

The contract is an Import Linter `forbidden` contract: `orders.controllers` (and its submodules) may not import `orders.infrastructure` (and its submodules). `allow_indirect_imports = True` is set explicitly, so controller → application service → repository stays legal. The service imports the repository module, and the controller imports only the service.

The fixtures make the boundaries concrete. Each one leaves every behavioural test passing:

| Fixture | Sensor | Why |
| --- | --- | --- |
| *(baseline)* | pass | The legal indirect path. |
| `direct_import` | **violation** at `orders.controllers.orders -> orders.infrastructure.repository` | A behaviour-preserving shortcut: the list endpoint reads straight from the repository. The behavioural tests cannot see it. |
| `semantic_leakage` | pass | The controller decides discount eligibility itself. No forbidden import exists, so only a semantic rubric can flag it. |
| `runtime_reach_through` | pass | The controller reaches the repository through `self._service._repository`. Dependencies passed around as runtime objects, and dynamic imports, are invisible to an import graph. |
| `syntax_error` | **checker error** | A half-written module stops lint-imports from parsing the package. |

An import edge is a proxy for the architectural intent, not proof about runtime calls or correct business behaviour. A stricter design, such as dependency inversion where controllers may not reach infrastructure even indirectly, needs a different contract (for example, `layers` or a forbidden contract without `allow_indirect_imports`). This example deliberately does not tighten silently.

## Simulate CI locally

No hosted GitHub Actions run is planned for this example (decision recorded 2026-11-19). [`integrations/simulate_ci.py`](integrations/simulate_ci.py) runs one job's own steps, read from the workflow file, in a clean copy:

```sh
# Reader workflow, laid out as in your own repository:
.venv/bin/python integrations/simulate_ci.py --workflow integrations/github-actions.yaml \
  --job architecture-contracts --layout standalone --overlay fixtures/direct_import
# The site repository's workflow (run from the site checkout's copy of this example):
.venv/bin/python integrations/simulate_ci.py --workflow ../../.github/workflows/coding-agent-gates.yml \
  --job architecture-contracts --layout site
```

| Workflow element | What the simulation does |
| --- | --- |
| `actions/checkout` | Copies the example's tracked and unignored files from the working tree into a new directory under `.tmp/ci-sim/`: no `.venv`, caches or ignored files. `--layout site` keeps the files at their path in the site repository, which the site workflow's `working-directory` expects. The record says which commit the files came from and whether they had uncommitted changes. |
| The pull request's change | `--overlay DIR` copies a directory over the example in the copy, for example the direct-import fixture. Without it, the copy is the tree as it stands. |
| `actions/setup-python` with `python-version-file` | Checks that a local interpreter (`--python`, default `python3.12` on `PATH`) matches the file's version, then puts it first on `PATH` as `python`. A mismatch fails the step. |
| `run` steps | Executed verbatim with `bash --noprofile --norc -eo pipefail`, GitHub's default shell for Linux runners, in the step's working directory, with `CI=true`. The first failure fails the job and skips the remaining steps. The job's `timeout-minutes` bounds the run. |
| Anything else | Refused with exit 2, before anything runs: `${{ }}` expressions, `if:`, `needs`, step or job `env`, other shells, other actions. Nothing is silently skipped. |

Exit status: 0 if the job succeeded, 1 if it failed or timed out, 2 if it could not be simulated. `--output FILE` writes a JSON record: the workflow file's hash, the source commit, overlay file hashes, a hash of the copied tree, interpreter, Bash and Git versions, and, for each step, the exit status, duration, the last 80 lines of the log with the full log's SHA-256, and any sensor snapshot ids. Every record carries the label *LOCAL SIMULATION … Not a hosted run* and lists what it could not reproduce: the ubuntu-latest image, the actions' own code, the `GITHUB_*` environment and token, the trigger event, and required-check settings. The copy is deleted afterwards unless you pass `--keep-workspace`. The install step needs network access.

### Recorded runs (2026-11-19)

Run in the site worktree. The copied files were commit `cde460d` plus this change's uncommitted files, so `source_uncommitted_changes` is `true` in each record. The copied-tree hash includes `evidence/` and documentation, so it differs from run to run. The sensor's snapshot id is the stable identifier of what was checked. "Repair" means the copy without the overlay: the controller and wiring as in the baseline, which is the repair from step 5 of the walkthrough.

| Workflow and check name | Change | Conclusion | Failing step | Check exit | Sensor snapshot | Record |
| --- | --- | --- | --- | --- | --- | --- |
| `integrations/github-actions.yaml`, `architecture-contracts` | direct import | failure | Check architecture contracts (full package) | 1 | `3ee1fecf56ac` | [`ci-sim-example-violation-2026-11-19.json`](evidence/ci-sim-example-violation-2026-11-19.json) |
| same | repair | success | none | 0 | `470476b02ddd` | [`ci-sim-example-repaired-2026-11-19.json`](evidence/ci-sim-example-repaired-2026-11-19.json) |
| `.github/workflows/coding-agent-gates.yml`, `coding-agent-gates / architecture-contracts` | direct import | failure | Check architecture contracts (full package) | 1 | `3ee1fecf56ac` | [`ci-sim-site-violation-2026-11-19.json`](evidence/ci-sim-site-violation-2026-11-19.json) |
| same | repair | success | none | 0 | `470476b02ddd` | [`ci-sim-site-repaired-2026-11-19.json`](evidence/ci-sim-site-repaired-2026-11-19.json) |

In each failing run, the log tail of the failed step holds the same diagnostic as walkthrough step 3. The install step took 14.6–18.1 s and the check 1.0–1.5 s on this machine. These are not hosted-runner timings. The records show that the workflow's steps fail on the violation and pass after the repair. They do not show that a hosted check ran, or that merging was blocked; [integrations/ci.md](integrations/ci.md#making-it-a-merge-gate-configured-separately) describes what would. The site workflow's `integration` and `experiment-acceptance` jobs were not simulated here. The project's test policy keeps the integration suite in CI. The acceptance job's commands were run directly when the tasks were frozen ([`evidence/task-validation-2026-11-19.json`](evidence/task-validation-2026-11-19.json)).

## What has and has not been exercised

| Integration or command | How it was exercised | Evidence |
| --- | --- | --- |
| Sensor (`integrations/check_architecture.py`): pass, violation, repair | Real lint-imports in a scratch copy, 2026-11-19 | [transcript](evidence/walkthrough-2026-11-19.txt) §3, §5, §7 |
| Sensor: checker error | Real runs: a renamed contract (through pre-commit) and, on 2026-11-19 before ignored imports were recognised, an `ignore_imports` edit. The syntax-error fixture is asserted only in the CI-only integration suite | [pre-commit guide](integrations/pre-commit.md#observed-behaviour); transcript §8 |
| Sensor: ignored import on a required rule | Real lint-imports 2.17 in a scratch copy, 2026-11-20: violation (exit 1) naming the `ignore_imports` entry | [`evidence/ignored-import-2026-11-20.txt`](evidence/ignored-import-2026-11-20.txt) |
| pre-commit hook | Real pre-commit 4.7.0 in a scratch Git repository. The commit was rejected (exit 1), and `--no-verify` committed the violation (exit 0) | transcript §6, §8; [pre-commit guide](integrations/pre-commit.md#observed-behaviour) |
| Stop-hook adapter (`integrations/claude_stop_hook.py`) | The real entrypoint, with a synthetic Stop event piped in: block on the violation, allow on the repair | transcript §6, §7 |
| Stop hook in a real Claude Code conversation | **Not exercised** for `integrations/claude_stop_hook.py`. The pilot's 20 arm B and C runs were real Claude Code sessions with `experiment/tools/experiment_stop_hook.py`, which wraps the same adapter. The gate never requested a repair in them. One real block-and-repair cycle was observed in the pre-freeze harness check, where the agent was told to add the forbidden import: the hook blocked, the agent removed the import and the next stop passed. | [experiment/results.md](experiment/results.md); [`experiment/runs/harness-check-2026-11-19/`](experiment/runs/harness-check-2026-11-19/) |
| CI workflow (`architecture-contracts`, both workflow files) | **Local simulation** of the workflow's steps, failing and passing | `evidence/ci-sim-*.json` |
| Hosted GitHub Actions run, required check, merge blocking | **Not exercised**, and none planned | none |
| Site workflow `integration` job | **Not run** locally (CI-only by project policy) | none |
| Live semantic judge (Claude Haiku 5.5 via the Claude Code CLI) | Real calls over the fixtures and calibration set | `evidence/live-judge-*.json` |
| Windows | **Not exercised** | none |

## Live semantic judge

`src/gates/claude_cli_judge.py` is the live provider for the semantic stage: Claude Haiku 5.5 (`claude-haiku-5-5`) called through the Claude Code CLI, using whatever login the `claude` CLI already has. It needs no API key and never reads, prints or forwards a credential. Each request is one subprocess:

```sh
claude -p --model claude-haiku-5-5 --output-format json --tools "" \
  --no-session-persistence --setting-sources "" \
  --max-budget-usd <budget> --system-prompt "<rubric instructions>"
```

with `CLAUDE_CODE_MAX_OUTPUT_TOKENS=8000` and `CLAUDE_CODE_MAX_RETRIES=0` added to the child's environment (see [Spend bound](#spend-bound)).

The fixed rubric text is the system prompt; the source under review goes only on stdin, inside the JSON payload. The reply text goes back to `gates.semantic`, which validates it as strictly as any other reply. A missing CLI, a timeout, non-JSON output, `is_error: true`, a missing result or a reply from a model other than the one requested is inconclusive, never a pass. Each call records the model(s) named in `modelUsage`, the CLI's `duration_ms`, measured wall time, `usage` and `total_cost_usd`.

That `total_cost_usd` is the CLI's API-equivalent list-price estimate. Under a subscription login it is a notional figure, not an invoice. One known limit: the CLI wraps the rubric in roughly 8,000 tokens of its own framing (visible as cache tokens in `usage`), so the judge does not see only the rubric and payload.

`src/gates/anthropic_judge.py` is an alternative provider through the `anthropic` Python SDK for anyone with an API key (`ANTHROPIC_API_KEY`). It is unit-tested but was not used for the recorded run.

Every paid call, and later every agent run, goes through the shared spend ledger, `experiment/tools/spend_ledger.py`, which writes `experiment/runs/spend-ledger.json`. Before a call it reserves the call's bound (see [Spend bound](#spend-bound)) and refuses if the committed total plus that reservation would exceed the US$100 cap. Afterwards it replaces the reservation with the reported cost. If the cost is unknown (for example, the call timed out), the reservation stays as the charge. Writers take a file lock (POSIX only). The ledger itself only guarantees the cap while every actual cost stays within its reservation, so the reservation has to be a real upper bound, derived from limits the CLI cannot exceed.

### Spend bound

`--max-budget-usd` alone is not an upper bound. Claude Code checks it after each response arrives, so spend can pass it by up to one response's cost ([budget headroom](https://code.claude.com/docs/en/agent-sdk/agent-loop#budget-headroom), read 2026-11-19). The adapter can't count the CLI's own framing before launch, so it doesn't try to. It reserves the budget plus one response at the largest size the model allows:

| Part | Size | Price |
| --- | --- | --- |
| One response (the overshoot) | Claude Haiku 5.5's documented limits: a 1M-token context window and 128K output tokens ([models overview](https://platform.claude.com/docs/en/about-claude/models/overview), retrieved 2026-11-19). The CLI's framing, however large, is part of that context window. | Every input token at US$1 per million (the 1-hour cache-write rate for prompts over 100,000 tokens) and every output token at US$2.50 per million (the long-context output rate), from the pricing page retrieved 2026-11-19 (`drafts/sensors-and-gates/sources.md`, T17): **US$1.32**. The normal rates are US$0.10 and US$0.50. |
| Budget (`--max-budget-usd`) | The expected size of a normal call: rubric plus payload (refused above 200,000 UTF-8 bytes before launch; a token covers at least one byte), plus 32,000 tokens of CLI framing (about four times the roughly 8,000 observed), plus 8,000 output tokens (`CLAUDE_CODE_MAX_OUTPUT_TOKENS=8000`). | The same highest rates. |

For a request of `n` bytes the budget is `(32,000 + n) × US$1.00/M + 8,000 × US$2.50/M`, rounded up to US$0.0001, and the reservation is that budget plus US$1.32. For the committed fixtures (about 7–8 KB per request) that is about US$1.38 per call; the largest allowed request reserves US$1.572. The reservation is replaced by the reported cost as soon as a call finishes, so it only limits how close to the cap a call can start: with more than about US$98.62 committed, a fixture call is refused before launch. Because the CLI stops only once spend has passed the budget, a call that makes more than one model request is covered too.

If the CLI adds more framing than 32,000 tokens, the call is still within the reservation. The adapter records the excess (`over_budget_estimate` in the call record) and treats it as information, not a breach. `--tools ""` and `CLAUDE_CODE_MAX_RETRIES=0` keep a normal call to one model request, but the bound doesn't rely on them.

A timeout kills the CLI process and keeps the whole reservation as the charge. After every completed call the adapter compares the reported cost with the reservation. If the cost is higher, one of the remaining assumptions has failed: the documented budget behaviour, the documented model limits or the cached list prices. The cost is still recorded, the verdict is inconclusive, and `run_live_judge.py` starts no further calls and exits 6. That check can't undo the one call's spend; the assumptions are what keep the cap.

To run the judge once over the fixtures (and any calibration cases in `experiment/calibration/`):

```sh
.venv/bin/python experiment/tools/run_live_judge.py
```

The structural sensor runs first in a disposable copy for each fixture, and the judge is asked only when it passes. Results go to `evidence/live-judge-YYYYMMDD.json`. If `claude` is not on `PATH`, the script exits 5 before calling anything and writes nothing. If the ledger refuses a call, or a call breaks its spend bound, the script stops starting calls, records the remaining cases as not run and exits 6. If any started call has an unknown cost, `total_cost_usd` is `null` rather than a partial sum.

The first live run (2026-11-19, CLI 2.1.322) is in [`evidence/live-judge-20261119.json`](evidence/live-judge-20261119.json). The judge was called for the three fixtures that pass the structural check and skipped for the two that do not. It returned `pass` for `baseline`, `violation` for `semantic_leakage` (citing the discount logic in `_priced_body`, lines 59–66) and `pass` for `runtime_reach_through`. That last one matches the rubric, which asks only about business decisions; the judge's rationale still mentioned the repository reach-through. These are three single calls, not an accuracy measurement. Reported cost was US$0.0033 in total (notional), and CLI durations ranged from 2.4 to 3.9 seconds. No calibration set existed yet.

After an earlier version of the spend bound replaced the fixed US$0.10 reservation, the judge was run once more the same day to confirm that the CLI accepts the budget and environment settings: [`evidence/live-judge-20261119-bounded.json`](evidence/live-judge-20261119-bounded.json). The verdicts were the same (`pass`, `violation`, `pass`). Requests were 7,417–7,645 bytes, reservations US$0.1190–0.1194, reported costs US$0.0016 in total (notional), at most 605 output tokens and about 11,200 input tokens per call. No call broke its bound. That version priced a 32,000-token framing allowance into the reservation instead of the model's limits; the bound above replaced it the same day, after a review showed the allowance was assumed rather than enforced. The two runs' ledger entries keep the reservations of their time (US$0.10, then US$0.1190–0.1194); no call has run under the current bound yet.

## The experiment

`experiment/` holds a frozen A/B/C study that asks whether architectural
feedback helps a coding agent. All three arms use the same end-of-turn
placement:

- **A:** instruction only.
- **B:** A plus the structural sensor through a Stop hook.
- **C:** B plus the live semantic judge.

Read [`experiment/protocol.md`](experiment/protocol.md) first, then:

| File | What it is |
| --- | --- |
| `experiment/instruction.md`, `arms.json`, `tasks/*.json` | The frozen instruction, the arm configuration and the ten task requests. Hashed in `frozen-manifest.json`. |
| `experiment/evaluator/` | The independent final evaluator: frozen acceptance tests, its own contract copy, reference implementations and negative variants (never copied into an agent's workspace). |
| `experiment/calibration/`, `adjudication.md` | Twelve labelled controller examples and the rubric a person would follow to label final snapshots. |
| `experiment/run-record.schema.json`, `run-record.template.json` | The record each run produces, and an explicitly unpopulated template. |
| `experiment/tools/` | `freeze.py`, `validate_tasks.py`, `prepare_run.py`, `experiment_stop_hook.py`, `run_pilot.py`, `run_record.py`, `summarize.py`, plus the spend ledger and the live-judge run. |
| `experiment/runs/` | The spend ledger, the harness checks and the retained pilot runs (redacted transcripts, hook logs, final diffs, evaluations, records, summary). |
| [`experiment/analysis.md`](experiment/analysis.md), [`experiment/results.md`](experiment/results.md) | How to recompute the numbers, and what the pilot found. |

Check and reproduce:

```sh
.venv/bin/python experiment/tools/freeze.py --check
.venv/bin/python experiment/tools/validate_tasks.py
.venv/bin/python experiment/tools/summarize.py --pilot pilot-2026-11-19
```

Running the pilot again (`prepare_run.py plan` with a new pilot name, then
`run_pilot.py --pilot NAME`) spends real money. It needs a logged-in `claude`
CLI and is charged to the shared ledger.

**Pilot result (2026-11-19, 30 runs).** This was a ceiling effect:

- All 30 runs were accepted. Every final snapshot passed the structural
  contract, including the 10 instruction-only runs in arm A.
- The semantic judge returned `pass` on every final snapshot. These are judge
  outputs under a rubric that covers only business decisions in controllers,
  not verified labels.
- Tamper detection in the pilot did not compare the external `--settings`
  file that installs the hook. Later runs do.
- The gates never requested a repair.
- Median attempt time was 32.8 s (A), 36.1 s (B) and 40.5 s (C).
- Total reported cost was US$0.90 (A), US$0.90 (B) and US$0.98 (C). These are
  notional API-equivalent figures.

The pilot cannot show whether the feedback helps on these tasks. See
[`experiment/results.md`](experiment/results.md) for the denominators and
limits.

**Follow-up study (version 2, 2026-11-20, 36 sessions).** A second protocol,
[`experiment/protocol-v2.md`](experiment/protocol-v2.md), was frozen before
any session (`v2/frozen-manifest.json`). It added context pressure: four
dependent steps per session in a larger codebase with Git history, the rule
stated only in the workspace `CLAUDE.md`, a legacy controller that already
breaks the rule (accepted as a reviewed exception), `claude-sonnet-5-5` and
`claude-haiku-5-5`, and 3 repeats per cell. Its own fixtures, tooling and
contracts live under `experiment/v2/` and `experiment/tools/*_v2.py`.

- No first candidate added a forbidden import: 0 of 36 sessions, 0 of 144
  turns. Per arm and agent that is 0/6 sessions (one-sided 95% upper bound
  39%); per arm pooled, 0/12 (22%). Another ceiling effect.
- Every session completed and passed all four acceptance tests; no final
  snapshot had a structural violation and no tampering was flagged.
- Arm C's judge returned `violation` for 3 of 51 judged candidates, each
  citing the pre-existing `reports.py`. In those three sessions the agent then
  moved the legacy report logic behind a service, removing the legacy
  repository import. The judge had passed the same unchanged file in fixture
  validation, but the request then held different surrounding controllers, so
  this is not evidence of different verdicts on an identical request.
- Total reported spend: US$5.84 agent, US$0.19 judge (notional).

See [`experiment/results-v2.md`](experiment/results-v2.md), generated by
`experiment/tools/summarize_v2.py` from the retained records.

The "Running it" commands in the frozen protocol name the retained study,
`follow-up-v2-2026-11-20`. Its plan and records are committed, so the planner
refuses that name and the runner would skip every session. To recompute the
retained results without spending anything:

```sh
mkdir -p .tmp
.venv/bin/python experiment/tools/summarize_v2.py --study follow-up-v2-2026-11-20 \
    --out .tmp/results-v2-recompute.md
diff .tmp/results-v2-recompute.md experiment/results-v2.md
```

To run fresh sessions (this spends money against the shared ledger), use one
new study name for planning, running and the summary, and write the summary
inside that study's directory:

```sh
STUDY=follow-up-v2-rerun-1
.venv/bin/python experiment/tools/freeze.py --v2 --check
.venv/bin/python experiment/tools/prepare_v2.py plan --study "$STUDY"
.venv/bin/python experiment/tools/run_study_v2.py --study "$STUDY"
.venv/bin/python experiment/tools/summarize_v2.py --study "$STUDY" \
    --out "experiment/runs/$STUDY/results.md" --json "experiment/runs/$STUDY/summary.json"
```

[`experiment/reproducing-v2.md`](experiment/reproducing-v2.md) covers resuming
an interrupted run, the spend cap, and running from a standalone copy.


### Version 3: written-down rules, unwritten rules and the gate

Versions 1 and 2 never saw a slip, because the rule was always written in the
workspace `CLAUDE.md`. [`experiment/protocol-v3.md`](experiment/protocol-v3.md)
adds one factor: how much of the rule the instruction file states (the full
rule, a one-line hint, or nothing), with and without the structural gate. It
reuses the frozen version 2 runner, hook, scenarios and evaluator unchanged;
[`experiment/tools/run_study_v3.py`](experiment/tools/run_study_v3.py) only
adds the guidance factor.

Results, from 72 sessions: [`experiment/results-v3.md`](experiment/results-v3.md).
With the rule stated or hinted at, 0 of 48 sessions slipped. With nothing
written down, 9 of 12 ungated sessions slipped and kept the violation; with the
gate, 10 of 12 slipped, all 10 were caught and repaired after one request, and
no final snapshot violated the rule.

The factor was chosen after exploratory sessions, which are not study data.
Their per-session results, including later probes for long contexts,
compaction, oversized and contradictory instruction files, are in
[`experiment/runs/exploratory-v3-2026-11-20/probes.json`](experiment/runs/exploratory-v3-2026-11-20/probes.json).

```sh
.venv/bin/python experiment/tools/run_study_v3.py freeze --check
mkdir -p .tmp
.venv/bin/python experiment/tools/summarize_v3.py --study guidance-v3-2026-11-20 \
    --out .tmp/results-v3-recompute.md
diff .tmp/results-v3-recompute.md experiment/results-v3.md && echo identical
```


### Version 4: a lean prompt with a gate, or a large handbook?

[`experiment/protocol-v4.md`](experiment/protocol-v4.md) reuses version 3's
runner with two guidance levels: version 3's one-line hint, and a generated
instruction file of about 162,000 characters
([`experiment/v4/instructions/handbook.md`](experiment/v4/instructions/handbook.md),
made by [`experiment/tools/make_handbook.py`](experiment/tools/make_handbook.py))
that contains version 2's full Architecture section.

Results, from 48 sessions: [`experiment/results-v4.md`](experiment/results-v4.md).
No structural slips with either prompt. Mean reported cost per session was
US$0.30 (lean) against US$0.63 (handbook) for Sonnet, and US$0.02 against
US$0.07 for Haiku. The evaluation judge flagged the final controllers in 5 of
24 lean-prompt sessions and 0 of 24 handbook sessions.

```sh
.venv/bin/python experiment/tools/run_study_v4.py freeze --check
mkdir -p .tmp
.venv/bin/python experiment/tools/summarize_v4.py --study handbook-v4-2026-11-20 \
    --out .tmp/results-v4-recompute.md
diff .tmp/results-v4-recompute.md experiment/results-v4.md && echo identical
```

### Version 5: the same rule on an older model

[`experiment/protocol-v5.md`](experiment/protocol-v5.md) reuses version 3's
runner on `claude-haiku-4-5` and `claude-haiku-5-5` with four conditions: the
rule stated, a one-line hint, the rule stated while every request asks for the
shortcut, and the rule stated while a nested `CLAUDE.md` contradicts it.

Results, from 92 of 96 planned sessions (the shared spend cap refused the last
four, recorded as `not_started_cap`): [`experiment/results-v5.md`](experiment/results-v5.md).
Haiku 5.5 added no forbidden import in 46 sessions. Haiku 4.5 added none with
the rule stated and nothing pushing against it (0 of 11), and added one in 5
of 6 (hint), 6 of 6 (shortcut) and 6 of 6 (nested file) sessions without the
gate. With the gate, all 15 slips were caught and repaired after one request
and no session ended with a violation; 4 of the 12 gated sessions under
pressure then failed at least one acceptance test.

```sh
.venv/bin/python experiment/tools/run_study_v5.py freeze --check
mkdir -p .tmp
.venv/bin/python experiment/tools/summarize_v5.py --study models-v5-2026-11-20 \
    --out .tmp/results-v5-recompute.md
diff .tmp/results-v5-recompute.md experiment/results-v5.md && echo identical
```

## Unit tests

```sh
.venv/bin/python -m pytest
```

pytest collects only `tests/unit` (see `[tool.pytest.ini_options]` in `pyproject.toml`). Unit tests are pure: they mock the lint-imports process and the model provider, and they use temporary directories (under the gitignored `.tmp/`) for state. Property tests use Hypothesis.

From the site repository root, `npm test` runs both the site's Vitest suite and this pytest suite. It uses this directory's `.venv` and fails, with setup instructions, if the environment or pytest is missing. A file filter such as `npm test -- test_sensor` runs only the suite that contains a matching file, and a filter that matches nothing is an error.

## Integration tests (CI only)

```sh
.venv/bin/python -m pytest tests/integration -m integration
```

These copy the example to a temporary directory, apply fixtures, and run the real sensor, the behavioural tests, the Stop-hook entrypoint and pre-commit inside a throwaway Git repository. They never install hooks into the repository that holds this example. In the site repository they run in `.github/workflows/coding-agent-gates.yml`. Per the project's testing policy they are not part of the local unit run, and they have not yet run on a hosted runner.

## Who controls the rules

What "passing" means is decided by the contract (`.importlinter`), the sensor (`src/gates/`), the tests, and the hook and CI configuration (`.pre-commit-config.yaml`, `.claude/settings.json`, the workflow file). Whoever can edit those files controls the gate. That should be the people who own the architecture, reviewing changes to them as decisions in their own right, not the agent doing the feature work.

An agent with the same file and Git permissions as you can get past every local placement. The [transcript](evidence/walkthrough-2026-11-19.txt), §8, shows three ways, in a scratch repository:

- **Skip the hook.** `git commit --no-verify` committed the direct-import violation (exit 0). The sensor still reports it on the committed tree (exit 1), so the skipped hook made no difference to the finding, only to whether anything checked it. `SKIP=architecture-contracts`, or simply not installing the hook, has the same effect.
- **Move the code out of the checked package.** A one-line module outside `orders` (`src/order_shortcuts/`) re-exports the repository, and the controller imports it from there. The sensor reports **PASSED** (snapshot `b2c0e7a728d3`, exit 0), and the behavioural tests pass, yet the controller still reads straight from the repository. The contract governs only `orders`, so the import graph never sees that edge.
- **Edit the contract.** Appending an `ignore_imports` line for the offending edge to `.importlinter` makes lint-imports itself report the contract `KEPT (1 ignored import)` and exit 0. When the walkthrough was recorded (2026-11-19), the sensor didn't recognise that status line and reported a checker error, `required rule not evaluated` (exit 3): it failed closed, but with a misleading reason. The sensor now parses the suffix and treats any ignored import on a required rule as a **violation that needs review** (exit 1). The diagnostic names each `ignore_imports` entry from the contract file it ran (lint-imports reports only a count) and asks for the contract to be restored or the exception reviewed by a person ([`evidence/ignored-import-2026-11-20.txt`](evidence/ignored-import-2026-11-20.txt)). That closes this particular edit, not the general hole: the agent could equally delete the contract's required rule from `src/gates/rules.py`, edit the sensor, the hook settings or the workflow.

So none of the local placements is tamper-proof, and the Stop hook and pre-commit should not be described as enforcement. They give fast feedback to a cooperative agent. The acceptance boundary has to be a check the agent cannot change, run on a snapshot it did not choose: a required CI check over the committed tree, with human review (for example CODEOWNERS) of `.importlinter`, `src/gates/`, `tests/`, `.pre-commit-config.yaml` and `.github/workflows/`. When measuring agents, use an evaluator copy outside the agent's workspace, as the [experiment](experiment/protocol.md) does. A changed snapshot id with no change to the application code is a signal worth checking: the fingerprint covers the contract too. Each integration guide discusses its own bypasses.

## Troubleshooting

| Symptom | Likely cause and fix |
| --- | --- |
| `ARCHITECTURE CHECK ERROR: the architecture rules were not checked` (exit 3) | Not a pass. Read the `Reason:` line. Common causes: a syntax error in a module, running without the example's `.venv` (so `lint-imports` is missing), or an edited or renamed contract in `.importlinter`. Fix the cause and rerun. |
| `pip install --require-hashes` fails | Use Python 3.12 (`python3.12 -m venv .venv`). The lock was compiled for 3.12, so other versions or unusual platforms may need a wheel that isn't in it. A partial install leaves a broken `.venv`: delete the scratch copy's `.venv` and run the install again. |
| The behavioural tests pass but the sensor fails | That is expected for the direct-import shortcut. The tests check behaviour. The sensor checks the import structure. |
| pre-commit: `Executable .venv/bin/python not found` | The hook runs the example's own environment. Create `.venv` in the repository where the hook is installed. |
| pre-commit runs in the wrong repository | `git rev-parse --show-toplevel` shows where the hook is installed. Run `.venv/bin/pre-commit uninstall` there, and use a standalone copy of the example. |
| The Stop-hook adapter allows the stop with **UNRESOLVED** right away | The session's repair budget was used up, or its state file is unreadable. Run `.venv/bin/python integrations/claude_stop_hook.py --reset`. |
| `simulate_ci.py` exits 2 with `CI SIMULATION NOT RUN` | No `python3.12` on `PATH` (pass `--python`), the directory is not a Git checkout (run `git init` and commit first), or the workflow uses syntax the simulation refuses. The message names it. |
| `simulate_ci.py` fails at `Install pinned environment` | No network access, or a pip error shown in the record's log tail. |

## Open questions

