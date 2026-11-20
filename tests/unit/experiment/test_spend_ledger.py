"""Shared spend ledger: reservations, refusal at the cap, totals and the file layer.
Usage is always mocked; the only filesystem use is pytest's temporary directory."""

import json
import threading
from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

import spend_ledger as sl
from spend_ledger import Ledger, LedgerError, SpendCapExceeded

D = Decimal
NOW = "2026-11-19T00:00:00+00:00"


def ledger(cap="100"):
    return Ledger(D(cap))


class TestBegin:
    def test_reserves_and_counts_toward_committed(self):
        led, eid = sl.begin(ledger(), "judge", "fixture", D("0.01"), now=NOW)
        assert led.entry(eid).status == "open"
        assert led.committed_usd == D("0.01")
        assert led.remaining_usd == D("99.99")

    def test_refuses_when_reservation_would_exceed_cap(self):
        led, _ = sl.begin(ledger(), "agent", "run 1", D("99.50"), now=NOW)
        with pytest.raises(SpendCapExceeded) as err:
            sl.begin(led, "judge", "call", D("0.51"), now=NOW)
        assert err.value.committed == D("99.50") and err.value.reserve == D("0.51")
        assert "remaining US$0.50" in str(err.value)

    def test_reservation_exactly_reaching_cap_is_allowed(self):
        led, _ = sl.begin(ledger(), "agent", "run", D("100"), now=NOW)
        assert led.remaining_usd == 0
        with pytest.raises(SpendCapExceeded):
            sl.begin(led, "judge", "any more", D("0.0000001"), now=NOW)

    @pytest.mark.parametrize("bad", ["-1", "NaN", "Infinity", "abc", None])
    def test_rejects_invalid_reservations(self, bad):
        with pytest.raises(LedgerError):
            sl.begin(ledger(), "judge", "x", bad, now=NOW)

    def test_rejects_zero_reservation_and_unknown_kind(self):
        with pytest.raises(LedgerError, match="positive"):
            sl.begin(ledger(), "judge", "x", D(0), now=NOW)
        with pytest.raises(LedgerError, match="kind"):
            sl.begin(ledger(), "ci", "x", D(1), now=NOW)

    def test_open_reservations_block_later_work(self):
        led, _ = sl.begin(ledger("1"), "agent", "still running", D("0.9"), now=NOW)
        with pytest.raises(SpendCapExceeded):
            sl.begin(led, "agent", "second", D("0.2"), now=NOW)


class TestClose:
    def test_finish_replaces_reservation_with_actual(self):
        led, eid = sl.begin(ledger(), "judge", "c", D("0.01"), now=NOW)
        led = sl.finish(led, eid, D("0.0003"), {"input_tokens": 1000}, now=NOW)
        e = led.entry(eid)
        assert (e.status, e.charged_usd, e.usage) == ("finished", D("0.0003"), {"input_tokens": 1000})
        assert led.committed_usd == D("0.0003")

    def test_fail_without_usage_keeps_reservation_as_charge(self):
        led, eid = sl.begin(ledger(), "agent", "r", D("2"), now=NOW)
        led = sl.fail(led, eid, note="timeout", now=NOW)
        e = led.entry(eid)
        assert e.status == "failed" and e.actual_usd is None and e.charged_usd == D("2")
        assert "usage unknown" in e.note and "timeout" in e.note

    def test_fail_with_known_cost_charges_it(self):
        led, eid = sl.begin(ledger(), "agent", "r", D("2"), now=NOW)
        led = sl.fail(led, eid, D("0.7"), {"output_tokens": 5}, now=NOW)
        assert led.committed_usd == D("0.7")

    def test_overrun_is_recorded_and_flagged(self):
        led, eid = sl.begin(ledger(), "agent", "r", D("1"), now=NOW)
        led = sl.finish(led, eid, D("1.5"), now=NOW)
        assert led.committed_usd == D("1.5")
        assert "exceeded reservation" in led.entry(eid).note

    def test_cannot_close_twice_or_unknown(self):
        led, eid = sl.begin(ledger(), "judge", "c", D("0.01"), now=NOW)
        led = sl.finish(led, eid, D("0.001"), now=NOW)
        with pytest.raises(LedgerError, match="already finished"):
            sl.fail(led, eid, now=NOW)
        with pytest.raises(LedgerError, match="no ledger entry"):
            sl.finish(led, "missing", D(0), now=NOW)


class TestSerialisation:
    def test_roundtrip_and_summary_fields(self):
        led, a = sl.begin(ledger(), "judge", "j", D("0.01"), now=NOW)
        led = sl.finish(led, a, D("0.000123"), {"input_tokens": 3}, now=NOW)
        led, _ = sl.begin(led, "agent", "a", D("5"), now=NOW)
        data = json.loads(json.dumps(led.to_json()))
        assert data["committed_usd"] == "5.000123"
        assert data["committed_by_kind_usd"] == {"judge": "0.000123", "agent": "5"}
        assert Ledger.from_json(data) == led

    @pytest.mark.parametrize("doc", [
        {}, {"schema": "other"}, {"schema": sl.SCHEMA, "cap_usd": "100", "entries": {}},
        {"schema": sl.SCHEMA, "cap_usd": "100", "entries": [{"id": "x"}]},
        {"schema": sl.SCHEMA, "cap_usd": "-1", "entries": []},
    ])
    def test_rejects_malformed_documents(self, doc):
        with pytest.raises(LedgerError):
            Ledger.from_json(doc)


