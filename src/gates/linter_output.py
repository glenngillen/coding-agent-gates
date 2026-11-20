"""Parse the text report printed by ``lint-imports`` (Import Linter 2.17).

Import Linter does not document its exit codes, and the installed 2.17 exits 1
both for broken contracts and for every tool failure observed (syntax errors,
invalid configuration, missing packages). The report text is therefore the
only way to tell a violation from a checker failure. The parser is strict about
shape and returns empty results for anything it does not recognise; deciding
what an unrecognised report means is the classifier's job (``gates.sensor``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_ANALYZED = re.compile(r"^Analyzed (\d+) files, (\d+) dependencies\.$")
# A contract status line. Import Linter 2.17 appends an optional suffix
# (``_build_result_suffix_text`` in importlinter/application/rendering.py):
# ``(N ignored import[s])``, ``(N warning[s])`` or both, in that order, with
# zero counts omitted. Anything else is not recognised as a status line.
_CONTRACT_STATE = re.compile(
    r"^(?P<name>\S.*?) (?P<state>KEPT|BROKEN)"
    r"(?: \((?:"
    r"(?P<ignored>[1-9]\d*) ignored (?P<ignored_noun>imports?)"
    r"(?:, (?P<warnings_after>[1-9]\d*) (?P<warnings_after_noun>warnings?))?"
    r"|(?P<warnings>[1-9]\d*) (?P<warnings_noun>warnings?)"
    r")\))?$"
)
_SUMMARY = re.compile(r"^Contracts: (\d+) kept, (\d+) broken\.$")
_EDGE = re.compile(
    r"^-\s+(?P<importer>[\w.]+) -> (?P<imported>[\w.]+) \((?P<lines>l\.\d+(?:, l\.\d+)*)\)$"
)
_UNDERLINE = re.compile(r"^-+$")


@dataclass(frozen=True)
class Edge:
    """A direct import from ``importer`` to ``imported`` on the given source lines."""

    importer: str
    imported: str
    lines: tuple[int, ...] = ()


@dataclass(frozen=True)
class ContractStatus:
    """One contract's status line: its name, KEPT/BROKEN and the suffix counts."""

    name: str
    state: str
    ignored: int = 0
    warnings: int = 0


def _noun_agrees(count: int, noun: str, singular: str) -> bool:
    return noun == (singular if count == 1 else singular + "s")


def parse_contract_status(line: str) -> ContractStatus | None:
    """Parse ``<name> KEPT|BROKEN[ (<suffix>)]``; ``None`` if the line is anything else.

    A suffix whose noun disagrees with its count (``1 ignored imports``) is
    rejected rather than guessed at: it is not something 2.17 prints.
    """
    match = _CONTRACT_STATE.match(line)
    if not match:
        return None
    ignored = warnings = 0
    if match.group("ignored"):
        ignored = int(match.group("ignored"))
        if not _noun_agrees(ignored, match.group("ignored_noun"), "import"):
            return None
        if match.group("warnings_after"):
            warnings = int(match.group("warnings_after"))
            if not _noun_agrees(warnings, match.group("warnings_after_noun"), "warning"):
                return None
    elif match.group("warnings"):
        warnings = int(match.group("warnings"))
        if not _noun_agrees(warnings, match.group("warnings_noun"), "warning"):
            return None
    return ContractStatus(match.group("name"), match.group("state"), ignored, warnings)


@dataclass
class LintReport:
    analyzed_files: int | None = None
    contracts: dict[str, str] = field(default_factory=dict)
    # Contracts whose status line reported ignored imports, with the count.
    ignored: dict[str, int] = field(default_factory=dict)
    kept: int | None = None
    broken: int | None = None
    edges: dict[str, tuple[Edge, ...]] = field(default_factory=dict)


def parse_lint_imports_output(text: str) -> LintReport:
    report = LintReport()
    lines = [line.rstrip() for line in text.splitlines()]
    in_contract_list = False
    in_broken_section = False
    current: str | None = None
    edges: dict[str, list[Edge]] = {}

    for index, line in enumerate(lines):
        if not in_broken_section:
            if match := _ANALYZED.match(line):
                report.analyzed_files = int(match.group(1))
                in_contract_list = True
                continue
            if match := _SUMMARY.match(line):
                report.kept, report.broken = int(match.group(1)), int(match.group(2))
                in_contract_list = False
                continue
            if line == "Broken contracts" and report.kept is not None:
                in_broken_section = True
                continue
            if in_contract_list and (status := parse_contract_status(line)):
                report.contracts[status.name] = status.state
                if status.ignored:
                    report.ignored[status.name] = status.ignored
            continue

        # Broken-contracts section: a contract name underlined with dashes,
        # followed by edge lines.
        following = lines[index + 1] if index + 1 < len(lines) else ""
        if line in report.contracts and _UNDERLINE.match(following):
            current = line
            continue
        if current and (match := _EDGE.match(line)):
            refs = tuple(int(ref[2:]) for ref in match.group("lines").split(", "))
            edges.setdefault(current, []).append(
                Edge(match.group("importer"), match.group("imported"), refs)
            )

    if report.kept is None:
        # Without the summary line there is no trustworthy contract result.
        report.contracts = {}
        report.ignored = {}
        return report
    report.edges = {name: tuple(found) for name, found in edges.items()}
    return report
