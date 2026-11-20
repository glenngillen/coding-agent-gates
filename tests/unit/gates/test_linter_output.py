from hypothesis import given
from hypothesis import strategies as st

from gates.linter_output import (
    ContractStatus,
    Edge,
    parse_contract_status,
    parse_lint_imports_output,
)

import lint_samples as s


def test_parses_a_kept_contract():
    report = parse_lint_imports_output(s.KEPT)

    assert report.analyzed_files == 9
    assert report.contracts == {s.RULE: "KEPT"}
    assert (report.kept, report.broken) == (1, 0)
    assert report.edges == {}


def test_parses_the_offending_edge_and_line():
    report = parse_lint_imports_output(s.BROKEN_ONE_EDGE)

    assert report.contracts == {s.RULE: "BROKEN"}
    assert (report.kept, report.broken) == (0, 1)
    assert report.edges == {
        s.RULE: (Edge("orders.controllers.orders", "orders.infrastructure.repository", (14,)),)
    }


def test_parses_every_edge_of_a_broken_contract():
    report = parse_lint_imports_output(s.BROKEN_TWO_EDGES)

    assert [e.importer for e in report.edges[s.RULE]] == [
        "orders.controllers",
        "orders.controllers.orders",
    ]


def test_parses_a_kept_contract_with_an_ignored_import():
    report = parse_lint_imports_output(s.KEPT_ONE_IGNORED)

    assert report.contracts == {s.RULE: "KEPT"}
    assert report.ignored == {s.RULE: 1}
    assert (report.kept, report.broken) == (1, 0)


def test_contracts_without_ignored_imports_have_no_ignored_entry():
    assert parse_lint_imports_output(s.KEPT).ignored == {}


class TestContractStatus:
    def test_plain_states(self):
        assert parse_contract_status("Rule A KEPT") == ContractStatus("Rule A", "KEPT", 0, 0)
        assert parse_contract_status("Rule A BROKEN") == ContractStatus("Rule A", "BROKEN", 0, 0)

    def test_every_suffix_import_linter_2_17_renders(self):
        # importlinter/application/rendering.py::_build_result_suffix_text
        assert parse_contract_status("R KEPT (1 ignored import)") == ContractStatus("R", "KEPT", 1, 0)
        assert parse_contract_status("R KEPT (19 ignored imports)") == ContractStatus("R", "KEPT", 19, 0)
        assert parse_contract_status("R KEPT (1 warning)") == ContractStatus("R", "KEPT", 0, 1)
        assert parse_contract_status("R BROKEN (2 ignored imports, 3 warnings)") == ContractStatus(
            "R", "BROKEN", 2, 3
        )

    def test_unrecognised_suffixes_are_not_contract_lines(self):
        for line in (
            "R KEPT (ignored)",
            "R KEPT (0 ignored imports)",
            "R KEPT (1 ignored imports, )",
            "R KEPT (1 warning, 1 ignored import)",
            "R KEPT [0.1s]",
            "R kept",
            "KEPT",
            "",
        ):
            assert parse_contract_status(line) is None, line


def test_tool_errors_produce_no_contract_results():
    for text in (
        s.SYNTAX_ERROR,
        s.MISSING_FIELD,
        s.MISSING_MODULE,
        s.NO_CONTRACTS,
        s.NOT_ON_PATH,
        s.UNPARSEABLE_CONFIG,
        "",
    ):
        report = parse_lint_imports_output(text)
        assert report.contracts == {}
        assert report.kept is None and report.broken is None


def suffix(ignored, warnings):
    """Mirror of Import Linter 2.17's ``_build_result_suffix_text``."""
    parts = []
    if ignored:
        parts.append(f"{ignored} ignored {'import' if ignored == 1 else 'imports'}")
    if warnings:
        parts.append(f"{warnings} {'warning' if warnings == 1 else 'warnings'}")
    return f" ({', '.join(parts)})" if parts else ""


def render(contracts, edges, analyzed, ignored=None):
    ignored = ignored or {}
    """Render a report in lint-imports' layout (inverse of the parser)."""
    kept = sum(1 for v in contracts.values() if v == "KEPT")
    lines = ["", "---------", "Contracts", "---------", "",
             f"Analyzed {analyzed} files, 3 dependencies.", "-" * 20, ""]
    lines += [f"{name} {state}{suffix(ignored.get(name, 0), 0)}" for name, state in contracts.items()]
    lines += ["", f"Contracts: {kept} kept, {len(contracts) - kept} broken.", ""]
    broken = [n for n, v in contracts.items() if v == "BROKEN"]
    if broken:
        lines += ["", "-" * 16, "Broken contracts", "-" * 16, ""]
        for name in broken:
            lines += [name, "-" * len(name), "", "a is not allowed to import b:", ""]
            for edge in edges.get(name, ()):
                refs = ", ".join(f"l.{n}" for n in edge.lines)
                lines += [f"-   {edge.importer} -> {edge.imported} ({refs})", ""]
    return "\n".join(lines) + "\n"


module = st.from_regex(r"[a-z][a-z_]{0,6}(\.[a-z][a-z_]{0,6}){0,3}", fullmatch=True)
contract_name = st.from_regex(r"[A-Z][A-Za-z ]{0,30}[a-z]", fullmatch=True).filter(
    lambda n: not n.endswith((" KEPT", " BROKEN")) and "  " not in n
)
edge = st.builds(
    Edge, module, module, st.lists(st.integers(1, 9999), min_size=1, max_size=3).map(tuple)
)


class TestProperties:
    @given(st.text())
    def test_never_raises_on_arbitrary_output(self, text):
        parse_lint_imports_output(text)

    @given(
        st.dictionaries(contract_name, st.sampled_from(["KEPT", "BROKEN"]), max_size=4),
        st.lists(edge, min_size=1, max_size=3),
        st.integers(1, 500),
        st.integers(0, 3),
    )
    def test_roundtrip_recovers_contracts_and_edges(self, contracts, edges, analyzed, ignore_each):
        expected_edges = {n: tuple(edges) for n, v in contracts.items() if v == "BROKEN"}
        ignored = {n: ignore_each for n in contracts if ignore_each}

        report = parse_lint_imports_output(render(contracts, expected_edges, analyzed, ignored))

        assert report.contracts == contracts
        assert report.edges == expected_edges
        assert report.kept + report.broken == len(contracts)
        assert report.analyzed_files == analyzed
        assert report.ignored == ignored

    @given(
        contract_name,
        st.sampled_from(["KEPT", "BROKEN"]),
        st.integers(0, 10_000),
        st.integers(0, 10_000),
    )
    def test_status_line_roundtrip(self, name, state, ignored, warnings):
        line = f"{name} {state}{suffix(ignored, warnings)}"

        assert parse_contract_status(line) == ContractStatus(name, state, ignored, warnings)

    @given(st.text())
    def test_status_parser_never_raises_and_counts_are_positive_when_present(self, line):
        status = parse_contract_status(line)
        if status is not None:
            assert status.state in ("KEPT", "BROKEN")
            assert status.ignored >= 0 and status.warnings >= 0
            assert line.startswith(status.name)
