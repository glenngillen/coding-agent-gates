"""Claude Code CLI judge adapter with a mocked subprocess runner and spend guard:
no process is spawned, no network, no credentials."""

import json
import subprocess
from decimal import Decimal
from types import SimpleNamespace as NS

import pytest
from hypothesis import given
from hypothesis import strategies as st

import spend_ledger as sl
from gates import claude_cli_judge as cj
from gates.result import SensorResult, Status
from gates.semantic import JudgeRequest, ProviderTimeout, ProviderUnavailable, SourceFile, judge

CONTROLLER = "src/orders/controllers/orders.py"
FILES = (SourceFile(CONTROLLER, "def handler(request):\n    return {}\n"),)
PASS_REPLY = '{"verdict": "pass", "findings": [], "rationale": "Only maps requests."}'
SECRET = "sk-ant-should-never-appear"


def cli_json(result=PASS_REPLY, is_error=False, models=("claude-haiku-5-5",), cost=0.0021, **extra):
    data = {
        "type": "result", "subtype": "success", "is_error": is_error, "result": result,
        "duration_ms": 1234, "stop_reason": "end_turn", "session_id": "s-1",
        "total_cost_usd": cost,
        "usage": {"input_tokens": 2, "output_tokens": 160, "cache_read_input_tokens": 7956},
        "modelUsage": {m: {"costUSD": cost} for m in models},
    }
    data.update(extra)
    return json.dumps(data)


