import json

import pytest
from hypothesis import given
from hypothesis import strategies as st

from gates.linter_output import Edge
from gates.result import SensorResult, Status, Violation, format_diagnostic

RULE = "Controllers must not import infrastructure repositories directly"


def violation_result():
    return SensorResult(
        status=Status.VIOLATION,
        rules={RULE: "BROKEN"},
        violations=(
            Violation(RULE, Edge("orders.controllers.orders", "orders.infrastructure.repository", (14,))),
        ),
        error=None,
        fingerprint="ab" * 32,
        tool_version="2.17",
        exit_code=1,
        raw_output="...",
    )


def test_exit_codes_distinguish_the_three_outcomes():
    assert Status.PASS.exit_code == 0
    assert Status.VIOLATION.exit_code == 1
    assert Status.CHECKER_ERROR.exit_code == 3


def test_violation_diagnostic_names_the_rule_edge_and_line():
    text = format_diagnostic(violation_result())

    assert text.startswith("ARCHITECTURE VIOLATION")
    assert RULE in text
    assert "orders.controllers.orders -> orders.infrastructure.repository (line 14)" in text
    # The repair hint points at the code, not at the gate.
    assert "do not edit .importlinter" in text


def test_checker_error_diagnostic_never_reads_as_a_pass():
    result = SensorResult.checker_error("lint-imports not found", fingerprint=None)

    text = format_diagnostic(result)

    assert text.startswith("ARCHITECTURE CHECK ERROR")
    assert "not checked" in text
    assert "lint-imports not found" in text


def test_pass_diagnostic_is_short_and_names_the_snapshot():
    result = SensorResult(
        status=Status.PASS, rules={RULE: "KEPT"}, violations=(), error=None,
        fingerprint="cd" * 32, tool_version="2.17", exit_code=0, raw_output="",
    )

    text = format_diagnostic(result)

    assert text.startswith("ARCHITECTURE CHECK PASSED")
    assert "cdcdcdcdcdcd" in text


def test_stored_results_without_a_violation_kind_read_as_broken():
    data = violation_result().to_dict()
    for item in data["violations"]:
        del item["kind"]

    assert SensorResult.from_dict(data).violations[0].kind == "broken"


def test_unknown_violation_kind_is_rejected():
    data = violation_result().to_dict()
    data["violations"][0]["kind"] = "waived"

    with pytest.raises(ValueError):
        SensorResult.from_dict(data)


@pytest.mark.parametrize(
    "payload",
    [
        "not json",
        "[]",
        json.dumps({"schema": "something-else"}),
        json.dumps({"schema": SensorResult.SCHEMA, "status": "maybe"}),
    ],
)
def test_from_json_rejects_malformed_payloads(payload):
    with pytest.raises(ValueError):
        SensorResult.from_json(payload)


names = st.text(min_size=1, max_size=40)
modules = st.from_regex(r"[a-z]{1,5}(\.[a-z]{1,5}){0,3}", fullmatch=True)
edges = st.builds(Edge, modules, modules, st.lists(st.integers(1, 10**6), max_size=3).map(tuple))
results = st.builds(
    SensorResult,
    status=st.sampled_from(list(Status)),
    rules=st.dictionaries(names, st.sampled_from(["KEPT", "BROKEN"]), max_size=3),
    violations=st.lists(
        st.builds(Violation, names, edges, st.sampled_from(["broken", "ignored"])), max_size=3
    ).map(tuple),
    error=st.none() | st.text(max_size=80),
    fingerprint=st.none() | st.from_regex(r"[0-9a-f]{64}", fullmatch=True),
    tool_version=st.none() | st.text(max_size=10),
    exit_code=st.none() | st.integers(-255, 255),
    raw_output=st.text(max_size=200),
)


class TestProperties:
    @given(results)
    def test_json_roundtrip(self, result):
        assert SensorResult.from_json(result.to_json()) == result

    @given(st.text())
    def test_from_json_raises_only_value_error(self, text):
        try:
            SensorResult.from_json(text)
        except ValueError:
            pass

    @given(results)
    def test_diagnostic_status_matches_result_status(self, result):
        text = format_diagnostic(result)
        prefix = {
            Status.PASS: "ARCHITECTURE CHECK PASSED",
            Status.VIOLATION: "ARCHITECTURE VIOLATION",
            Status.CHECKER_ERROR: "ARCHITECTURE CHECK ERROR",
        }[result.status]
        assert text.startswith(prefix)
