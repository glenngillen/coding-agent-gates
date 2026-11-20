"""Sensor classification and runner tests. The lint-imports process is mocked."""

import subprocess
from pathlib import Path

import lint_samples as s
import pytest
from hypothesis import given
from hypothesis import strategies as st

from gates import sensor
from gates.cache import ResultCache
from gates.linter_output import parse_lint_imports_output
from gates.result import SensorResult, Status, format_diagnostic
from gates.sensor import (
    ProcessOutput,
    classify,
    fingerprint,
    ignored_imports_from_config,
    run_sensor,
)

REQUIRED = (s.RULE,)


def classify_text(text, exit_code, required=REQUIRED, ignored_entries=None):
    return classify(parse_lint_imports_output(text), exit_code, required, raw_output=text,
                    ignored_entries=ignored_entries)


SHORTCUT = "orders.controllers.orders -> orders.infrastructure.repository"
CONFIG_WITH_IGNORE = f"""[importlinter]
root_packages =
    orders

[importlinter:contract:controllers-not-repositories]
name = {s.RULE}
type = forbidden
source_modules =
    orders.controllers
forbidden_modules =
    orders.infrastructure
allow_indirect_imports = True
ignore_imports =
    {SHORTCUT}
"""


class TestClassify:
    def test_kept_with_exit_zero_is_a_pass(self):
        result = classify_text(s.KEPT, 0)

        assert result.status is Status.PASS
        assert result.violations == ()

    def test_broken_with_exit_one_is_a_violation_with_edges(self):
        result = classify_text(s.BROKEN_ONE_EDGE, 1)

        assert result.status is Status.VIOLATION
        assert [(v.rule, v.edge.importer, v.edge.imported) for v in result.violations] == [
            (s.RULE, "orders.controllers.orders", "orders.infrastructure.repository")
        ]

    @pytest.mark.parametrize(
        "text",
        [s.SYNTAX_ERROR, s.MISSING_FIELD, s.MISSING_MODULE, s.NO_CONTRACTS, s.NOT_ON_PATH,
         s.UNPARSEABLE_CONFIG, ""],
    )
    def test_tool_failures_are_checker_errors_even_though_lint_imports_exits_one(self, text):
        result = classify_text(text, 1)

        assert result.status is Status.CHECKER_ERROR
        assert result.error

    def test_exit_zero_without_a_summary_is_not_a_pass(self):
        assert classify_text("", 0).status is Status.CHECKER_ERROR

    def test_a_missing_required_rule_is_not_a_pass(self):
        result = classify_text(s.KEPT, 0, required=(s.RULE, "Some other rule"))

        assert result.status is Status.CHECKER_ERROR
        assert "Some other rule" in result.error

    def test_kept_output_with_a_failing_exit_is_a_checker_error(self):
        assert classify_text(s.KEPT, 1).status is Status.CHECKER_ERROR

    def test_broken_output_with_exit_zero_is_a_checker_error(self):
        assert classify_text(s.BROKEN_ONE_EDGE, 0).status is Status.CHECKER_ERROR

    def test_broken_without_parseable_edges_is_a_checker_error(self):
        text = s.BROKEN_ONE_EDGE.replace(
            "-   orders.controllers.orders -> orders.infrastructure.repository (l.14)", ""
        )

        assert classify_text(text, 1).status is Status.CHECKER_ERROR


