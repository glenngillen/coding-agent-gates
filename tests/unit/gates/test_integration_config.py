"""Static checks of the committed integration configuration and fixture layout.

These read committed files only; nothing is executed. Real runs of the same
configuration live in tests/integration (CI only).
"""

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
CANONICAL = "integrations/check_architecture.py"


def load_yaml(rel):
    return yaml.safe_load((ROOT / rel).read_text())


class TestPreCommit:
    def hook(self):
        config = load_yaml(".pre-commit-config.yaml")
        (repo,) = config["repos"]
        assert repo["repo"] == "local"
        (hook,) = repo["hooks"]
        return hook

    def test_runs_the_canonical_sensor_from_the_example_venv(self):
        assert self.hook()["entry"] == f".venv/bin/python {CANONICAL}"

    def test_checks_the_full_package_on_every_commit(self):
        hook = self.hook()
        assert hook["pass_filenames"] is False
        assert hook["always_run"] is True
        for narrowing in ("files", "exclude", "types", "types_or", "stages"):
            assert narrowing not in hook

    def test_uses_the_current_language_name(self):
        # pre-commit 4.4.0 renamed `system` to `unsupported` (pinned: 4.7.0).
        assert self.hook()["language"] == "unsupported"
        assert "pre-commit==4.7.0" in (ROOT / "requirements.lock").read_text().replace(" \\", "")


class TestClaudeCodeSettings:
    def settings(self):
        return json.loads((ROOT / "integrations/claude-code-settings.json").read_text())["hooks"]

    def test_stop_hook_runs_the_adapter_in_exec_form_without_retrying_failures(self):
        (group,) = self.settings()["Stop"]
        assert "matcher" not in group  # Stop has no matcher
        (hook,) = group["hooks"]
        assert hook["type"] == "command"
        assert hook["command"] == "${CLAUDE_PROJECT_DIR}/.venv/bin/python"
        assert hook["args"][0] == "${CLAUDE_PROJECT_DIR}/integrations/claude_stop_hook.py"
        # A process failure (missing .venv, timeout) happens outside the adapter's
        # repair budget, and Claude Code's own cap resets on tool calls, so
        # "block" could retry without bound. The adapter reports its own failures
        # as UNRESOLVED; anything else ends the turn unchecked, not passed.
        assert hook["onFailure"] == "continue"
        assert "--max-repairs" in hook["args"]

    def test_stop_hook_timeout_exceeds_the_sensor_timeout(self):
        from gates.sensor import TIMEOUT_SECONDS

        (group,) = self.settings()["Stop"]
        (hook,) = group["hooks"]
        assert hook["timeout"] > TIMEOUT_SECONDS

    def test_prompt_hook_resets_without_blocking_the_user(self):
        (group,) = self.settings()["UserPromptSubmit"]
        (hook,) = group["hooks"]
        assert hook["args"] == ["${CLAUDE_PROJECT_DIR}/integrations/claude_stop_hook.py"]
        assert hook["onFailure"] == "continue"

    def test_hook_protocol_fixtures_are_valid_events(self):
        events = {}
        for path in sorted((ROOT / "fixtures/hook-protocol").glob("*.json")):
            data = json.loads(path.read_text())
            if "hook_event_name" in data:
                assert isinstance(data["session_id"], str) and data["session_id"]
                events[path.name] = data["hook_event_name"]
        assert events == {
            "stop.json": "Stop",
            "stop-continuing.json": "Stop",
            "user-prompt-submit.json": "UserPromptSubmit",
        }


class TestGitHubActions:
    def workflow(self):
        return load_yaml("integrations/github-actions.yaml")

    def triggers(self):
        workflow = self.workflow()
        return workflow.get("on", workflow.get(True))  # PyYAML reads `on` as True

    def test_runs_on_every_pull_request_without_path_filters(self):
        triggers = self.triggers()
        assert "pull_request" in triggers
        for event in triggers.values():
            if isinstance(event, dict):
                assert not {"paths", "paths-ignore", "branches-ignore"} & set(event)
        assert triggers["pull_request"] in (None, {})

    def test_has_one_stable_named_job_without_skip_conditions(self):
        jobs = self.workflow()["jobs"]
        assert list(jobs) == ["architecture-contracts"]
        job = jobs["architecture-contracts"]
        assert job["name"] == "architecture-contracts"
        assert "if" not in job and "needs" not in job and "continue-on-error" not in job
        for step in job["steps"]:
            assert "if" not in step and "continue-on-error" not in step

    def test_pins_python_and_dependencies_and_runs_the_canonical_sensor(self):
        steps = self.workflow()["jobs"]["architecture-contracts"]["steps"]
        setup = next(s for s in steps if s.get("uses", "").startswith("actions/setup-python@"))
        assert setup["with"]["python-version-file"] == ".python-version"
        scripts = "\n".join(s.get("run", "") for s in steps)
        assert "--require-hashes -r requirements.lock" in scripts
        assert f".venv/bin/python {CANONICAL}" in scripts


class TestFixtures:
    def scenarios(self):
        return json.loads((ROOT / "fixtures/scenarios.json").read_text())["scenarios"]

    def test_fixtures_live_outside_the_checked_package(self):
        for path in (ROOT / "fixtures").rglob("*.py"):
            assert ROOT / "src" not in path.parents

    def test_every_overlay_exists_and_only_targets_the_order_service(self):
        for scenario in self.scenarios():
            if scenario["overlay"] is None:
                continue
            overlay = ROOT / scenario["overlay"]
            files = [p for p in overlay.rglob("*") if p.is_file()]
            assert files, scenario["id"]
            for path in files:
                rel = path.relative_to(overlay)
                assert rel.parts[:2] == ("src", "orders"), rel

    def test_scenarios_cover_pass_violation_and_checker_error(self):
        statuses = {s["expected_status"] for s in self.scenarios()}
        assert statuses == {"pass", "violation", "checker_error"}
        for scenario in self.scenarios():
            if scenario["expected_status"] == "violation":
                assert scenario["expected_edges"]
            else:
                assert scenario["expected_edges"] == []

    def test_every_overlay_directory_is_listed(self):
        listed = {s["overlay"] for s in self.scenarios() if s["overlay"]}
        on_disk = {
            f"fixtures/{p.name}" for p in (ROOT / "fixtures").iterdir()
            if p.is_dir() and (p / "src").is_dir()
        }
        assert listed == on_disk