class Runner:
    def __init__(self, stdout="", returncode=0, stderr="", exc=None):
        self.stdout, self.returncode, self.stderr, self.exc = stdout, returncode, stderr, exc
        self.calls = []

    def __call__(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        if self.exc:
            raise self.exc
        return NS(stdout=self.stdout, returncode=self.returncode, stderr=self.stderr)


class Guard:
    def __init__(self, refuse=False):
        self.refuse, self.events = refuse, []

    def begin(self, label, reserve):
        self.events.append(("begin", label, reserve))
        if self.refuse:
            raise RuntimeError("refused: cap")
        return "entry-1"

    def finish(self, entry_id, actual, usage=None, note=""):
        self.events.append(("finish", entry_id, actual, usage))

    def fail(self, entry_id, actual=None, usage=None, note=""):
        self.events.append(("fail", entry_id, actual, note))


def request(payload='{"files": []}'):
    return JudgeRequest("business-decision-in-controller", "RUBRIC INSTRUCTIONS", payload)


def provider(runner, guard=None, environ=None):
    ticks = iter([10.0, 12.5])
    return cj.ClaudeCliJudgeProvider(guard or Guard(), runner=runner, clock=lambda: next(ticks),
                                     environ={"PATH": "/usr/bin"} if environ is None else environ)


REQ_BOUND = cj.call_bound("RUBRIC INSTRUCTIONS", '{"files": []}')


def test_success_returns_reply_text_and_records_call():
    runner, guard = Runner(cli_json()), Guard()
    p = provider(runner, guard)
    assert p(request()) == PASS_REPLY
    rec = p.calls[0]
    assert rec.models_reported == ["claude-haiku-5-5"]
    assert rec.duration_ms == 1234 and rec.wall_s == 2.5
    assert rec.cost_usd == "0.0021" and rec.usage["output_tokens"] == 160
    assert rec.error is None and rec.exit_code == 0
    assert "notional" in rec.cost_basis
    assert guard.events[0] == ("begin", "judge (claude-haiku-5-5, CLI)", REQ_BOUND.reservation_usd)
    assert rec.reservation_usd == "1.3721" and rec.bound["budget_usd"] == "0.0521"
    assert rec.bound_exceeded is None
    assert guard.events[1][:3] == ("finish", "entry-1", Decimal("0.0021"))


def test_command_shape_and_payload_on_stdin():
    runner = Runner(cli_json())
    provider(runner)(request('{"payload": 1}'))
    argv, kwargs = runner.calls[0]
    assert argv[:2] == ["claude", "-p"]
    assert argv[argv.index("--model") + 1] == "claude-haiku-5-5"
    assert argv[argv.index("--output-format") + 1] == "json"
    assert argv[argv.index("--tools") + 1] == ""
    assert "--no-session-persistence" in argv
    assert argv[argv.index("--system-prompt") + 1] == "RUBRIC INSTRUCTIONS"
    budget = cj.call_bound("RUBRIC INSTRUCTIONS", '{"payload": 1}').budget_usd
    assert argv[argv.index("--max-budget-usd") + 1] == str(budget)
    assert '{"payload": 1}' not in argv  # source under review only on stdin
    assert kwargs["input"] == '{"payload": 1}'
    assert kwargs["timeout"] == cj.TIMEOUT_S
    # Environment inherited as is, plus only the settings the spend bound needs.
    assert kwargs["env"] == {"PATH": "/usr/bin", "CLAUDE_CODE_MAX_OUTPUT_TOKENS": "8000",
                             "CLAUDE_CODE_MAX_RETRIES": "0"}


def test_no_credential_is_read_or_recorded(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", SECRET)
    runner = Runner(cli_json())
    p = cj.ClaudeCliJudgeProvider(Guard(), runner=runner)  # real os.environ
    p(request())
    assert runner.calls[0][1]["env"]["ANTHROPIC_API_KEY"] == SECRET  # passed through untouched
    assert SECRET not in json.dumps([c.to_json() for c in p.calls])
    assert SECRET not in json.dumps(runner.calls[0][0])


def test_ledger_refusal_starts_nothing():
    runner, guard = Runner(cli_json()), Guard(refuse=True)
    p = provider(runner, guard)
    with pytest.raises(RuntimeError):
        p(request())
    assert runner.calls == []
    assert p.calls[0].error.startswith("not started")


def test_missing_cli_is_unavailable_and_charges_nothing():
    guard = Guard()
    p = provider(Runner(exc=FileNotFoundError("claude")), guard)
    with pytest.raises(ProviderUnavailable, match="not found"):
        p(request())
    assert guard.events[-1][:3] == ("fail", "entry-1", Decimal(0))
    assert p.calls[0].ledger_charged_usd == "0"
    assert p.calls[0].cost_usd is None


def test_timeout_keeps_reservation():
    guard = Guard()
    p = provider(Runner(exc=subprocess.TimeoutExpired("claude", 180)), guard)
    with pytest.raises(ProviderTimeout):
        p(request())
    assert guard.events[-1][:3] == ("fail", "entry-1", None)
    assert p.calls[0].ledger_charged_usd == p.calls[0].reservation_usd == str(REQ_BOUND.reservation_usd)


@pytest.mark.parametrize("stdout", ["", "not json", "[]", '{"type": "assistant"}'])
def test_invalid_output_is_unavailable(stdout):
    guard = Guard()
    p = provider(Runner(stdout, returncode=1, stderr="boom"), guard)
    with pytest.raises(ProviderUnavailable, match="invalid CLI output"):
        p(request())
    assert guard.events[-1][:3] == ("fail", "entry-1", None)


def test_is_error_charges_reported_cost_and_is_unavailable():
    guard = Guard()
    p = provider(Runner(cli_json(result="API Error", is_error=True, cost=0.0005,
                                 subtype="error_during_execution"), returncode=1), guard)
    with pytest.raises(ProviderUnavailable, match="error"):
        p(request())
    assert guard.events[-1][:3] == ("fail", "entry-1", Decimal("0.0005"))
    assert p.calls[0].ledger_charged_usd == "0.0005"


def test_missing_is_error_counts_as_error():
    data = json.loads(cli_json())
    del data["is_error"]
    with pytest.raises(ProviderUnavailable):
        provider(Runner(json.dumps(data)))(request())


def test_other_model_is_unavailable():
    guard = Guard()
    p = provider(Runner(cli_json(models=("claude-sonnet-5-5",))), guard)
    with pytest.raises(ProviderUnavailable, match="not claude-haiku-5-5"):
        p(request())
    assert p.calls[0].models_reported == ["claude-sonnet-5-5"]
    assert guard.events[-1][0] == "fail"


def test_missing_cost_is_unavailable():
    with pytest.raises(ProviderUnavailable, match="total_cost_usd"):
        provider(Runner(cli_json(cost=None)))(request())


def test_judge_turns_cli_failures_into_inconclusive():
    structural = SensorResult(Status.PASS, {}, (), None, "ab" * 32, "2.17", 0, "")
    for runner in (Runner(exc=FileNotFoundError("claude")), Runner("garbage"),
                   Runner(exc=subprocess.TimeoutExpired("claude", 1))):
        outcome = judge(structural, FILES, provider(runner))
        assert outcome.status == "inconclusive"


def test_judge_passes_through_valid_verdict():
    outcome = judge(SensorResult(Status.PASS, {}, (), None, "ab" * 32, "2.17", 0, ""), FILES, provider(Runner(cli_json())))
    assert outcome.status == "pass"


# --- spend bound -----------------------------------------------------------

def _price(tokens_in, tokens_out):
    return tokens_in * cj.INPUT_USD_PER_TOKEN_MAX + tokens_out * cj.OUTPUT_USD_PER_TOKEN_MAX


def test_call_bound_arithmetic():
    # Budget (expected normal call): 19 + 13 bytes + 32,000 framing = 32,032 input tokens at
    # $1.00/MTok + 8,000 output tokens at $2.50/MTok = 0.052032, rounded up to 0.0521.
    assert REQ_BOUND.input_bytes == 32 and REQ_BOUND.budget_input_tokens == 32_032
    assert REQ_BOUND.budget_output_tokens == 8_000 and REQ_BOUND.budget_usd == Decimal("0.0521")
    # One response at the documented model limits: 1M x $1/MTok + 128K x $2.50/MTok = 1.32.
    assert REQ_BOUND.response_input_tokens_max == 1_000_000
    assert REQ_BOUND.response_output_tokens_max == 128_000
    assert REQ_BOUND.response_usd == cj.RESPONSE_USD_MAX == Decimal("1.3200")
    assert REQ_BOUND.reservation_usd == Decimal("1.3721")


def test_response_bound_does_not_depend_on_the_framing_allowance(monkeypatch):
    before = cj.call_bound("", "x")
    monkeypatch.setattr(cj, "FRAMING_ALLOWANCE_TOKENS", 0)
    after = cj.call_bound("", "x")
    assert after.response_usd == before.response_usd == cj.RESPONSE_USD_MAX
    assert after.budget_usd < before.budget_usd


def test_largest_allowed_request_reservation():
    b = cj.call_bound("", "x" * cj.MAX_INPUT_BYTES)
    assert b.budget_usd == Decimal("0.2520")  # 0.232 + 0.02
    assert b.reservation_usd == Decimal("1.5720")


def test_oversized_request_is_refused_before_ledger_or_launch():
    runner, guard = Runner(cli_json()), Guard()
    p = provider(runner, guard)
    with pytest.raises(cj.RequestTooLarge):
        p(request("x" * cj.MAX_INPUT_BYTES))
    assert runner.calls == [] and guard.events == []
    assert p.calls[0].error.startswith("not started")


def test_bytes_not_characters_are_counted():
    with pytest.raises(cj.RequestTooLarge):
        cj.call_bound("", "\u00e9" * (cj.MAX_INPUT_BYTES // 2 + 1))  # 2 bytes each


def _ledger_at(path, committed):
    """A ledger file whose committed total is exactly ``committed``."""
    if committed:
        entry = sl.begin_run(path, "agent", "earlier work", committed)
        sl.finish_run(path, entry, committed)
    return sl.FileSpendGuard(path, "judge")


def test_reservation_that_exactly_fits_the_cap_is_started(tmp_path):
    path = tmp_path / "ledger.json"
    guard = _ledger_at(path, sl.CAP_USD - REQ_BOUND.reservation_usd)
    runner = Runner(cli_json(cost=0.0011))
    provider(runner, guard)(request())
    assert len(runner.calls) == 1
    assert sl.load(path).committed_usd == sl.CAP_USD - REQ_BOUND.reservation_usd + Decimal("0.0011")


def test_reservation_one_step_over_the_cap_is_refused_before_launch(tmp_path):
    path = tmp_path / "ledger.json"
    guard = _ledger_at(path, sl.CAP_USD - REQ_BOUND.reservation_usd + cj.USD_STEP)
    runner = Runner(cli_json())
    p = provider(runner, guard)
    with pytest.raises(sl.SpendCapExceeded):
        p(request())
    assert runner.calls == []
    assert p.calls[0].error.startswith("not started: refused")


def test_review_scenario_99_8958_committed_is_refused_before_launch(tmp_path):
    # Regression for the review: US$99.8958 committed used to admit a US$0.1042
    # reservation, and a US$0.20 reply then left US$100.0958 committed. The
    # reservation now covers a response at the model's limits, so nothing starts.
    path = tmp_path / "ledger.json"
    runner = Runner(cli_json(cost=0.20))
    p = provider(runner, _ledger_at(path, Decimal("99.8958")))
    with pytest.raises(sl.SpendCapExceeded):
        p(request())
    assert runner.calls == []
    assert sl.load(path).committed_usd == Decimal("99.8958")


@pytest.mark.parametrize("framing_tokens", [32_001, 200_000, 600_000,
                                            1_000_000 - 32 - 1])
def test_cli_framing_beyond_the_allowance_stays_within_the_cap(tmp_path, framing_tokens):
    # The CLI adds far more context than the 32,000-token allowance (and output runs to
    # the model maximum). Priced at the highest rates, that reply still fits the
    # reservation, so starting at exactly cap - reservation never passes the cap.
    path = tmp_path / "ledger.json"
    guard = _ledger_at(path, sl.CAP_USD - REQ_BOUND.reservation_usd)
    usage = {"input_tokens": 32, "cache_creation_input_tokens": framing_tokens,
             "output_tokens": cj.MODEL_MAX_OUTPUT_TOKENS}
    cost = _price(32 + framing_tokens, cj.MODEL_MAX_OUTPUT_TOKENS)
    p = provider(Runner(cli_json(cost=str(cost), usage=usage)), guard)
    assert p(request()) == PASS_REPLY  # not a breach: the bound does not assume the allowance
    rec = p.calls[0]
    assert rec.bound_exceeded is None and "input tokens > estimate" in rec.over_budget_estimate
    assert sl.load(path).committed_usd <= sl.CAP_USD


def test_framing_overrun_cost_alone_exceeds_the_old_reservation():
    # The case the old allowance-based reservation missed: 200,000 framing tokens cost more
    # than the whole old US$0.1042 reservation but less than the new one.
    cost = _price(32 + 200_000, cj.MAX_OUTPUT_TOKENS)
    assert Decimal("0.1042") < cost <= REQ_BOUND.reservation_usd


def test_budget_overshoot_by_one_maximal_response_fits_the_reservation():
    # Documented behaviour: the budget is checked after each response, so a call can pass
    # the budget by at most one response. A run of tiny replies followed by one maximal
    # reply is the worst case.
    spent = Decimal(0)
    for reply in [Decimal("0.0001")] * 520 + [cj.RESPONSE_USD_MAX]:
        if spent > REQ_BOUND.budget_usd:
            break
        spent += reply
    assert spent > REQ_BOUND.budget_usd and spent <= REQ_BOUND.reservation_usd


def test_timeout_at_the_boundary_keeps_the_full_bound_and_stays_within_cap(tmp_path):
    path = tmp_path / "ledger.json"
    guard = _ledger_at(path, sl.CAP_USD - REQ_BOUND.reservation_usd)
    p = provider(Runner(exc=subprocess.TimeoutExpired("claude", 180)), guard)
    with pytest.raises(ProviderTimeout):
        p(request())
    ledger = sl.load(path)
    assert ledger.entries[-1].status == "failed"
    assert ledger.entries[-1].charged_usd == REQ_BOUND.reservation_usd
    assert ledger.committed_usd == sl.CAP_USD
    with pytest.raises(sl.SpendCapExceeded):  # and nothing further can start
        provider(Runner(cli_json()), guard)(request())


@pytest.mark.parametrize("usage, note", [
    ({"input_tokens": 40_000, "output_tokens": 10}, "input tokens > estimate"),
    ({"input_tokens": 2, "output_tokens": 8_001}, "output tokens > estimate"),
    (None, None),
])
def test_usage_beyond_the_estimate_is_recorded_not_a_breach(usage, note):
    guard = Guard()
    p = provider(Runner(cli_json(cost=0.004, usage=usage)), guard)
    assert p(request()) == PASS_REPLY
    assert p.calls[0].over_budget_estimate == note or note in p.calls[0].over_budget_estimate
    assert guard.events[-1][:3] == ("finish", "entry-1", Decimal("0.004"))


def test_cost_over_reservation_breaks_the_bound(tmp_path):
    path = tmp_path / "ledger.json"
    p = provider(Runner(cli_json(cost=1.5)), sl.FileSpendGuard(path, "judge"))
    with pytest.raises(cj.SpendBoundExceeded, match="reservation"):
        p(request())
    entry = sl.load(path).entries[-1]
    assert entry.actual_usd == Decimal("1.5") and "exceeded reservation" in entry.note


class _MemoryGuard:
    """The begin/finish/fail protocol over the pure ledger, for property tests."""

    def __init__(self, ledger):
        self.ledger = ledger

    def begin(self, label, reserve):
        self.ledger, entry = sl.begin(self.ledger, "judge", label, reserve)
        return entry

    def finish(self, entry_id, actual, usage=None, note=""):
        self.ledger = sl.finish(self.ledger, entry_id, actual, usage, note=note)

    def fail(self, entry_id, actual=None, usage=None, note=""):
        self.ledger = sl.fail(self.ledger, entry_id, actual, usage, note=note)


class TestProperties:
    @given(st.text(max_size=300))
    def test_parse_never_raises_beyond_value_error(self, text):
        try:
            cj.parse_cli_output(text)
        except (ValueError, RecursionError):
            pass

    @given(st.one_of(st.none(), st.booleans(), st.integers(), st.floats(allow_nan=True),
                     st.text(max_size=20), st.lists(st.integers(), max_size=3)))
    def test_cost_is_none_or_finite_non_negative(self, value):
        cost = cj._cost(value)
        assert cost is None or (cost.is_finite() and cost >= 0)

    @given(st.integers(0, 13_721).map(lambda c: Decimal(c) / 10_000))
    def test_success_charges_exactly_reported_cost(self, cost):
        guard = Guard()
        p = cj.ClaudeCliJudgeProvider(guard, runner=Runner(cli_json(cost=str(cost))), environ={})
        p(request())
        assert guard.events[-1][2] == cost

    @given(st.integers(0, cj.MAX_INPUT_BYTES),
           st.integers(0, cj.MODEL_CONTEXT_WINDOW_TOKENS),
           st.integers(0, cj.MODEL_MAX_OUTPUT_TOKENS))
    def test_any_response_within_model_limits_costs_at_most_one_response_bound(
            self, payload_bytes, tokens_in, tokens_out):
        # tokens_in covers any mix of payload and CLI framing, up to the context window.
        bound = cj.call_bound("", "x" * payload_bytes)
        worst = _price(tokens_in, tokens_out)
        assert worst <= bound.response_usd
        assert bound.reservation_usd == bound.budget_usd + bound.response_usd
        assert bound.budget_usd + worst <= bound.reservation_usd

    @given(st.lists(st.tuples(st.integers(0, cj.MODEL_CONTEXT_WINDOW_TOKENS),
                              st.integers(0, cj.MODEL_MAX_OUTPUT_TOKENS)),
                    min_size=1, max_size=20))
    def test_documented_budget_stop_keeps_any_request_sequence_within_reservation(self, replies):
        # However many requests the CLI makes, it stops once spend passes the budget.
        spent = Decimal(0)
        for tokens_in, tokens_out in replies:
            if spent > REQ_BOUND.budget_usd:
                break
            spent += _price(tokens_in, tokens_out)
        assert spent <= REQ_BOUND.reservation_usd

    @given(st.integers(0, 1_000_000).map(lambda c: Decimal(c) / 10_000),
           st.sampled_from(["ok", "timeout", "error"]),
           st.integers(0, cj.MODEL_CONTEXT_WINDOW_TOKENS),
           st.integers(0, cj.MODEL_MAX_OUTPUT_TOKENS))
    def test_cap_is_never_exceeded_from_any_starting_point(self, committed, outcome,
                                                           tokens_in, tokens_out):
        # Reported costs range over every reply the model limits allow, including CLI
        # framing far beyond the allowance, not only replies inside the old estimate.
        cost = _price(tokens_in, tokens_out)
        usage = {"input_tokens": tokens_in, "output_tokens": tokens_out}
        start = sl.Ledger(sl.CAP_USD)
        if committed:
            start, e = sl.begin(start, "agent", "earlier", committed)
            start = sl.finish(start, e, committed)
        guard = _MemoryGuard(start)
        runner = {"ok": Runner(cli_json(cost=str(cost), usage=usage)),
                  "timeout": Runner(exc=subprocess.TimeoutExpired("claude", 1)),
                  "error": Runner(cli_json(is_error=True, cost=str(cost), usage=usage),
                                  returncode=1)}[outcome]
        p = cj.ClaudeCliJudgeProvider(guard, runner=runner, environ={})
        try:
            p(request())
        except (sl.SpendCapExceeded, ProviderUnavailable, ProviderTimeout):
            pass
        fits = committed + REQ_BOUND.reservation_usd <= sl.CAP_USD
        assert bool(runner.calls) == fits  # launched exactly when the full bound fits
        assert guard.ledger.committed_usd <= sl.CAP_USD
        assert not any(c.bound_exceeded for c in p.calls)
