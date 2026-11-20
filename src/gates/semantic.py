"""Optional semantic judge boundary for rule ``business-decision-in-controller``.

The structural sensor answers "does a controller import a repository?". It
cannot answer "does a controller decide business policy?". This module
prepares that narrower question for a judge (a person or a model), calls an
injected provider, and turns its reply into one of four outcomes:

- ``pass`` / ``violation``: a schema-valid verdict with checkable evidence.
  A pass can still be wrong; it is a judgment, not proof.
- ``inconclusive``: the judge abstained, or the reply was invalid, or the
  provider timed out, was unavailable or failed. Never a pass.
- ``not_evaluated``: the structural check had not passed, so the judge was not
  asked. Structural failures are repaired first.

``Provider`` is any callable taking a ``JudgeRequest`` and returning the raw
reply text. The live adapter (Claude Haiku 5.5 through the Claude Code CLI) is
``gates.claude_cli_judge.ClaudeCliJudgeProvider``; an API-key alternative is
``gates.anthropic_judge.AnthropicJudgeProvider``; tests inject fakes. Source text is
placed only in the JSON data payload; the instructions are fixed text from the
committed rubric and never change with the code under review.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from gates.result import SensorResult, Status

RULE_ID = "business-decision-in-controller"
EXAMPLE_ROOT = Path(__file__).resolve().parents[2]
RUBRIC_PATH = EXAMPLE_ROOT / "semantic" / "rubric.md"
CONTEXT_GLOB = "src/orders/controllers/*.py"
MAX_CONTEXT_CHARS = 40_000
MAX_FINDINGS = 20  # verdict.schema.json findings.maxItems
MAX_RATIONALE_CHARS = 2000  # verdict.schema.json rationale.maxLength
MAX_EXPLANATION_CHARS = 1000  # verdict.schema.json findings[].explanation.maxLength
_START = "<!-- judge-instructions:start -->"
_END = "<!-- judge-instructions:end -->"
_TOP_LEVEL = {"verdict", "findings", "rationale"}
_FINDING = {"path", "line_start", "line_end", "rule", "explanation"}


class ProviderTimeout(Exception):
    """The provider did not answer in time."""


class ProviderUnavailable(Exception):
    """The provider could not be reached or refused the request."""


@dataclass(frozen=True)
class SourceFile:
    path: str  # relative to the example root, POSIX separators
    text: str


@dataclass(frozen=True)
class JudgeRequest:
    rule_id: str
    instructions: str  # fixed rubric text (system-style prompt)
    payload: str  # JSON data: the source under review, as numbered lines


@dataclass(frozen=True)
class Finding:
    path: str
    line_start: int
    line_end: int
    explanation: str


@dataclass(frozen=True)
class JudgeOutcome:
    status: str  # pass | violation | inconclusive | not_evaluated
    reason: str
    findings: tuple[Finding, ...] = ()
    raw_response: str | None = None
    # True when the provider itself failed (timeout, unavailable, error), as
    # opposed to answering. Still inconclusive, never a pass; the experiment
    # uses it to tell "the judge abstained" from "the judge could not run".
    provider_failed: bool = False


Provider = Callable[[JudgeRequest], str]


def judge_instructions(rubric_path: Path = RUBRIC_PATH) -> str:
    text = rubric_path.read_text(encoding="utf-8")
    start, end = text.index(_START) + len(_START), text.index(_END)
    return text[start:end].strip()


def load_context(root: Path) -> tuple[SourceFile, ...]:
    """Only the controller modules: the narrow context the rubric is about."""
    root = Path(root)
    return tuple(
        SourceFile(p.relative_to(root).as_posix(), p.read_text(encoding="utf-8"))
        for p in sorted(root.glob(CONTEXT_GLOB))
    )


def build_request(files: Sequence[SourceFile]) -> JudgeRequest:
    payload = {
        "rule_id": RULE_ID,
        "files": [
            {
                "path": f.path,
                "lines": [{"n": n, "text": line} for n, line in enumerate(f.text.splitlines(), 1)],
            }
            for f in files
        ],
    }
    return JudgeRequest(RULE_ID, judge_instructions(), json.dumps(payload, ensure_ascii=False))


def _inconclusive(reason: str, raw: str | None) -> JudgeOutcome:
    return JudgeOutcome("inconclusive", reason, (), raw)


def _provider_failed(reason: str) -> JudgeOutcome:
    return JudgeOutcome("inconclusive", reason, (), None, provider_failed=True)


def parse_verdict(raw: str, files: Sequence[SourceFile]) -> JudgeOutcome:
    """Strictly validate a reply against semantic/verdict.schema.json plus
    cross-field rules. Anything invalid is inconclusive, never a pass."""
    if not isinstance(raw, str):
        return _inconclusive("invalid response: not text", None)
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, RecursionError, ValueError):
        return _inconclusive("invalid response: not a single JSON object", raw)
    if not isinstance(data, dict):
        return _inconclusive("invalid response: not a JSON object", raw)
    if set(data) != _TOP_LEVEL:
        extra = sorted(set(data) - _TOP_LEVEL)
        missing = sorted(_TOP_LEVEL - set(data))
        return _inconclusive(
            f"invalid response: unexpected fields {extra}, missing fields {missing}", raw)
    verdict, findings, rationale = data["verdict"], data["findings"], data["rationale"]
    if verdict not in ("pass", "violation", "inconclusive"):
        return _inconclusive(f"invalid response: unknown verdict {verdict!r}", raw)
    if not isinstance(rationale, str) or not isinstance(findings, list):
        return _inconclusive("invalid response: wrong field types", raw)
    if len(rationale) > MAX_RATIONALE_CHARS:
        return _inconclusive(
            f"invalid response: rationale exceeds {MAX_RATIONALE_CHARS} characters", raw)
    if len(findings) > MAX_FINDINGS:
        return _inconclusive("invalid response: too many findings", raw)

    line_counts = {f.path: len(f.text.splitlines()) for f in files}
    parsed: list[Finding] = []
    for item in findings:
        if not isinstance(item, dict) or set(item) != _FINDING:
            return _inconclusive("invalid response: malformed finding", raw)
        start, end = item["line_start"], item["line_end"]
        if type(start) is not int or type(end) is not int:
            return _inconclusive("invalid response: line numbers must be integers", raw)
        if item["rule"] != RULE_ID:
            return _inconclusive(f"invalid response: unknown rule {item['rule']!r}", raw)
        if not isinstance(item["explanation"], str) or not item["explanation"].strip():
            return _inconclusive("invalid response: finding without explanation", raw)
        if len(item["explanation"]) > MAX_EXPLANATION_CHARS:
            return _inconclusive(
                f"invalid response: explanation exceeds {MAX_EXPLANATION_CHARS} characters", raw)
        path = item["path"]
        # Type-check before the dict lookup: an unhashable path (list, object)
        # would otherwise raise instead of staying unresolved.
        if not isinstance(path, str) or not path:
            return _inconclusive("invalid response: path must be a non-empty string", raw)
        if path not in line_counts:
            return _inconclusive(f"invalid evidence: {path!r} was not in the supplied context", raw)
        if not 1 <= start <= end <= line_counts[path]:
            return _inconclusive(
                f"invalid evidence: lines {start}-{end} are outside {path} "
                f"(1-{line_counts[path]})", raw)
        parsed.append(Finding(path, start, end, item["explanation"]))

    if verdict == "violation":
        if not parsed:
            return _inconclusive("invalid response: violation without evidence", raw)
        return JudgeOutcome("violation", rationale, tuple(parsed), raw)
    if parsed:
        return _inconclusive(f"invalid response: findings supplied with verdict {verdict!r}", raw)
    if verdict == "inconclusive":
        return _inconclusive(f"judge abstained: {rationale}", raw)
    return JudgeOutcome("pass", rationale, (), raw)


def judge(
    structural: SensorResult,
    files: Sequence[SourceFile],
    provider: Provider,
) -> JudgeOutcome:
    if structural.status is not Status.PASS:
        return JudgeOutcome(
            "not_evaluated",
            f"structural check is {structural.status.value}; repair it before semantic review",
        )
    if sum(len(f.text) for f in files) > MAX_CONTEXT_CHARS:
        return _inconclusive("context too large for the judge; narrow the files under review", None)
    request = build_request(files)
    try:
        raw = provider(request)
    except (ProviderTimeout, TimeoutError) as exc:
        return _provider_failed(f"provider timed out: {exc}")
    except (ProviderUnavailable, ConnectionError) as exc:
        return _provider_failed(f"provider unavailable: {exc}")
    except Exception as exc:  # any other provider failure is unresolved, not a pass
        return _provider_failed(f"provider error: {exc!r}")
    return parse_verdict(raw, files)


def format_outcome(outcome: JudgeOutcome) -> str:
    if outcome.status == "violation":
        lines = [f"SEMANTIC VIOLATION ({RULE_ID}): {outcome.reason}"]
        lines += [f"  {f.path}:{f.line_start}-{f.line_end}: {f.explanation}" for f in outcome.findings]
        lines.append("Check the cited lines yourself: a judge's verdict is a claim, not ground truth.")
        return "\n".join(lines)
    if outcome.status == "pass":
        return (f"SEMANTIC CHECK: no violation found ({RULE_ID}). A judge pass can be wrong; "
                f"it is not proof of compliance. Rationale: {outcome.reason}")
    if outcome.status == "not_evaluated":
        return f"SEMANTIC CHECK NOT RUN: {outcome.reason}"
    return f"SEMANTIC CHECK INCONCLUSIVE (not a pass): {outcome.reason}"
