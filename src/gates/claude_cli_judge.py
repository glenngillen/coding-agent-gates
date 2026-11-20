"""Live semantic-judge provider: Claude Haiku 5.5 through the Claude Code CLI.

``ClaudeCliJudgeProvider`` is a ``gates.semantic.Provider``: it takes a
``JudgeRequest`` and returns the model's raw reply text. ``gates.semantic``
still owns every decision about that text (strict schema and evidence checks;
anything invalid is inconclusive, never a pass). This adapter runs one
non-interactive CLI call per request::

    claude -p --model claude-haiku-5-5 --output-format json --tools "" \\
        --no-session-persistence --setting-sources "" \\
        --max-budget-usd <budget> --system-prompt <rubric instructions>

with the JSON data payload (the source under review) on stdin. It uses
whatever login the ``claude`` CLI already has. It needs no API key and never
reads, prints or forwards a credential: the child process inherits the
environment, plus the two spend settings below, and nothing from it is
recorded.

Spend bound. Each call is charged to the shared spend ledger
(experiment/tools/spend_ledger.py) before it starts, with a reservation that
does not depend on how much context the CLI adds:

* ``--max-budget-usd`` is checked only after a response arrives, so the
  documented overshoot is one response's cost
  (https://code.claude.com/docs/en/agent-sdk/agent-loop#budget-headroom).
  A call can therefore spend at most ``budget + one response``, however many
  model requests the CLI makes.
* One response is bounded by the model's documented limits, not by anything
  the CLI promises: Claude Haiku 5.5 has a 1M-token context window and 128K
  maximum output tokens (models overview, retrieved 2026-11-19). Every one of
  those input tokens is priced at the highest Haiku 5.5 input rate (the 1-hour
  cache write for prompts over 100K tokens, US$1/MTok) and every output token
  at the long-context output rate (US$2.50/MTok): US$1.32 per response. The
  CLI's own framing (about 8,000 tokens observed) is inside that context
  window, so no framing allowance is part of the bound.
* The budget is the expected cost of a normal call: the rubric and payload
  (capped at ``MAX_INPUT_BYTES`` before launch; a token covers at least one
  UTF-8 byte), plus ``FRAMING_ALLOWANCE_TOKENS`` of CLI framing, plus
  ``CLAUDE_CODE_MAX_OUTPUT_TOKENS`` of output, at the same highest rates. If
  the CLI adds more framing than that, the call is still covered: it can stop
  only after a response, and one response is at most US$1.32.
* ``CLAUDE_CODE_MAX_RETRIES=0`` and ``--tools ""`` keep a normal call to one
  model request. The bound does not rely on them.

The reservation is ``budget + response bound``. The ledger refuses before
launch if the committed total plus that reservation would pass the cap, a
timeout (the child is killed) keeps the whole reservation as the charge, and
afterwards the reported ``total_cost_usd`` replaces it. The remaining
assumptions are the documented budget behaviour, the documented model limits
and the cached list prices. If the reported cost ever exceeds the reservation,
one of them has failed: the cost is still recorded, the call raises
``SpendBoundExceeded`` and callers must stop starting new calls. Input above
the expected budget figures is recorded (``CallRecord.over_budget_estimate``)
but is not a breach.

``total_cost_usd`` is the CLI's API-equivalent list-price estimate; under a
subscription login it is a notional cost, not an invoice.

A missing CLI, a timeout, a non-JSON reply, ``is_error: true``, a missing
result or a different model than requested all raise
``ProviderUnavailable``/``ProviderTimeout``, which ``gates.semantic.judge``
turns into an inconclusive verdict.

Known limit (context, not cost): the CLI wraps the rubric in roughly 8,000 tokens of its own
framing (observed in ``usage`` on 2026-11-19, CLI 2.1.322), so the judge's
context is not only the rubric and payload.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from decimal import ROUND_CEILING, Decimal, InvalidOperation
from typing import Any, Protocol

from gates.semantic import JudgeRequest, ProviderTimeout, ProviderUnavailable

MODEL = "claude-haiku-5-5"
CLI = "claude"
TIMEOUT_S = 180.0
# Spend-bound parameters (see the module docstring).
# Documented claude-haiku-5-5 limits (models overview, retrieved 2026-11-19,
# drafts/sensors-and-gates/sources.md T19): "Context window | 1M tokens",
# "Max output | 128K tokens". They bound one response whatever the CLI adds.
MODEL_CONTEXT_WINDOW_TOKENS = 1_000_000
MODEL_MAX_OUTPUT_TOKENS = 128_000
# Expected size of a normal call; sets --max-budget-usd, not the worst case.
MAX_INPUT_BYTES = 200_000  # rubric + payload, UTF-8; larger requests are refused before launch
FRAMING_ALLOWANCE_TOKENS = 32_000  # CLI framing; ~8,000 observed on 2026-11-19 (CLI 2.1.322)
MAX_OUTPUT_TOKENS = 8_000  # CLAUDE_CODE_MAX_OUTPUT_TOKENS; observed replies used <= 605
# Highest claude-haiku-5-5 list rates per token (Anthropic pricing page, retrieved 2026-11-19,
# drafts/sensors-and-gates/sources.md T17): prompts over 100K tokens cost $0.50 input,
# $1 per MTok for a 1-hour cache write and $2.50 output. The 1.1x US-only inference_geo
# multiplier does not apply: the CLI reports inference_geo "global".
INPUT_USD_PER_TOKEN_MAX = Decimal("1.00") / 1_000_000
OUTPUT_USD_PER_TOKEN_MAX = Decimal("2.50") / 1_000_000
CHILD_ENV = {"CLAUDE_CODE_MAX_OUTPUT_TOKENS": str(MAX_OUTPUT_TOKENS),
             "CLAUDE_CODE_MAX_RETRIES": "0"}
USD_STEP = Decimal("0.0001")
COST_BASIS = ("total_cost_usd reported by the Claude Code CLI: an API-equivalent list-price "
              "estimate; under a subscription login it is notional, not an invoice")
MAX_STDERR_CHARS = 500


class RequestTooLarge(ProviderUnavailable):
    """The request is larger than the spend bound allows; nothing was started."""


class SpendBoundExceeded(ProviderUnavailable):
    """A call's reported usage or cost broke the bound it was reserved under."""


