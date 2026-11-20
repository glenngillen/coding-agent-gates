# CI: the architecture sensor as a pull-request check

This placement checks the committed tree of a pull request on a clean runner. It runs the same canonical sensor as the Stop hook and pre-commit. The local placements can be skipped or edited by whoever controls the machine. CI is where the check runs on a snapshot no local hook chose. It becomes a merge boundary only once a repository setting makes the check *required*.

**Verification status.** The workflow files are prepared but have **not** run on GitHub-hosted runners yet, and no repository has been configured with this check as required. Per Glenn's 2026-11-19 decision, no hosted run is planned. Instead, `integrations/simulate_ci.py` ran the `architecture-contracts` job's own steps from this workflow file and from the site's `.github/workflows/coding-agent-gates.yml` on 2026-11-19. It ran them locally, in clean copies, with Python 3.12 and the hash-pinned environment. In both workflows, the direct-import violation failed the step `Check architecture contracts (full package)` with exit 1 (sensor snapshot `3ee1fecf56ac`), and the repaired tree passed with exit 0 (`470476b02ddd`). The records are `evidence/ci-sim-*-2026-11-19.json`, described in the README's [Simulate CI locally](../README.md#simulate-ci-locally) section. They are a local simulation: nothing here claims that a hosted job has passed or failed, or that a merge was blocked. The GitHub behaviour described below comes from GitHub's documentation, retrieved 2026-11-19 (rows T14 and T15 in `drafts/sensors-and-gates/sources.md`).

## Files

| File | Use |
| --- | --- |
| `integrations/github-actions.yaml` | Reader-facing workflow. Copy it to `.github/workflows/architecture.yml` in a standalone copy of this example. |
| `.github/workflows/coding-agent-gates.yml` (site repository) | Runs this example's architecture check and its integration suite in the repository that hosts the article. |
| `tests/integration/` | The integration suite. It runs real `lint-imports`, Git and pre-commit against disposable copies, including fixtures that are expected to fail. Fixtures are asserted as failures and never applied to the checked package. |

## The workflow

```yaml
name: architecture
on:
  pull_request:
  push:
    branches: [main]
permissions:
  contents: read
jobs:
  architecture-contracts:
    name: architecture-contracts
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v6
      - uses: actions/setup-python@v5
        with:
          python-version-file: .python-version
      - name: Install pinned environment
        run: |
          python -m venv .venv
          .venv/bin/python -m pip install --require-hashes -r requirements.lock
      - name: Check architecture contracts (full package)
        run: .venv/bin/python integrations/check_architecture.py
```

Design choices:

- **Pinned interpreter and dependencies.** Python comes from `.python-version` (3.12), and every package, including transitive ones, is installed from the hash-pinned lock. Runner defaults are not used. The action versions are the major versions in GitHub's current Python guide. Pinning actions to commit SHAs is a further hardening step.
- **One stable, unique check name: `architecture-contracts`.** This is the name you mark as required. GitHub advises keeping job names unique across workflows, because a duplicate name makes it ambiguous which result satisfies the requirement.
- **No path filter, no skipping conditional.** The job runs on every pull request. Two "skipped" cases behave differently. If a workflow is skipped by a path filter, a branch filter or a skip instruction in the commit message, its checks stay **Pending**, and a pull request that requires them cannot merge. If a *job* is skipped by an `if:` conditional, or because a job it `needs` failed, it reports a skipped status, which **satisfies** a required check. So a path filter would leave pull requests stuck. A skipping conditional would let a violation through quietly. The architecture job has neither.
- **Exit status.** Any non-zero exit fails the check: violations (1) and checker errors (3, meaning the rules were not checked). The log shows the same diagnostic the other placements print.

## Making it a merge gate (configured separately)

A workflow reports a check. Whether that check *blocks merging* is a repository setting, and the YAML cannot show it:

1. Push the workflow and open a pull request, so the check has reported at least once and GitHub can offer it by name.
2. In the repository's settings, add a branch protection rule or a ruleset for the default branch that requires status checks to pass, and select `architecture-contracts`.
3. Decide whether the rule applies to administrators. By default, branch protection restrictions do not apply to people with admin permissions. Rulesets have their own bypass list.
4. Verify it: open a pull request containing the direct-import violation (`fixtures/direct_import/`), confirm that the check fails *and* that the merge button is unavailable, then push the repair and confirm both clear.

Only step 4, done in a real repository, is evidence that merging was blocked. A failing job on its own shows that the check ran and failed, not that anything was prevented.

## A failed check is not a repair loop

GitHub does not re-prompt the agent that wrote the code. A red check is a finding that waits for someone to act. To form a loop, a caller has to fetch the failure, give it to an agent, and submit the agent's next attempt, under a limit. The pseudocode below shows that shape. It is **illustrative pseudocode, not a working integration**: the function names stand for whatever your agent runner and Git hosting client provide, and none of them is a real API.

### Caller-orchestration pseudocode

```text
# ILLUSTRATIVE PSEUDOCODE. Function names are placeholders, not real APIs.
MAX_ATTEMPTS = 3

function repair_until_green(pull_request, agent):
    for attempt in 1..MAX_ATTEMPTS:
        result = wait_for_check(pull_request, name="architecture-contracts")
        if result.conclusion == "success":
            return PASSED                       # the check passed on this snapshot

        if result.conclusion not in ("failure",):
            return UNRESOLVED(result)           # cancelled, timed out, stuck pending:
                                                # not a finding the agent can fix

        diagnostic = fetch_job_log(result, step="Check architecture contracts")
        # The log holds the sensor's diagnostic: rule, offending edge and line,
        # or "ARCHITECTURE CHECK ERROR: the architecture rules were not checked".

        agent.send(
            "The architecture check failed on your pull request. Repair the code, "
            "not the contract, tests or workflow:\n" + diagnostic
        )
        new_commit = agent.wait_for_push(pull_request)
        if new_commit touches (".importlinter", ".github/workflows/", "src/gates/", "tests/"):
            return NEEDS_HUMAN_REVIEW(new_commit)  # gate files changed: do not trust
                                                    # a green check without review

    return UNRESOLVED("still failing after MAX_ATTEMPTS")   # stopping is not passing
```

The same shape works for pre-commit: run `git commit` or `pre-commit run`, capture its output, and pass it to the agent. Only the Stop hook delivers the diagnostic to the agent without such a caller, because Claude Code does that delivery itself.

## Who controls the criteria

The check is only as independent as its inputs. In a pull request, the agent can edit `.importlinter`, the gates package, the tests or the workflow file along with the code, and CI will run whatever the pull request contains. Keep those files under human review: for example, a CODEOWNERS entry with required review for `.importlinter`, `src/gates/`, `tests/` and `.github/workflows/`, and treat changes to them as a separate decision from the feature. For measuring agents, use an evaluator copy the agent cannot edit. See the experiment protocol.
