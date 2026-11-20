"""Live semantic-judge provider: Claude Haiku 5.5 through the Anthropic API.

``AnthropicJudgeProvider`` is a ``gates.semantic.Provider``: it takes a
``JudgeRequest`` and returns the model's raw reply text. ``gates.semantic``
still owns every decision about that text (strict schema and evidence checks;
anything invalid is inconclusive, never a pass). This module adds only:

- Credentials from the environment, never from files or arguments:
  ``ANTHROPIC_API_KEY`` (or ``ANTHROPIC_AUTH_TOKEN``). Missing credentials raise
  ``MissingCredentials`` before any request; there is no synthetic fallback.
- A spend guard consulted before each call (an upper-bound reservation) and
  updated after it (actual cost from the reported usage), so judge calls share
  the experiment's US$100 cap with agent runs (experiment/tools/spend_ledger.py).
- A ``CallRecord`` per call: requested and reported model, request id, latency,
  stop reason, token usage and cost.

Prices are the Anthropic first-party list prices for ``claude-haiku-5-5``,
retrieved 2026-11-19 from https://platform.claude.com/docs/en/about-claude/pricing
(see drafts/sensors-and-gates/sources.md). Re-check them before reusing the
cost figures: they are recorded constants, not fetched at run time.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from collections.abc import Mapping
from typing import Any, Protocol

from gates.semantic import JudgeRequest, ProviderTimeout, ProviderUnavailable

MODEL = "claude-haiku-5-5"
MAX_TOKENS = 8000  # includes adaptive-thinking tokens; a cut-off reply is inconclusive
EFFORT = "medium"  # the model's default, set explicitly so the run records it
TIMEOUT_S = 120.0
CREDENTIAL_VARS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")
PRICES_RETRIEVED = "2026-11-19"
PRICES_SOURCE = "https://platform.claude.com/docs/en/about-claude/pricing"
LONG_PROMPT_THRESHOLD = 100_000  # prompt tokens, counting cache reads and writes
MTOK = Decimal(1_000_000)
# US$ per million tokens: (input, 5m cache write, 1h cache write, cache read, output)
PRICES = {
    "standard": (Decimal("0.10"), Decimal("0.125"), Decimal("0.20"), Decimal("0.01"), Decimal("0.50")),
    "long": (Decimal("0.50"), Decimal("0.625"), Decimal("1"), Decimal("0.05"), Decimal("2.50")),
}
# Upper-bound allowance for message framing around the instructions and payload.
REQUEST_OVERHEAD_TOKENS = 1_000


class MissingCredentials(Exception):
    """No Anthropic credential is set in the environment."""

    def __init__(self) -> None:
        super().__init__(
            "no Anthropic API credential in the environment: set ANTHROPIC_API_KEY "
            "(or ANTHROPIC_AUTH_TOKEN) for an account that can call claude-haiku-5-5")


class SpendGuard(Protocol):
    def begin(self, label: str, reserve: Decimal) -> str: ...
    def finish(self, entry_id: str, actual: Decimal, usage: dict | None = None, note: str = "") -> None: ...
    def fail(self, entry_id: str, actual: Decimal | None = None, usage: dict | None = None,
             note: str = "") -> None: ...


@dataclass(frozen=True)
class Usage:
    input_tokens: int
    output_tokens: int
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_5m_tokens: int | None = None
    cache_creation_1h_tokens: int | None = None

    @property
    def prompt_tokens(self) -> int:
        return self.input_tokens + self.cache_creation_input_tokens + self.cache_read_input_tokens


def rate_card(prompt_tokens: int) -> str:
    return "long" if prompt_tokens > LONG_PROMPT_THRESHOLD else "standard"


def cost_usd(usage: Usage) -> Decimal:
    """Cost of one call from its reported usage, at the recorded list prices.

    Without a 5-minute/1-hour breakdown, cache writes are priced at the higher
    1-hour rate so the figure is never an under-estimate. The adapter does not
    request prompt caching, so these lines are normally zero.
    """
    p_in, p_w5, p_w1, p_read, p_out = PRICES[rate_card(usage.prompt_tokens)]
    if usage.cache_creation_5m_tokens is None or usage.cache_creation_1h_tokens is None:
        writes = usage.cache_creation_input_tokens * p_w1
    else:
        writes = usage.cache_creation_5m_tokens * p_w5 + usage.cache_creation_1h_tokens * p_w1
    total = (usage.input_tokens * p_in + writes + usage.cache_read_input_tokens * p_read
             + usage.output_tokens * p_out)
    return total / MTOK


def reservation_usd(request: JudgeRequest, max_tokens: int = MAX_TOKENS) -> Decimal:
    """An upper bound on one call's cost, reserved in the ledger before calling.

    A token is never shorter than one UTF-8 byte, so the byte length of the
    instructions and payload (plus framing overhead) bounds the input tokens;
    ``max_tokens`` bounds the output, thinking included.
    """
    prompt_bound = (len(request.instructions.encode("utf-8")) + len(request.payload.encode("utf-8"))
                    + REQUEST_OVERHEAD_TOKENS)
    p_in, _w5, _w1, _read, p_out = PRICES[rate_card(prompt_bound)]
    return (prompt_bound * p_in + max_tokens * p_out) / MTOK


def credential_from_env(environ: Mapping[str, str] | None = None) -> tuple[str, str]:
    env: Mapping[str, str] = os.environ if environ is None else environ
    for name in CREDENTIAL_VARS:
        if env.get(name):
            return name, env[name]
    raise MissingCredentials()


def make_client(environ: Mapping[str, str] | None = None) -> Any:
    """An ``anthropic.Anthropic`` client using only an environment credential.

    SDK retries are off (``max_retries=0``): a retry is a separate, visible
    attempt in the experiment record, not something hidden inside one call.
    """
    name, secret = credential_from_env(environ)
    import anthropic  # imported lazily: the offline tests and sensor never need the SDK

    kwargs = {"api_key": secret} if name == "ANTHROPIC_API_KEY" else {"auth_token": secret}
    return anthropic.Anthropic(**kwargs, max_retries=0, timeout=TIMEOUT_S)


def _usage_from(raw: Any) -> Usage:
    cache = getattr(raw, "cache_creation", None)
    return Usage(
        input_tokens=int(raw.input_tokens),
        output_tokens=int(raw.output_tokens),
        cache_creation_input_tokens=int(getattr(raw, "cache_creation_input_tokens", None) or 0),
        cache_read_input_tokens=int(getattr(raw, "cache_read_input_tokens", None) or 0),
        cache_creation_5m_tokens=(None if cache is None
                                  else int(getattr(cache, "ephemeral_5m_input_tokens", 0) or 0)),
        cache_creation_1h_tokens=(None if cache is None
                                  else int(getattr(cache, "ephemeral_1h_input_tokens", 0) or 0)),
    )


@dataclass
class CallRecord:
    label: str
    model_requested: str
    started_at: str
    reservation_usd: str
    effort: str = EFFORT
    max_tokens: int = MAX_TOKENS
    model_reported: str | None = None
    request_id: str | None = None
    latency_s: float | None = None
    stop_reason: str | None = None
    usage: dict | None = None
    cost_usd: str | None = None
    ledger_entry_id: str | None = None
    error: str | None = None

    def to_json(self) -> dict:
        return asdict(self)


def _classify(exc: Exception) -> Exception:
    """Map SDK and network failures onto the semantic boundary's exceptions."""
    name = type(exc).__name__
    if isinstance(exc, TimeoutError) or "Timeout" in name:
        return ProviderTimeout(f"{name}: {exc}")
    return ProviderUnavailable(f"{name}: {exc}")