class TestFileLayer:
    def test_begin_finish_persist_across_loads(self, tmp_path):
        path = tmp_path / "runs" / "spend-ledger.json"
        guard = sl.FileSpendGuard(path, "judge")
        eid = guard.begin("call", D("0.01"))
        assert sl.load(path).entry(eid).status == "open"
        guard.finish(eid, D("0.0002"), {"output_tokens": 10})
        assert sl.load(path).committed_usd == D("0.0002")
        assert guard.remaining() == D("99.9998")

    def test_refusal_leaves_file_unchanged(self, tmp_path):
        path = tmp_path / "ledger.json"
        sl.FileSpendGuard(path, "agent").begin("big", D("99.99"))
        before = path.read_text()
        with pytest.raises(SpendCapExceeded):
            sl.FileSpendGuard(path, "judge").begin("call", D("0.02"))
        assert path.read_text() == before

    def test_cap_mismatch_and_corrupt_file_are_errors(self, tmp_path):
        path = tmp_path / "ledger.json"
        sl.FileSpendGuard(path).begin("c", D("1"))
        with pytest.raises(LedgerError, match="differs"):
            sl.load(path, D("50"))
        path.write_text("{not json")
        with pytest.raises(LedgerError, match="cannot read"):
            sl.load(path)

    def test_concurrent_writers_never_exceed_cap(self, tmp_path):
        path = tmp_path / "ledger.json"
        guard = sl.FileSpendGuard(path, "agent", D("10"))
        results = []

        def worker():
            try:
                results.append(guard.begin("run", D("3")))
            except SpendCapExceeded:
                results.append(None)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        started = [r for r in results if r]
        assert len(started) == 3
        assert sl.load(path, D("10")).committed_usd == D("9")


money = st.decimals(min_value=D("0.000001"), max_value=D("40"), places=6)


class TestProperties:
    @given(st.lists(st.tuples(money, st.one_of(st.none(), money), st.booleans()), max_size=30))
    @settings(max_examples=200)
    def test_running_total_equals_sum_of_charges(self, ops):
        led = ledger()
        for i, (reserve, actual, close) in enumerate(ops):
            try:
                led, eid = sl.begin(led, "judge", f"op{i}", reserve, now=NOW)
            except SpendCapExceeded:
                continue
            if close:
                led = (sl.finish(led, eid, actual, now=NOW) if actual is not None
                       else sl.fail(led, eid, now=NOW))
        assert led.committed_usd == sum((e.charged_usd for e in led.entries), D(0))
        assert led.remaining_usd == led.cap_usd - led.committed_usd
        assert led.committed_usd >= led.actual_usd >= 0

    @given(st.lists(money, max_size=40), money)
    def test_refusal_boundary(self, reserves, probe):
        led = ledger()
        for i, r in enumerate(reserves):
            try:
                led, _ = sl.begin(led, "agent", f"r{i}", r, now=NOW)
            except SpendCapExceeded:
                pass
        allowed = led.committed_usd + probe <= led.cap_usd
        try:
            sl.begin(led, "judge", "probe", probe, now=NOW)
            assert allowed
        except SpendCapExceeded:
            assert not allowed

    @given(st.lists(st.tuples(money, st.decimals(min_value=0, max_value=1, places=6)), max_size=40))
    def test_cap_holds_when_actuals_stay_within_reservations(self, ops):
        led = ledger()
        for i, (reserve, fraction) in enumerate(ops):
            try:
                led, eid = sl.begin(led, "agent", f"r{i}", reserve, now=NOW)
            except SpendCapExceeded:
                continue
            led = sl.finish(led, eid, reserve * fraction, now=NOW)
            assert led.committed_usd <= led.cap_usd

    @given(st.lists(st.tuples(money, st.one_of(st.none(), money)), max_size=15))
    def test_json_roundtrip(self, ops):
        led = ledger()
        for i, (reserve, actual) in enumerate(ops):
            try:
                led, eid = sl.begin(led, "judge", f"o{i}", reserve, now=NOW)
            except SpendCapExceeded:
                continue
            if actual is not None:
                led = sl.finish(led, eid, actual, {"n": i}, now=NOW)
        assert Ledger.from_json(json.loads(json.dumps(led.to_json()))) == led

    @given(st.recursive(st.none() | st.booleans() | st.integers() | st.text(max_size=5),
                        lambda c: st.lists(c, max_size=3) | st.dictionaries(st.text(max_size=5), c, max_size=3),
                        max_leaves=10))
    def test_from_json_never_panics(self, doc):
        try:
            Ledger.from_json(doc)
        except LedgerError:
            pass
