"""results-v2.md rendering from synthetic records (labelled; no real run data)."""

import summarize_v2 as sm


def record(run_id, arm, model, slips, final="pass", cost="0.50"):
    return {
        "identity": {"run_id": run_id, "scenario_id": "S1-customer-insights", "arm": arm, "model_key": model,
                     "started_at": "2026-11-20T00:00:00+00:00", "finished_at": "2026-11-20T00:05:00+00:00",
                     "environment": {"claude_cli": "x", "python": "3.12", "import_linter": "2.17", "platform": "p"}},
        "outcome": {"termination": "completed", "final_structural": final, "semantic_judge": "pass",
                    "behavior": {"steps_accepted": ["a", "b", "c", "d"], "all_steps_accepted": True},
                    "tampering_detected": False, "legacy_reports_modified": False},
        "turns": [{"step": i + 1, "reached": True, "censored": False, "slip": s,
                   "caught": (True if s and arm != "A" else None), "repaired": (True if s and arm != "A" else None),
                   "new_edges": [["orders.controllers.x", "orders.infrastructure.y"]] if s else None,
                   "repair_requests": 1 if s and arm != "A" else 0, "end_structural": "pass",
                   "persisting_violation": False} for i, s in enumerate(slips)],
        "repair": {"applicable": arm != "A", "requests": sum(1 for s in slips if s) if arm != "A" else None},
        "usage": {"agent": {"cost_usd": cost}, "judge": {"development": {"cost_usd": "0.01"}, "evaluation": {}}},
        "time": {"session_s": 100.0},
    }


LEDGER = {"cap_usd": "100", "committed_usd": "10", "remaining_usd": "90", "committed_by_kind_usd": {}}


def test_renders_denominators_bounds_and_every_slip():
    records = [record("r1", "A", "haiku", [False, True, False, False], final="violation"),
               record("r2", "B", "haiku", [True, False, False, False])]
    plan = [{"run_id": "r1"}, {"run_id": "r2"}, {"run_id": "r3"}]
    s = sm.summarize(records, plan, LEDGER)
    text = sm.render("demo", records, plan, s)
    assert "Missing records: r3" in text
    assert "1/1 (95% bounds 5% to 100%)" in text
    assert "| r1 | 2 | `orders.controllers.x -> orders.infrastructure.y` |" in text
    assert "## Open questions" in text and "Slips occurred." in text


def test_a_ceiling_is_reported_as_one():
    records = [record("r1", "A", "sonnet", [False] * 4)]
    text = sm.render("demo", records, [{"run_id": "r1"}], sm.summarize(records, [{"run_id": "r1"}], LEDGER))
    assert "0/1 (upper 95% bound 95%)" in text
    assert "ceiling effect" in text


def test_per_cell_table_carries_bounds_for_every_count():
    records = [record("r1", "A", "haiku", [False] * 4), record("r2", "A", "haiku", [False] * 4),
               record("r3", "A", "haiku", [False] * 4)]
    plan = [{"run_id": r} for r in ("r1", "r2", "r3")]
    text = sm.render("demo", records, plan, sm.summarize(records, plan, LEDGER))
    per_cell = text.split("### Per cell", 1)[1].split("### Every slip", 1)[0]
    row = next(l for l in per_cell.splitlines() if l.startswith("| S1-customer-insights | A | haiku |"))
    assert row.count("0/3 (upper 95% bound 63%)") == 2
    assert "0/12 (upper 95% bound 22%)" in row
    assert "independent" in per_cell