@dataclass(frozen=True)
class CallBound:
    """Spend limits for one judge call, computed before launch."""

    input_bytes: int
    budget_input_tokens: int  # rubric + payload bytes + framing allowance
    budget_output_tokens: int
    budget_usd: Decimal  # passed as --max-budget-usd: the expected cost of a normal call
    response_input_tokens_max: int  # the model's context window
    response_output_tokens_max: int  # the model's maximum output
    response_usd: Decimal  # one response at the model limits and highest rates
    reservation_usd: Decimal  # budget + one response of overshoot

    def to_json(self) -> dict:
        return {k: str(v) if isinstance(v, Decimal) else v for k, v in asdict(self).items()}


def _price(tokens_in: int, tokens_out: int) -> Decimal:
    return (tokens_in * INPUT_USD_PER_TOKEN_MAX + tokens_out * OUTPUT_USD_PER_TOKEN_MAX
            ).quantize(USD_STEP, rounding=ROUND_CEILING)


# One response at the documented model limits: 1M x $1/MTok + 128K x $2.50/MTok = US$1.32.
RESPONSE_USD_MAX = _price(MODEL_CONTEXT_WINDOW_TOKENS, MODEL_MAX_OUTPUT_TOKENS)


def call_bound(system_prompt: str, payload: str) -> CallBound:
    """The reservation for one call. Raises ``RequestTooLarge`` above ``MAX_INPUT_BYTES``."""
    n = len(system_prompt.encode("utf-8")) + len(payload.encode("utf-8"))
    if n > MAX_INPUT_BYTES:
        raise RequestTooLarge(f"request is {n} bytes; the spend bound allows {MAX_INPUT_BYTES}")
    tokens_in = FRAMING_ALLOWANCE_TOKENS + n
    budget = _price(tokens_in, MAX_OUTPUT_TOKENS)
    return CallBound(n, tokens_in, MAX_OUTPUT_TOKENS, budget, MODEL_CONTEXT_WINDOW_TOKENS,
                     MODEL_MAX_OUTPUT_TOKENS, RESPONSE_USD_MAX, budget + RESPONSE_USD_MAX)


