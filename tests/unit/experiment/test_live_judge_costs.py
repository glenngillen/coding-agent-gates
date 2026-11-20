"""Cost aggregation for the live judge run: unknown spend is never reported as a
complete total. Pure: call records are plain dicts, nothing is executed."""

from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from run_live_judge import summarize_costs


def started(cost, reservation="0.05", eid="e1"):
    return {"ledger_entry_id": eid, "cost_usd": cost, "reservation_usd": reservation}


def refused(reservation="0.05"):
    return {"ledger_entry_id": None, "cost_usd": None, "reservation_usd": reservation,
            "error": "not started: spend cap reached"}


def test_all_known_reports_complete_total():
    s = summarize_costs([started("0.010"), started("0.002")])
    assert s["total_cost_usd"] == "0.012" == s["known_cost_subtotal_usd"]
    assert s["unknown_cost_calls"] == 0
    assert s["total_cost_note"].startswith("complete")


def test_all_unknown_makes_total_unavailable_not_zero():
    s = summarize_costs([started(None, "0.05"), started(None, "0.07")])
    assert s["total_cost_usd"] is None
    assert s["known_cost_subtotal_usd"] == "0"
    assert s["unknown_cost_calls"] == 2 and s["started_calls"] == 2
    assert s["unknown_cost_reserved_usd"] == "0.12"
    assert s["total_cost_note"].startswith("unavailable")


def test_mixed_reports_subtotal_and_unknown_count():
    s = summarize_costs([started("0.010"), started(None, "0.05")])
    assert s["total_cost_usd"] is None
    assert s["known_cost_subtotal_usd"] == "0.010"
    assert (s["known_cost_calls"], s["unknown_cost_calls"]) == (1, 1)


def test_ledger_refusals_are_not_unknown_spend():
    s = summarize_costs([started("0.010"), refused(), refused()])
    assert s["ledger_refused_calls"] == 2
    assert s["started_calls"] == 1 and s["unknown_cost_calls"] == 0
    assert s["total_cost_usd"] == "0.010"


def test_zero_cost_string_counts_as_known():
    assert summarize_costs([started("0")])["total_cost_usd"] == "0"


def test_no_calls():
    s = summarize_costs([])
    assert s["total_cost_usd"] == "0" and s["started_calls"] == 0


money = st.decimals(min_value=0, max_value=10, places=6).map(str)
call = st.one_of(
    st.builds(started, money, money),
    st.builds(started, st.none(), money),
    st.builds(refused, money),
)


class TestProperties:
    @given(st.lists(call, max_size=30))
    def test_counts_partition_and_total_only_when_complete(self, calls):
        s = summarize_costs(calls)
        assert s["started_calls"] + s["ledger_refused_calls"] == len(calls)
        assert s["known_cost_calls"] + s["unknown_cost_calls"] == s["started_calls"]
        known = [c for c in calls if c["ledger_entry_id"] and c["cost_usd"] is not None]
        assert Decimal(s["known_cost_subtotal_usd"]) == sum(
            (Decimal(c["cost_usd"]) for c in known), Decimal(0))
        if s["unknown_cost_calls"]:
            assert s["total_cost_usd"] is None
        else:
            assert s["total_cost_usd"] == s["known_cost_subtotal_usd"]
