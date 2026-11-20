"""Sensor result model, its JSON form and the diagnostic text adapters deliver.

Three outcomes, never collapsed:

- ``pass``: lint-imports ran over the full package and every required rule was KEPT.
- ``violation``: a required rule was BROKEN and the offending edges are known.
- ``checker_error``: the check did not produce a trustworthy answer (missing
  tool, invalid configuration, parse failure, timeout, unrecognised output).
  This is *not checked*, and adapters must not report it as success.
"""

from __future__ import annotations

import enum
import json
from dataclasses import dataclass
from typing import Any

from gates.linter_output import Edge
from gates.rules import REPAIR_HINTS


class Status(str, enum.Enum):
    PASS = "pass"
    VIOLATION = "violation"
    CHECKER_ERROR = "checker_error"

    @property
    def exit_code(self) -> int:
        # 3 rather than 2 for checker errors: exit 2 already means "usage error"
        # to argparse and "block" to Claude Code hooks.
        return {"pass": 0, "violation": 1, "checker_error": 3}[self.value]


VIOLATION_KINDS = ("broken", "ignored")


@dataclass(frozen=True)
class Violation:
    """A finding against a required rule.

    ``kind`` is ``"broken"`` for an import lint-imports reported as breaking the
    contract, and ``"ignored"`` for an import the contract's ``ignore_imports``
    hides from it. lint-imports reports the latter as KEPT; this sensor treats
    it as a violation that needs review, because an agent can add the entry.
    """

    rule: str
    edge: Edge
    kind: str = "broken"


@dataclass(frozen=True)
class SensorResult:
    SCHEMA = "coding-agent-gates/sensor-result/v1"

    status: Status
    rules: dict[str, str]
    violations: tuple[Violation, ...]
    error: str | None
    fingerprint: str | None
    tool_version: str | None
    exit_code: int | None
    raw_output: str

    @classmethod
    def checker_error(
        cls,
        error: str,
        *,
        fingerprint: str | None,
        tool_version: str | None = None,
        exit_code: int | None = None,
        raw_output: str = "",
    ) -> SensorResult:
        return cls(Status.CHECKER_ERROR, {}, (), error, fingerprint, tool_version,
                   exit_code, raw_output)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.SCHEMA,
            "status": self.status.value,
            "rules": dict(self.rules),
            "violations": [
                {
                    "rule": v.rule,
                    "importer": v.edge.importer,
                    "imported": v.edge.imported,
                    "lines": list(v.edge.lines),
                    "kind": v.kind,
                }
                for v in self.violations
            ],
            "error": self.error,
            "fingerprint": self.fingerprint,
            "tool_version": self.tool_version,
            "exit_code": self.exit_code,
            "raw_output": self.raw_output,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)

    @classmethod
    def from_dict(cls, data: Any) -> SensorResult:
        """Strictly validate a stored result; raise ``ValueError`` on any mismatch."""
        try:
            if not isinstance(data, dict) or data.get("schema") != cls.SCHEMA:
                raise ValueError("not a sensor result")
            rules = data["rules"]
            if not isinstance(rules, dict) or not all(
                isinstance(k, str) and v in ("KEPT", "BROKEN") for k, v in rules.items()
            ):
                raise ValueError("invalid rules")
            violations = []
            for item in data["violations"]:
                lines = item["lines"]
                kind = item.get("kind", "broken")  # absent in results stored before kinds
                if not (
                    kind in VIOLATION_KINDS
                    and
                    isinstance(item["rule"], str)
                    and isinstance(item["importer"], str)
                    and isinstance(item["imported"], str)
                    and isinstance(lines, list)
                    and all(type(n) is int for n in lines)
                ):
                    raise ValueError("invalid violation")
                violations.append(
                    Violation(item["rule"], Edge(item["importer"], item["imported"], tuple(lines)),
                              kind)
                )
            optional_str = ("error", "fingerprint", "tool_version")
            if not all(data[k] is None or isinstance(data[k], str) for k in optional_str):
                raise ValueError("invalid optional field")
            exit_code = data["exit_code"]
            if exit_code is not None and type(exit_code) is not int:
                raise ValueError("invalid exit code")
            if not isinstance(data["raw_output"], str):
                raise ValueError("invalid raw output")
            return cls(
                status=Status(data["status"]),
                rules=dict(rules),
                violations=tuple(violations),
                error=data["error"],
                fingerprint=data["fingerprint"],
                tool_version=data["tool_version"],
                exit_code=exit_code,
                raw_output=data["raw_output"],
            )
        except (KeyError, TypeError) as exc:
            raise ValueError(f"malformed sensor result: {exc!r}") from exc

    @classmethod
    def from_json(cls, text: str) -> SensorResult:
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, RecursionError) as exc:
            raise ValueError(f"invalid JSON: {exc}") from exc
        return cls.from_dict(data)


def _snapshot(result: SensorResult) -> str:
    return result.fingerprint[:12] if result.fingerprint else "unknown"


def format_diagnostic(result: SensorResult) -> str:
    """Human- and agent-readable text. The first line always states the outcome."""
    if result.status is Status.PASS:
        rules = ", ".join(sorted(result.rules)) or "(none)"
        return f"ARCHITECTURE CHECK PASSED (snapshot {_snapshot(result)}): {rules}"

    if result.status is Status.CHECKER_ERROR:
        return "\n".join(
            [
                "ARCHITECTURE CHECK ERROR: the architecture rules were not checked.",
                f"Reason: {result.error or 'unknown'}",
                f"Snapshot: {_snapshot(result)}",
                "This is not a pass. Fix the cause above (for example a syntax error "
                "or a missing tool) and run the check again.",
            ]
        )

    lines = ["ARCHITECTURE VIOLATION"]
    broken: dict[str, list[Edge]] = {}
    ignored: dict[str, list[Edge]] = {}
    for violation in result.violations:
        target = ignored if violation.kind == "ignored" else broken
        target.setdefault(violation.rule, []).append(violation.edge)
    for rule, edges in broken.items():
        lines.append(f"Rule broken: {rule}")
        for edge in edges:
            where = ", ".join(str(n) for n in edge.lines)
            suffix = f" (line {where})" if where else ""
            lines.append(f"  {edge.importer} -> {edge.imported}{suffix}")
        if hint := REPAIR_HINTS.get(rule):
            lines.append(f"How to fix: {hint}")
    for rule, edges in ignored.items():
        lines.append(f"Rule has ignored imports (needs review): {rule}")
        for edge in edges:
            lines.append(f"  ignore_imports: {edge.importer} -> {edge.imported}")
        lines.append(
            "How to fix: an ignore_imports entry hides these imports from the rule, so "
            "lint-imports reports it KEPT. A required rule may not carry exceptions the "
            "gate has not reviewed: restore .importlinter to its committed contract and "
            "repair the import. If the exception is intended, a person must review it."
        )
    lines.append(f"Snapshot: {_snapshot(result)}")
    lines.append(
        "Repair the code; do not edit .importlinter, the gates package or tests, "
        "and do not move code out of the checked package to make this pass."
    )
    return "\n".join(lines)