class TestIgnoredImports:
    """lint-imports reports a contract with an ``ignore_imports`` entry as KEPT and exits 0.

    On a required rule that is a hidden exception, so it is a violation that
    needs review, never a pass and never "required rule not evaluated".
    """

    def test_an_ignored_import_on_a_required_rule_is_a_violation_naming_the_import(self):
        result = classify_text(s.KEPT_ONE_IGNORED, 0, ignored_entries={s.RULE: (SHORTCUT,)})

        assert result.status is Status.VIOLATION
        assert result.status.exit_code == 1
        assert [(v.rule, v.kind, v.edge.importer, v.edge.imported) for v in result.violations] == [
            (s.RULE, "ignored", "orders.controllers.orders", "orders.infrastructure.repository")
        ]

    def test_the_diagnostic_names_the_ignored_import_and_asks_for_review(self):
        text = format_diagnostic(
            classify_text(s.KEPT_ONE_IGNORED, 0, ignored_entries={s.RULE: (SHORTCUT,)})
        )

        assert text.startswith("ARCHITECTURE VIOLATION")
        assert "ignored" in text and "review" in text
        assert SHORTCUT in text
        assert "not evaluated" not in text

    def test_an_ignored_import_whose_entry_cannot_be_read_is_still_a_violation(self):
        result = classify_text(s.KEPT_ONE_IGNORED, 0, ignored_entries={})

        assert result.status is Status.VIOLATION
        assert result.violations[0].kind == "ignored"
        assert "1 ignored import" in format_diagnostic(result)

    def test_ignored_imports_on_a_rule_that_is_not_required_do_not_fail_the_check(self):
        text = s.KEPT_ONE_IGNORED.replace(
            f"{s.RULE} KEPT (1 ignored import)", f"{s.RULE} KEPT\nAdvisory rule KEPT (1 ignored import)"
        ).replace("1 kept", "2 kept")
        result = classify_text(text, 0)

        assert result.status is Status.PASS

    def test_reads_ignore_entries_by_contract_name(self):
        assert ignored_imports_from_config(CONFIG_WITH_IGNORE) == {s.RULE: (SHORTCUT,)}

    def test_config_without_ignores_or_unparseable_config_gives_nothing(self):
        assert ignored_imports_from_config(CONFIG_WITH_IGNORE.split("ignore_imports")[0]) == {}
        assert ignored_imports_from_config("not an ini file") == {}

    def test_run_sensor_names_entries_from_the_contract_it_ran(self, tmp_path):
        root = make_example(tmp_path)
        (root / ".importlinter").write_text(CONFIG_WITH_IGNORE)

        result = run_sensor(root, runner=FakeRunner(ProcessOutput(0, s.KEPT_ONE_IGNORED, "")),
                            locate_tool=lambda: "x", tool_version=lambda: "2.17",
                            required_rules=REQUIRED)

        assert result.status is Status.VIOLATION
        assert result.violations[0].edge.importer == "orders.controllers.orders"


def make_example(root: Path) -> Path:
    (root / "src" / "orders" / "controllers").mkdir(parents=True)
    (root / "src" / "orders" / "__init__.py").write_text("")
    (root / "src" / "orders" / "controllers" / "__init__.py").write_text("")
    (root / ".importlinter").write_text("[importlinter]\n")
    return root


class FakeRunner:
    def __init__(self, output=None, exc=None):
        self.output, self.exc, self.calls = output, exc, []

    def __call__(self, argv, *, cwd, env, timeout):
        self.calls.append({"argv": argv, "cwd": cwd, "env": env, "timeout": timeout})
        if self.exc:
            raise self.exc
        return self.output