def usage_over_estimate(usage: dict | None, bound: CallBound) -> str | None:
    """Describe how reported usage exceeds the budget's size estimate, or None.
    Informational only: the reservation does not depend on the estimate."""
    if not isinstance(usage, dict):
        return None
    def n(key: str) -> int:
        v = usage.get(key, 0)
        return v if type(v) is int and v >= 0 else 0
    tokens_in = n("input_tokens") + n("cache_creation_input_tokens") + n("cache_read_input_tokens")
    tokens_out = n("output_tokens")
    notes = []
    if tokens_in > bound.budget_input_tokens:
        notes.append(f"{tokens_in} input tokens > estimate {bound.budget_input_tokens}")
    if tokens_out > bound.budget_output_tokens:
        notes.append(f"{tokens_out} output tokens > estimate {bound.budget_output_tokens}")
    return "; ".join(notes) or None


class SpendGuard(Protocol):
    def begin(self, label: str, reserve: Decimal) -> str: ...
    def finish(self, entry_id: str, actual: Decimal, usage: dict | None = None, note: str = "") -> None: ...
    def fail(self, entry_id: str, actual: Decimal | None = None, usage: dict | None = None,
             note: str = "") -> None: ...


Runner = Callable[..., Any]  # subprocess.run-compatible


def command(model: str, system_prompt: str, budget_usd: Decimal, cli: str = CLI) -> list[str]:
    """The argv for one judge call. No tools, no saved session, no settings files."""
    return [cli, "-p", "--model", model, "--output-format", "json", "--tools", "",
            "--no-session-persistence", "--setting-sources", "",
            "--max-budget-usd", str(budget_usd), "--system-prompt", system_prompt]


def _cost(value: Any) -> Decimal | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        amount = Decimal(str(value))
    except InvalidOperation:
        return None
    return amount if amount.is_finite() and amount >= 0 else None


@dataclass(frozen=True)
class CliReply:
    """The fields of one CLI JSON result that the adapter relies on."""

    is_error: bool
    result: str | None
    models: tuple[str, ...]  # modelUsage keys: the model(s) that actually answered
    duration_ms: int | None
    usage: dict | None
    cost_usd: Decimal | None
    stop_reason: str | None
    subtype: str | None
    session_id: str | None


def parse_cli_output(stdout: str) -> CliReply:
    """Parse the CLI's ``--output-format json`` result. Raises ``ValueError``
    for anything that is not a single JSON result object."""
    data = json.loads(stdout)
    if not isinstance(data, dict) or data.get("type") != "result":
        raise ValueError("not a Claude Code result object")
    usage = data.get("usage")
    model_usage = data.get("modelUsage")
    duration = data.get("duration_ms")
    result = data.get("result")
    return CliReply(
        is_error=data.get("is_error") is not False,  # absent or non-boolean counts as an error
        result=result if isinstance(result, str) else None,
        models=tuple(sorted(model_usage)) if isinstance(model_usage, dict) else (),
        duration_ms=duration if type(duration) is int else None,
        usage=usage if isinstance(usage, dict) else None,
        cost_usd=_cost(data.get("total_cost_usd")),
        stop_reason=data.get("stop_reason") if isinstance(data.get("stop_reason"), str) else None,
        subtype=data.get("subtype") if isinstance(data.get("subtype"), str) else None,
        session_id=data.get("session_id") if isinstance(data.get("session_id"), str) else None,
    )


@dataclass
class CallRecord:
    label: str
    model_requested: str
    started_at: str
    reservation_usd: str | None = None
    bound: dict | None = None
    models_reported: list[str] | None = None
    duration_ms: int | None = None  # as reported by the CLI
    wall_s: float | None = None  # measured around the subprocess
    stop_reason: str | None = None
    usage: dict | None = None
    cost_usd: str | None = None
    cost_basis: str = COST_BASIS
    exit_code: int | None = None
    ledger_entry_id: str | None = None
    ledger_charged_usd: str | None = None  # what the ledger kept: the cost, else the reservation
    over_budget_estimate: str | None = None  # informational; not a breach
    bound_exceeded: str | None = None
    error: str | None = None

    def to_json(self) -> dict:
        return asdict(self)


