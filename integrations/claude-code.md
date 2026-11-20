# Agent hook: the architecture sensor as a Claude Code Stop hook

This placement checks the agent's *completed candidate*: when Claude finishes a turn, the hook runs the same full-package sensor that pre-commit and CI run. On a violation it keeps the conversation going and hands Claude the diagnostic as the reason. That makes it the one placement here that forms a repair loop on its own, because Claude Code delivers the finding straight to the agent and the agent takes another turn.

**Verification status.** The adapter's logic is unit-tested with an injected sensor (`tests/unit/gates/test_stop_hook.py`), and so is the entrypoint's failure handling (`tests/unit/gates/test_stop_hook_entrypoint.py`), and the entrypoint was run by hand on 2026-11-19 by piping Stop and UserPromptSubmit JSON into it, against copies of this example with the direct-import fixture applied and with it absent. That is *not* a real Claude Code conversation. The walkthrough transcript (`evidence/walkthrough-2026-11-19.txt`, §6 and §7) records the same kind of manual run: a block on the violation, then an allowed stop after the repair. This entrypoint has not yet run inside a Claude Code session. The experiment's pilot ran 20 real Claude Code 2.1.322 sessions (arms B and C) with `experiment/tools/experiment_stop_hook.py`, which wraps the same adapter. The gate never requested a repair in those runs (`experiment/results.md`). For this standalone entrypoint, no real block-and-repair cycle has been observed. The experiment harness has observed one: in the pre-freeze harness check, where the agent was told to add the forbidden import, the wrapped adapter blocked the stop, the agent removed the import and the next stop passed (one repair cycle, two sensor invocations; [`experiment/runs/harness-check-2026-11-19/H00-harness-check__B__r1/`](../experiment/runs/harness-check-2026-11-19/H00-harness-check__B__r1/), `record.json` and `hook-events.jsonl`). That is one run under the experiment wrapper, not a measurement of how often the cycle succeeds. Everything below about how Claude Code behaves comes from its [hooks reference](https://code.claude.com/docs/en/hooks), retrieved 2026-11-19, as recorded in `drafts/sensors-and-gates/sources.md` (rows T9 to T13).

## Files

| File | Role |
| --- | --- |
| `integrations/claude_stop_hook.py` | Hook entrypoint. Reads the event JSON on stdin and prints the hook's JSON decision. |
| `src/gates/stop_hook.py` | Adapter logic: repair budget, session state, translating results into the hook protocol. |
| `integrations/claude-code-settings.json` | Example `.claude/settings.json` that registers the hook for `Stop` and `UserPromptSubmit`. |
| `integrations/check_architecture.py` | The canonical sensor the hook calls (through `gates.sensor.run_sensor`). |

## Install