class TestRunSensor:
    def run(self, tmp_path, runner, tool="/venv/bin/lint-imports", cache=None):
        root = make_example(tmp_path)
        return run_sensor(
            root, runner=runner, locate_tool=lambda: tool, tool_version=lambda: "2.17",
            required_rules=REQUIRED, cache=cache,
        )

    def test_invokes_lint_imports_on_the_full_package_without_its_cache(self, tmp_path):
        runner = FakeRunner(ProcessOutput(0, s.KEPT, ""))

        result = self.run(tmp_path, runner)

        assert result.status is Status.PASS
        call = runner.calls[0]
        assert call["argv"][0] == "/venv/bin/lint-imports"
        assert "--no-cache" in call["argv"]
        assert call["argv"][-1] == str(tmp_path / ".importlinter")
        assert call["cwd"] == tmp_path
        assert call["env"]["PYTHONPATH"].split(sensor.os.pathsep)[0] == str(tmp_path / "src")
        assert not any(a.endswith(".py") for a in call["argv"])  # never file-scoped

    def test_records_fingerprint_and_tool_version(self, tmp_path):
        result = self.run(tmp_path, FakeRunner(ProcessOutput(0, s.KEPT, "")))

        assert result.tool_version == "2.17"
        assert result.fingerprint == fingerprint(tmp_path, tool_version="2.17")

    def test_missing_tool_is_a_checker_error_and_never_runs(self, tmp_path):
        runner = FakeRunner(ProcessOutput(0, s.KEPT, ""))

        result = self.run(tmp_path, runner, tool=None)

        assert result.status is Status.CHECKER_ERROR
        assert "lint-imports" in result.error
        assert runner.calls == []

    def test_timeout_is_a_checker_error(self, tmp_path):
        runner = FakeRunner(exc=subprocess.TimeoutExpired(["lint-imports"], 1))

        assert self.run(tmp_path, runner).status is Status.CHECKER_ERROR

    def test_os_error_starting_the_tool_is_a_checker_error(self, tmp_path):
        runner = FakeRunner(exc=PermissionError("denied"))

        assert self.run(tmp_path, runner).status is Status.CHECKER_ERROR

    def test_missing_config_is_a_checker_error(self, tmp_path):
        root = make_example(tmp_path)
        (root / ".importlinter").unlink()
        runner = FakeRunner(ProcessOutput(0, s.KEPT, ""))

        result = run_sensor(root, runner=runner, locate_tool=lambda: "x",
                            tool_version=lambda: "2.17", required_rules=REQUIRED)

        assert result.status is Status.CHECKER_ERROR
        assert runner.calls == []

    def test_an_external_contract_is_used_instead_of_the_copy_s_own(self, tmp_path):
        root = make_example(tmp_path / "copy")
        (root / ".importlinter").write_text("[importlinter]\n# edited inside the copy\n")
        external = tmp_path / "frozen" / ".importlinter"
        external.parent.mkdir()
        external.write_text("[importlinter]\n")
        runner = FakeRunner(ProcessOutput(0, s.KEPT, ""))

        result = run_sensor(root, runner=runner, locate_tool=lambda: "x",
                            tool_version=lambda: "2.17", required_rules=REQUIRED, config=external)

        assert result.status is Status.PASS
        assert runner.calls[0]["argv"][-1] == str(external)
        assert result.fingerprint == fingerprint(root, tool_version="2.17", config=external)
        assert result.fingerprint != fingerprint(root, tool_version="2.17")

    def test_a_missing_external_contract_is_a_checker_error(self, tmp_path):
        root = make_example(tmp_path)
        runner = FakeRunner(ProcessOutput(0, s.KEPT, ""))

        result = run_sensor(root, runner=runner, locate_tool=lambda: "x", tool_version=lambda: "2.17",
                            required_rules=REQUIRED, config=tmp_path / "absent.ini")

        assert result.status is Status.CHECKER_ERROR
        assert runner.calls == []

    def test_stderr_is_considered_when_classifying(self, tmp_path):
        result = self.run(tmp_path, FakeRunner(ProcessOutput(1, "", s.SYNTAX_ERROR)))

        assert result.status is Status.CHECKER_ERROR
        assert "Syntax error" in result.raw_output

    def test_cached_result_is_reused_only_for_an_identical_snapshot(self, tmp_path):
        cache = ResultCache(tmp_path / "cache")
        runner = FakeRunner(ProcessOutput(1, s.BROKEN_ONE_EDGE, ""))
        root = make_example(tmp_path / "example")
        kwargs = dict(runner=runner, locate_tool=lambda: "x", tool_version=lambda: "2.17",
                      required_rules=REQUIRED, cache=cache)

        first = run_sensor(root, **kwargs)
        second = run_sensor(root, **kwargs)
        assert len(runner.calls) == 1
        assert second == first

        # Any change to the checked inputs invalidates the cached result.
        (root / "src" / "orders" / "controllers" / "orders.py").write_text("x = 1\n")
        runner.output = ProcessOutput(0, s.KEPT, "")
        third = run_sensor(root, **kwargs)
        assert len(runner.calls) == 2
        assert third.status is Status.PASS

    def test_checker_errors_are_never_cached(self, tmp_path):
        cache = ResultCache(tmp_path / "cache")
        runner = FakeRunner(ProcessOutput(1, s.SYNTAX_ERROR, ""))
        root = make_example(tmp_path / "example")
        kwargs = dict(runner=runner, locate_tool=lambda: "x", tool_version=lambda: "2.17",
                      required_rules=REQUIRED, cache=cache)

        run_sensor(root, **kwargs)
        run_sensor(root, **kwargs)

        assert len(runner.calls) == 2