@dataclass
class AnthropicJudgeProvider:
    """Callable provider for ``gates.semantic.judge``. Records every call."""

    client: Any
    guard: SpendGuard
    model: str = MODEL
    max_tokens: int = MAX_TOKENS
    effort: str = EFFORT
    label: str = "judge"
    clock: Any = time.monotonic
    calls: list[CallRecord] = field(default_factory=list)

    def __call__(self, request: JudgeRequest) -> str:
        reserve = reservation_usd(request, self.max_tokens)
        record = CallRecord(self.label, self.model,
                            datetime.now(timezone.utc).isoformat(timespec="seconds"),
                            str(reserve), self.effort, self.max_tokens)
        self.calls.append(record)
        try:
            record.ledger_entry_id = self.guard.begin(f"{self.label} ({self.model})", reserve)
        except Exception as exc:  # cap reached or ledger unusable: no request is sent
            record.error = f"not started: {exc}"
            raise
        start = self.clock()
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=request.instructions,
                messages=[{"role": "user", "content": request.payload}],
                output_config={"effort": self.effort},
            )
        except Exception as exc:
            record.latency_s = round(self.clock() - start, 3)
            record.error = f"{type(exc).__name__}: {exc}"
            self.guard.fail(record.ledger_entry_id, None, None, note=record.error)
            raise _classify(exc) from exc
        record.latency_s = round(self.clock() - start, 3)
        record.model_reported = getattr(response, "model", None)
        record.request_id = getattr(response, "_request_id", None) or getattr(response, "id", None)
        record.stop_reason = getattr(response, "stop_reason", None)
        try:
            usage = _usage_from(response.usage)
        except (AttributeError, TypeError, ValueError) as exc:
            record.error = f"usage missing or malformed: {exc!r}"
            self.guard.fail(record.ledger_entry_id, None, None, note=record.error)
            raise ProviderUnavailable(record.error) from exc
        cost = cost_usd(usage)
        record.usage = {**asdict(usage), "rate_card": rate_card(usage.prompt_tokens)}
        record.cost_usd = str(cost)
        self.guard.finish(record.ledger_entry_id, cost, record.usage,
                          note=f"request_id={record.request_id}")

        if record.stop_reason == "refusal":
            details = getattr(response, "stop_details", None)
            record.error = f"refusal: {getattr(details, 'category', None)}"
            raise ProviderUnavailable(f"model declined the request ({record.error})")
        if record.stop_reason == "max_tokens":
            record.error = "reply cut off at max_tokens"
            raise ProviderUnavailable(record.error)
        return "".join(b.text for b in response.content if getattr(b, "type", None) == "text")


def records_json(records: list[CallRecord]) -> str:
    return json.dumps([r.to_json() for r in records], indent=2)
