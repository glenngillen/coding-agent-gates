"""Fixtures for the integration tier. Helpers live in support/integration_helpers.py."""

import pytest


@pytest.fixture
def git_env(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    return {
        "HOME": str(home),
        "GIT_CONFIG_GLOBAL": str(home / ".gitconfig"),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "Integration Test",
        "GIT_AUTHOR_EMAIL": "integration@example.invalid",
        "GIT_COMMITTER_NAME": "Integration Test",
        "GIT_COMMITTER_EMAIL": "integration@example.invalid",
        "PRE_COMMIT_HOME": str(tmp_path / "pre-commit-home"),
    }