class TestFingerprint:
    def test_changes_when_package_source_changes(self, tmp_path):
        root = make_example(tmp_path)
        before = fingerprint(root, tool_version="2.17")
        (root / "src" / "orders" / "controllers" / "__init__.py").write_text("import os\n")
        assert fingerprint(root, tool_version="2.17") != before

    def test_changes_when_config_changes(self, tmp_path):
        root = make_example(tmp_path)
        before = fingerprint(root, tool_version="2.17")
        (root / ".importlinter").write_text("[importlinter]\n# edited\n")
        assert fingerprint(root, tool_version="2.17") != before

    def test_changes_when_a_module_is_added_renamed_or_deleted(self, tmp_path):
        root = make_example(tmp_path)
        base = fingerprint(root, tool_version="2.17")
        new = root / "src" / "orders" / "extra.py"
        new.write_text("")
        added = fingerprint(root, tool_version="2.17")
        new.rename(root / "src" / "orders" / "renamed.py")
        renamed = fingerprint(root, tool_version="2.17")
        (root / "src" / "orders" / "renamed.py").unlink()
        assert len({base, added, renamed}) == 3
        assert fingerprint(root, tool_version="2.17") == base

    def test_changes_with_tool_version(self, tmp_path):
        root = make_example(tmp_path)
        assert fingerprint(root, tool_version="2.17") != fingerprint(root, tool_version="2.18")

    def test_ignores_bytecode_caches(self, tmp_path):
        root = make_example(tmp_path)
        before = fingerprint(root, tool_version="2.17")
        cache_dir = root / "src" / "orders" / "__pycache__"
        cache_dir.mkdir()
        (cache_dir / "x.cpython-312.pyc").write_bytes(b"\0")
        assert fingerprint(root, tool_version="2.17") == before


class TestCache:
    def test_corrupt_entries_are_misses(self, tmp_path):
        cache = ResultCache(tmp_path)
        key = "ab" * 32
        (tmp_path / f"{key}.json").write_text("{not json")

        assert cache.get(key) is None

    def test_entry_for_a_different_fingerprint_is_a_miss(self, tmp_path):
        cache = ResultCache(tmp_path)
        result = classify_text(s.KEPT, 0)
        stored = SensorResult(**{**result.__dict__, "fingerprint": "cd" * 32})
        cache.put(stored)
        # Copy the stored entry under a different key: the embedded fingerprint
        # no longer matches, so it must not be served.
        (tmp_path / f"{'ef' * 32}.json").write_text((tmp_path / f"{'cd' * 32}.json").read_text())

        assert cache.get("ef" * 32) is None
        assert cache.get("cd" * 32) == stored

    def test_rejects_keys_that_are_not_hex_digests(self, tmp_path):
        cache = ResultCache(tmp_path)
        assert cache.get("../../etc/passwd") is None


class TestProperties:
    @given(st.text(), st.integers(-5, 300))
    def test_classify_never_raises_and_only_passes_on_exit_zero(self, text, exit_code):
        result = classify_text(text, exit_code)
        if result.status is Status.PASS:
            assert exit_code == 0
        if result.status is Status.VIOLATION:
            assert exit_code in (0, 1) and result.violations

    @given(st.text())
    def test_reading_ignore_entries_never_raises(self, text):
        entries = ignored_imports_from_config(text)
        assert all(isinstance(v, tuple) for v in entries.values())
