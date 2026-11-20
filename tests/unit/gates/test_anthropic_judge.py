"""Live judge adapter with a mocked Anthropic client and spend guard: no network,
no SDK import, no credentials."""

from decimal import Decimal
from types import SimpleNamespace as NS

import pytest
from hypothesis import given
from hypothesis import strategies as st

from gates import anthropic_judge as aj
from gates.result import SensorResult, Status
from gates.semantic import JudgeRequest, ProviderTimeout, ProviderUnavailable, SourceFile, judge

CONTROLLER = "src/orders/controllers/orders.py"
FILES = (SourceFile(CONTROLLER, "def handler(request):\n    return {}\n"),)
PASS_REPLY = '{"verdict": "pass", "findings": [], "rationale": "Only maps requests."}'


def request(payload="{}"):
    return JudgeRequest("business-decision-in-controller", "instructions", payload)


def response(text=PASS_REPLY, stop="end_turn", usage=None, model="claude-haiku-5-5"):
    usage = usage or NS(input_tokens=1200, output_tokens=300, cache_creation_input_tokens=0,
                        cache_read_input_tokens=0, cache_creation=None)
    return NS(model=model, _request_id="req_test", id="msg_test", stop_reason=stop,
              stop_details=NS(category="cyber") if stop == "refusal" else None,
              usage=usage, content=[NS(type="thinking", thinking=""), NS(type="text", text=text)])


class Client:
    def __init__(self, reply=None, exc=None):
        self.reply, self.exc, self.kwargs = reply, exc, []
        self.messages = self

    def create(self, **kwargs):
        self.kwargs.append(kwargs)
        if self.exc:
            raise self.exc
        return self.reply


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


def provider(client, guard=None):
    ticks = iter([10.0, 11.25])
    return aj.AnthropicJudgeProvider(client, guard or Guard(), clock=lambda: next(ticks))


def structural_pass():
    return SensorResult(Status.PASS, {}, (), None, "ab" * 32, "2.17", 0, "")


class TestCredentials:
    def test_prefers_api_key_then_auth_token(self):
        assert aj.credential_from_env({"ANTHROPIC_API_KEY": "k", "ANTHROPIC_AUTH_TOKEN": "t"}) == (
            "ANTHROPIC_API_KEY", "k")
        assert aj.credential_from_env({"ANTHROPIC_AUTH_TOKEN": "t"}) == ("ANTHROPIC_AUTH_TOKEN", "t")

    @pytest.mark.parametrize("env", [{}, {"ANTHROPIC_API_KEY": ""}, {"OTHER": "x"}])
    def test_missing_credentials_name_what_is_needed(self, env):
        with pytest.raises(aj.MissingCredentials, match="ANTHROPIC_API_KEY"):
            aj.credential_from_env(env)

    def test_make_client_fails_before_importing_sdk(self):
        with pytest.raises(aj.MissingCredentials):
            aj.make_client({})


