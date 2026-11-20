# Pre-commit: the architecture sensor as a commit gate

This placement checks what is about to be committed. `git commit` runs [pre-commit](https://pre-commit.com/), which runs the same full-package sensor as the Stop hook and CI. If the sensor exits non-zero, Git aborts the commit.

**Verification status.** The configuration was exercised by hand on 2026-11-19 in a throwaway Git repository: a copy of this example under the gitignored `.tmp/`, with pre-commit 4.7.0, Git 2.56.0 and Python 3.12.15 on macOS. The scenarios and results are listed in [Observed behaviour](#observed-behaviour). The same scenarios are automated in `tests/integration/test_precommit.py`, which runs in CI only and has not yet run on a hosted runner. Formal captured outputs belong in `evidence/` with the reader walkthrough.

## Configuration

`.pre-commit-config.yaml` at the example root:

```yaml
repos:
  - repo: local
    hooks:
      - id: architecture-contracts
        name: architecture contracts (full package)
        entry: .venv/bin/python integrations/check_architecture.py
        language: unsupported
        pass_filenames: false
        always_run: true
```

Why each line:

- **`repo: local` and the `.venv` entry.** The sensor runs `lint-imports` from the example's own virtual environment, so it uses the version pinned in `requirements.lock` and analyses the package as installed there. This is the setup Import Linter documents for pre-commit. On Windows, use `.venv\Scripts\python.exe`.
- **`language: unsupported`.** Import Linter's documentation says `language: system`. pre-commit 4.4.0 renamed `system` to `unsupported` and keeps `system` only as a deprecated alias. pre-commit 4.7.0 is pinned here, so the example uses the current name. Both mean "run this command as-is, with no environment managed by pre-commit".
- **`pass_filenames: false`.** The rule is about the import graph of the whole package. A changed controller can break the rule through an import of an unchanged module, and a changed `.importlinter` changes every result. So the sensor always analyses the full package, and it never receives a list of files.
- **`always_run: true`.** Runs the hook even when no staged file matches. Without it, a commit that only deletes files reports `(no files to check) Skipped` (observed). Commits that only change `.importlinter` are checked either way, because the hook matches every file type by default.

## Install

Start from the [README's setup](../README.md#set-up): clone `https://github.com/glenngillen/coding-agent-gates` and install the locked environment. In full, from any directory outside another repository:

```sh
git clone https://github.com/glenngillen/coding-agent-gates.git
cd coding-agent-gates
python3.12 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements.lock
.venv/bin/pre-commit install
```

pre-commit reads `.pre-commit-config.yaml` from the root of the Git repository, and `pre-commit install` writes into that repository's `.git/hooks/`, so run these commands from the clone's root. Don't install the hook into a larger repository that merely contains the example.

Run it without committing: `.venv/bin/pre-commit run --all-files`. Uninstall: `.venv/bin/pre-commit uninstall`.

## Which snapshot is checked

pre-commit documents that it runs hooks on the *staged* contents of files, by temporarily stashing unstaged changes while the hooks run. For this hook, that means:

| Working tree state | What the sensor sees | Result observed |
| --- | --- | --- |
| Violation staged | the violation | commit rejected |
| Violation staged, repair present but unstaged | the staged violation (the unstaged repair is set aside, then restored) | commit rejected |
| Harmless change staged, violation present but unstaged | the staged files without the violation | commit allowed; the unstaged violation stays in the working tree |
| Harmless change staged, **untracked** violating module in the package | the untracked module too | commit rejected |
| Only `.importlinter` changed (contract renamed) | the changed configuration | commit rejected with a checker error ("required rule not evaluated") |
| Only a module deleted | the package without that module | hook ran (`Passed`); without `always_run`, it was skipped |

Two consequences:

1. **Partial staging is handled for tracked files.** The commit is judged on what it will contain, not on what happens to be in the working tree.
2. **Untracked files leak into the snapshot.** pre-commit sets aside unstaged changes to tracked files, but in this run an untracked module under `src/orders/` stayed in place, and the sensor analyses the whole package directory. An untracked file can therefore make the hook fail on a commit that does not contain it. A commit that relies on a file you forgot to add can also pass here and fail in CI. CI checks out exactly the committed tree, so treat CI as the authoritative snapshot.

## Failure modes and bypasses

- **Checker errors reject the commit.** The sensor exits 3 when the rules were not checked: a syntax error, a missing `lint-imports`, or invalid or renamed contracts. pre-commit treats any non-zero exit as a failure, so these block the commit and print "the rules were not checked", never a pass. A missing `.venv` fails as well, because pre-commit cannot start the entry.
- **Bypasses exist and are ordinary Git features.** `git commit --no-verify` skips the Git hook entirely, and was observed to commit a violation. `SKIP=architecture-contracts git commit ...` skips this hook by id. Commits made where the hook is not installed (a fresh clone, or another machine) are not checked at all. An agent that runs Git with the same permissions as you can use any of these. It can also edit `.pre-commit-config.yaml` or `.importlinter`.
- **Recovery.** Read the diagnostic, fix the staged code, `git add` the fix and commit again. If the failure was a checker error, fix its cause first. If a hook run is interrupted, pre-commit restores the stashed unstaged changes. Check `git status` before retrying.

## Who makes the next attempt

A rejected commit is a failed command, not a repair loop. Git does not notify an agent or schedule another attempt. Something has to read the hook's output and act on it:

- **A person** reads the failure in the terminal and fixes the code.
- **An agent that ran `git commit` itself** sees the failed command's output in its tool result. Whether it then repairs the code, retries with `--no-verify` or gives up depends on the agent and its instructions. The hook cannot control that.
- **An orchestrating script** can run the commit (or `pre-commit run`), capture the output, pass it to the agent as the next instruction, and cap the number of attempts. See the labelled pseudocode in [ci.md](ci.md#caller-orchestration-pseudocode). The same shape applies here.

Because the hook can be bypassed, it is a convenience boundary for cooperative workflows. Keep the independent check in CI, with a required status check, if the rule must hold for what gets merged.

## Observed behaviour

Manual run, 2026-11-19, in a copy of this example under `.tmp/` initialised with `git init`. The copy's `.venv` was a symlink to the example's environment. Hooks were installed with `.venv/bin/pre-commit install` in that copy only. The direct-import violation is `fixtures/direct_import/`.

| Scenario | Hook line | `git commit` exit |
| --- | --- | --- |
| Violation staged | `Failed` (`ARCHITECTURE VIOLATION`, edge `orders.controllers.orders -> orders.infrastructure.repository (line 16)`) | 1 |
| Repair staged (restoring the committed baseline) | `Passed` | 1: Git then found nothing to commit, because the repair matched `HEAD` |
| Staged violation, unstaged repair | `Failed`; unstaged repair restored afterwards | 1 |
| Staged harmless change, unstaged violation | `Passed`; unstaged violation still present | 0 |
| Staged harmless change, untracked violating module | `Failed` | 1 |
| `.importlinter` contract renamed | `Failed` (`ARCHITECTURE CHECK ERROR`) | 1 |
| Deletion-only commit, `always_run: true` | `Passed` | 0 |
| Deletion-only commit, `always_run: false` | `(no files to check) Skipped` | 0 |
| Violation committed with `--no-verify` | (hook not run) | 0 |
