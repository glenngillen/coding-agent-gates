"""Real pre-commit runs in a throwaway Git repository made from a copy of the example."""

import shutil

import pytest
from integration_helpers import EXAMPLE, make_copy, run

pytestmark = pytest.mark.integration

CONTROLLER = "src/orders/controllers/orders.py"
WIRING = "src/orders/wiring.py"


@pytest.fixture
def repo(tmp_path, git_env):
    root = make_copy(tmp_path)
    git = lambda *a: run(["git", *a], root, env=git_env)  # noqa: E731
    assert git("init", "-q").returncode == 0
    assert git("add", "-A").returncode == 0
    assert git("commit", "-qm", "baseline", "--no-verify").returncode == 0
    install = run([root / ".venv" / "bin" / "pre-commit", "install"], root, env=git_env)
    assert install.returncode == 0, install.stderr
    # Installed into the copy's own repository only.
    assert (root / ".git" / "hooks" / "pre-commit").exists()
    return root, git


def overlay(root, *rels, source="fixtures/direct_import"):
    for rel in rels:
        shutil.copy(EXAMPLE / source / rel, root / rel)


def restore(root, *rels):
    for rel in rels:
        shutil.copy(EXAMPLE / rel, root / rel)


def commit(git, message):
    proc = git("commit", "-m", message)
    return proc.returncode, proc.stdout + proc.stderr


def test_staged_violation_is_rejected_and_repair_is_accepted(repo):
    root, git = repo
    overlay(root, CONTROLLER, WIRING)
    git("add", "-A")

    code, out = commit(git, "violation")
    assert code != 0
    assert "ARCHITECTURE VIOLATION" in out

    restore(root, CONTROLLER, WIRING)
    (root / "src/orders/domain.py").write_text((root / "src/orders/domain.py").read_text() + "\n")
    git("add", "-A")
    code, out = commit(git, "repaired")
    assert code == 0, out


def test_partial_staging_checks_the_staged_violation_not_the_unstaged_repair(repo):
    root, git = repo
    overlay(root, CONTROLLER, WIRING)
    git("add", CONTROLLER, WIRING)
    restore(root, CONTROLLER, WIRING)  # unstaged repair

    code, out = commit(git, "staged violation")

    assert code != 0 and "ARCHITECTURE VIOLATION" in out
    # pre-commit restores the unstaged change afterwards.
    assert (root / CONTROLLER).read_text() == (EXAMPLE / CONTROLLER).read_text()


def test_partial_staging_ignores_an_unstaged_violation(repo):
    root, git = repo
    domain = root / "src/orders/domain.py"
    domain.write_text(domain.read_text() + "\n# staged change\n")
    git("add", "src/orders/domain.py")
    overlay(root, CONTROLLER, WIRING)  # unstaged violation

    code, out = commit(git, "harmless")

    assert code == 0, out
    assert "orders.infrastructure.repository" in (root / CONTROLLER).read_text()


def test_untracked_files_are_part_of_the_checked_snapshot(repo):
    root, git = repo
    (root / "src/orders/controllers/admin.py").write_text(
        "from orders.infrastructure.repository import InMemoryOrderRepository\n")
    domain = root / "src/orders/domain.py"
    domain.write_text(domain.read_text() + "\n# staged change\n")
    git("add", "src/orders/domain.py")

    code, out = commit(git, "untracked module present")

    assert code != 0 and "ARCHITECTURE VIOLATION" in out


def test_configuration_only_change_is_checked(repo):
    root, git = repo
    config = root / ".importlinter"
    config.write_text(config.read_text().replace(
        "name = Controllers must not import infrastructure repositories directly", "name = Renamed"))
    git("add", ".importlinter")

    code, out = commit(git, "rename contract")

    assert code != 0 and "ARCHITECTURE CHECK ERROR" in out


def test_deletion_only_commit_still_runs_the_hook(repo):
    root, git = repo
    git("rm", "-q", WIRING)

    code, out = commit(git, "delete wiring")

    assert "architecture contracts (full package)" in out
    assert "Skipped" not in out
    assert code == 0, out


def test_no_verify_bypasses_the_hook(repo):
    root, git = repo
    overlay(root, CONTROLLER, WIRING)
    git("add", "-A")

    proc = git("commit", "-qm", "bypass", "--no-verify")

    assert proc.returncode == 0  # a local hook is not an enforcement boundary