class TestCall:
    def test_sends_fixed_instructions_as_system_and_payload_as_user(self):
        client = Client(response())
        assert provider(client)(request('{"files": []}')) == PASS_REPLY
        sent = client.kwargs[0]
        assert sent["model"] == "claude-haiku-5-5"
        assert sent["system"] == "instructions"
        assert sent["messages"] == [{"role": "user", "content": '{"files": []}'}]
        assert sent["output_config"] == {"effort": "medium"}
        assert "temperature" not in sent and "thinking" not in sent

    def test_records_model_latency_usage_and_cost(self):
        guard = Guard()
        p = provider(Client(response()), guard)
        p(request())
        rec = p.calls[0]
        assert (rec.model_requested, rec.model_reported, rec.request_id) == (
            "claude-haiku-5-5", "claude-haiku-5-5", "req_test")
        assert rec.latency_s == 1.25 and rec.stop_reason == "end_turn"
        assert rec.usage["input_tokens"] == 1200 and rec.usage["rate_card"] == "standard"
        # 1200 x $0.10/MTok + 300 x $0.50/MTok
        assert Decimal(rec.cost_usd) == Decimal("0.00027")
        assert [e[0] for e in guard.events] == ["begin", "finish"]
        assert guard.events[1][2] == Decimal("0.00027")
        assert guard.events[0][2] == Decimal(rec.reservation_usd) >= Decimal(rec.cost_usd)

    def test_refused_by_ledger_sends_nothing(self):
        client = Client(response())
        p = provider(client, Guard(refuse=True))
        with pytest.raises(RuntimeError, match="cap"):
            p(request())
        assert client.kwargs == [] and p.calls[0].error.startswith("not started")

    def test_ledger_refusal_is_inconclusive_through_judge(self):
        outcome = judge(structural_pass(), FILES, provider(Client(response()), Guard(refuse=True)))
        assert outcome.status == "inconclusive"

    @pytest.mark.parametrize("exc,expected", [
        (TimeoutError("slow"), ProviderTimeout),
        (type("APITimeoutError", (Exception,), {})("t"), ProviderTimeout),
        (type("AuthenticationError", (Exception,), {})("401"), ProviderUnavailable),
        (ConnectionError("down"), ProviderUnavailable),
    ])
    def test_api_failures_map_to_boundary_and_keep_reservation(self, exc, expected):
        guard = Guard()
        p = provider(Client(exc=exc), guard)
        with pytest.raises(expected):
            p(request())
        assert guard.events[-1][0] == "fail" and guard.events[-1][2] is None
        assert p.calls[0].error and p.calls[0].latency_s == 1.25

    @pytest.mark.parametrize("stop", ["refusal", "max_tokens"])
    def test_refusal_and_truncation_are_charged_then_inconclusive(self, stop):
        guard = Guard()
        outcome = judge(structural_pass(), FILES, provider(Client(response(stop=stop)), guard))
        assert outcome.status == "inconclusive"
        assert guard.events[-1][0] == "finish"

    def test_missing_usage_fails_entry_and_is_inconclusive(self):
        guard = Guard()
        reply = response()
        reply.usage = None
        outcome = judge(structural_pass(), FILES, provider(Client(reply), guard))
        assert outcome.status == "inconclusive" and guard.events[-1][0] == "fail"

    def test_live_reply_still_goes_through_strict_parser(self):
        outcome = judge(structural_pass(), FILES, provider(Client(response("```json\n{}\n```"))))
        assert outcome.status == "inconclusive"
        outcome = judge(structural_pass(), FILES, provider(Client(response())))
        assert outcome.status == "pass"


class TestCost:
    def test_long_prompt_rate_card(self):
        u = aj.Usage(input_tokens=100_001, output_tokens=0)
        assert aj.cost_usd(u) == Decimal("100001") * Decimal("0.50") / aj.MTOK

    def test_cache_reads_count_toward_threshold(self):
        u = aj.Usage(input_tokens=50_000, output_tokens=0, cache_read_input_tokens=60_000)
        assert aj.rate_card(u.prompt_tokens) == "long"

    def test_cache_writes_without_breakdown_use_1h_rate(self):
        u = aj.Usage(input_tokens=0, output_tokens=0, cache_creation_input_tokens=100_000)
        assert aj.cost_usd(u) == Decimal("0.02")  # $0.20/MTok
        u = aj.Usage(0, 0, 100_000, 0, cache_creation_5m_tokens=100_000, cache_creation_1h_tokens=0)
        assert aj.cost_usd(u) == Decimal("0.0125")  # $0.125/MTok


tokens = st.integers(min_value=0, max_value=300_000)


class TestProperties:
    @given(tokens, tokens, tokens, tokens)
    def test_cost_is_non_negative_and_monotone_in_output(self, i, o, cw, cr):
        u = aj.Usage(i, o, cw, cr)
        more = aj.Usage(i, o + 1, cw, cr)
        assert aj.cost_usd(u) >= 0
        assert aj.cost_usd(more) > aj.cost_usd(u)

    @given(st.text(max_size=2000), st.text(max_size=2000), st.integers(0, 120_000), st.integers(1, 8000))
    def test_reservation_bounds_cost_of_any_reply_within_limits(self, instr, payload, extra, out):
        req = JudgeRequest("r", instr, payload)
        max_input = len(instr.encode()) + len(payload.encode()) + aj.REQUEST_OVERHEAD_TOKENS
        used = aj.Usage(input_tokens=min(max_input, extra), output_tokens=out)
        assert aj.reservation_usd(req, 8000) >= aj.cost_usd(used)