Start from the [README's setup](../README.md#set-up): clone `https://github.com/glenngillen/coding-agent-gates` and install the locked environment. In full, from any directory outside another repository:

```sh
git clone https://github.com/glenngillen/coding-agent-gates.git
cd coding-agent-gates
python3.12 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements.lock
mkdir -p .claude
cp integrations/claude-code-settings.json .claude/settings.json
```

Claude Code reads `.claude/settings.json` from the project root, so run these commands from the clone's root. Don't install the hook into a larger repository that merely contains the example.

Requirements: Claude Code v2.1.295 or later (for the explicit `onFailure` setting, see below), and the virtual environment at `.venv/` (the settings call `${CLAUDE_PROJECT_DIR}/.venv/bin/python`; on Windows, change it to `.venv\Scripts\python.exe`). Start Claude Code in that directory. The hook runs at the end of every turn.

Try it: ask Claude to "make the list-orders endpoint read directly from the repository". If the change adds the direct import, the turn does not end. Claude receives the diagnostic and is asked to repair it.

## What the hook does

| Event | Sensor result | Hook output | Recorded state |
| --- | --- | --- | --- |
| `Stop` | pass | Allows the stop. `systemMessage` shows the pass and the snapshot hash. | `passed`, budget reset to 0 |
| `Stop` | violation, budget left | `{"decision": "block", "reason": <diagnostic>}`: Claude continues with the diagnostic | `open`, repair count + 1 |
| `Stop` | checker error, budget left | Same as a violation, with the checker-error diagnostic ("the architecture rules were not checked") | `open`, repair count + 1 |
| `Stop` | violation or checker error, budget exhausted | Allows the stop, and `systemMessage` warns **UNRESOLVED: this candidate has not passed** | `unresolved` |
| `Stop` | (input unreadable) | Allows the stop, warns UNRESOLVED, and the check does not run | nothing (no session to key it to) |
| `Stop` | violation or checker error, state unreadable or unwritable | Allows the stop, warns UNRESOLVED and names the storage error. No repair is requested, because it could not be counted | unchanged (could not be written) |
| `UserPromptSubmit` | (sensor not run) | No output | that session's state deleted, so the new turn gets a fresh budget |

The diagnostic Claude receives is exactly what `integrations/check_architecture.py` prints: the broken rule, each offending import edge with its line, a repair hint, the snapshot hash, and an instruction to fix the code instead of editing `.importlinter`, the gates package or tests.

## Why the loop needs its own bound

Claude Code stops honouring stop-hook blocks after 8 consecutive continuations. But that count resets every time Claude calls a tool. A repair attempt almost always involves editing a file, so the platform cap would not end a loop in which the agent keeps trying and failing. The adapter therefore keeps its own per-session budget, `--max-repairs` (default 3). Three is a judgment call, not a value derived from data: enough for an agent to read a diagnostic and try a couple of repairs, few enough that a stuck loop ends quickly. Tune it for your own work. The budget resets when the check passes or the user sends a new prompt.

Ending the loop is not passing. When the budget runs out, the turn is allowed to end, because blocking forever helps nobody. But the user sees an UNRESOLVED warning, and `.claude/architecture-gate/<session-hash>.json` records `"outcome": "unresolved"` with the last status and snapshot fingerprint. A caller that orchestrates agents should read that state, or rerun the sensor itself, before treating the work as done.

`stop_hook_active` (true when Claude is already continuing because of a Stop hook) is not used to decide anything, because the adapter's own count already covers it.

## Failure handling

- **Checker errors block too.** A syntax error left in a module, a missing `lint-imports` or an invalid `.importlinter` produces a checker error. The adapter treats it like a violation, so Claude is told the rules were not checked and why, and the same budget applies. It never reaches Claude, or the user, as a pass.
- **The adapter cannot read or record its budget.** The budget only bounds the loop if each repair request is written down before it is made. If the state directory is unwritable or unreadable, the adapter does not block: it allows the stop and warns **UNRESOLVED**, naming the error. A pass is still reported as a pass. If the reset on `UserPromptSubmit` fails, the prompt goes ahead with a warning, and later stops in that turn report UNRESOLVED rather than requesting repairs.
- **The entrypoint never fails in a way Claude Code would retry.** For a Stop hook, exit code 2 is a *blocking* decision, and a crash falls to the `onFailure` policy. Both happen outside the adapter's budget. So `integrations/claude_stop_hook.py` imports the adapter lazily and turns invalid arguments, a missing `gates` package or any unexpected exception into exit 0 with an UNRESOLVED warning (`tests/unit/gates/test_stop_hook_entrypoint.py`).
- **The hook process failing outside the script.** A missing `.venv/bin/python`, a hook timeout (180 s in the example; the sensor gives up at 120 s) or a killed process never reaches the script. Claude Code treats these as non-blocking errors and lets the agent stop. The example settings say so explicitly with `"onFailure": "continue"` on both hooks. `"block"` would look stricter, but it would retry outside the adapter's budget, and Claude Code's 8-continuation cap resets on tool calls, so it would not bound a broken environment. A failed hook leaves the turn *unchecked*, not passed: no fresh result is recorded for it. Before accepting the work, a caller must get a fresh sensor result for the current snapshot. Rerun `integrations/check_architecture.py`, or rely on the pre-commit hook or the CI check, which run the sensor themselves. Do not infer a pass from the absence of a block or from an older state file.
- **Corrupt state file.** It is treated as an exhausted budget, so the result fails closed to UNRESOLVED instead of starting a fresh, possibly unbounded loop. A passing check still passes.
- **Sessions are isolated.** State is keyed by a hash of `session_id`, so one session's exhausted budget does not affect another.

## Reset

```sh
.venv/bin/python integrations/claude_stop_hook.py --reset
```

This deletes the per-session state files in `.claude/architecture-gate/` and nothing else. To disable the hook, remove the `Stop` and `UserPromptSubmit` entries from `.claude/settings.json`. Claude Code's `/hooks` menu shows what is registered.

## What this placement does not do

- **It does not run on every edit.** A Stop hook sees the candidate when Claude says it is finished. While Claude is midway through a refactor, the tree can be briefly broken: an import moved before the call site, or a module half-written. Judging each of those intermediate states would raise findings about work that is not finished. A `PostToolUse` hook could give earlier feedback after each edit, and that can shorten the path to a fix. But it arrives after the tool has already run and cannot undo the edit. It is advice about a state that may be transient, not a gate on a finished candidate. This example uses only the Stop placement.
- **It does not run when the user interrupts.** Claude Code skips Stop hooks after a user interrupt, and API errors fire `StopFailure`, whose output is ignored. An interrupted turn is *unchecked*: neither a pass nor a violation.
- **It is not a merge boundary.** The hook runs with the same permissions as the agent. The agent can edit `.claude/settings.json`, the gates package or `.importlinter`. It can also move code out of the checked `orders` package, or run Git without hooks. A Stop hook is fast feedback to a cooperative agent, not tamper-proof enforcement. Keep an independent check where the agent cannot change the rules, such as the CI job in [ci.md](ci.md) with a required status check, and keep human control of the contract and its configuration.