@dataclass
class ClaudeCliJudgeProvider:
    """Callable provider for ``gates.semantic.judge``. Records every call."""

    guard: SpendGuard
    runner: Runner = subprocess.run
    model: str = MODEL
    cli: str = CLI
    timeout_s: float = TIMEOUT_S
    environ: Mapping[str, str] = field(default_factory=lambda: os.environ)
    cwd: str | None = None
    label: str = "judge"
    clock: Callable[[], float] = time.monotonic
    calls: list[CallRecord] = field(default_factory=list)

    def _fail(self, record: CallRecord, error: str, actual: Decimal | None,
              usage: dict | None = None) -> None:
        record.error = error
        assert record.ledger_entry_id is not None  # only called after a successful begin()
        self.guard.fail(record.ledger_entry_id, actual, usage, note=error)
        record.ledger_charged_usd = str(actual) if actual is not None else record.reservation_usd

    def __call__(self, request: JudgeRequest) -> str:
        record = CallRecord(self.label, self.model,
                            datetime.now(timezone.utc).isoformat(timespec="seconds"))
        self.calls.append(record)
        try:
            bound = call_bound(request.instructions, request.payload)
        except RequestTooLarge as exc:
            record.error = f"not started (request too large): {exc}"
            raise
        record.bound, record.reservation_usd = bound.to_json(), str(bound.reservation_usd)
        try:
            record.ledger_entry_id = entry_id = self.guard.begin(f"{self.label} ({self.model}, CLI)",
                                                      bound.reservation_usd)
        except Exception as exc:  # cap reached or ledger unusable: nothing is started
            record.error = f"not started: {exc}"
            raise

        argv: Sequence[str] = command(self.model, request.instructions, bound.budget_usd, self.cli)
        # The child inherits the environment as is (nothing from it is read or
        # recorded) plus the two settings that make the spend bound hold.
        env = {**self.environ, **CHILD_ENV}
        start = self.clock()
        try:
            proc = self.runner(argv, input=request.payload, capture_output=True, text=True,
                               timeout=self.timeout_s, cwd=self.cwd, env=env, check=False)
        except FileNotFoundError as exc:
            record.wall_s = round(self.clock() - start, 3)
            # The CLI never started, so nothing was spent.
            self._fail(record, f"Claude Code CLI not found: {exc}", Decimal(0))
            raise ProviderUnavailable(record.error) from exc
        except subprocess.TimeoutExpired as exc:
            record.wall_s = round(self.clock() - start, 3)
            # subprocess.run killed the child; spend is unknown but within the
            # bound, so the whole reservation stays as the charge.
            self._fail(record, f"timed out after {self.timeout_s}s", None)
            raise ProviderTimeout(record.error) from exc
        except OSError as exc:
            record.wall_s = round(self.clock() - start, 3)
            self._fail(record, f"could not run the CLI: {exc}", None)
            raise ProviderUnavailable(record.error) from exc
        record.wall_s = round(self.clock() - start, 3)
        record.exit_code = proc.returncode

        try:
            reply = parse_cli_output(proc.stdout or "")
        except (ValueError, RecursionError) as exc:
            stderr = (proc.stderr or "").strip()[:MAX_STDERR_CHARS]
            self._fail(record, f"invalid CLI output (exit {proc.returncode}): {exc}; stderr: {stderr}",
                       None)
            raise ProviderUnavailable(record.error) from exc

        record.models_reported = list(reply.models)
        record.duration_ms = reply.duration_ms
        record.stop_reason = reply.stop_reason
        record.usage = reply.usage
        record.cost_usd = None if reply.cost_usd is None else str(reply.cost_usd)

        problem = None
        if reply.is_error or proc.returncode != 0:
            problem = f"CLI reported an error (exit {proc.returncode}, subtype {reply.subtype})"
        elif reply.result is None:
            problem = "CLI result has no reply text"
        elif reply.models != (self.model,):
            problem = f"answered by {list(reply.models)}, not {self.model}"
        elif reply.cost_usd is None:
            problem = "CLI result has no usable total_cost_usd"

        record.over_budget_estimate = usage_over_estimate(reply.usage, bound)
        if reply.cost_usd is not None and reply.cost_usd > bound.reservation_usd:
            over = f"cost US${reply.cost_usd} > reservation US${bound.reservation_usd}"
            record.bound_exceeded = over
            problem = f"spend bound broken: {over}"
            # The money is spent: record the reported cost.
            self._fail(record, problem, reply.cost_usd, reply.usage)
            raise SpendBoundExceeded(problem)

        if problem or reply.cost_usd is None or reply.result is None:
            problem = problem or "incomplete CLI result"
            self._fail(record, problem, reply.cost_usd, reply.usage)
            raise ProviderUnavailable(problem)
        self.guard.finish(entry_id, reply.cost_usd, reply.usage,
                          note=f"session_id={reply.session_id}; {COST_BASIS}")
        record.ledger_charged_usd = str(reply.cost_usd)
        return reply.result
