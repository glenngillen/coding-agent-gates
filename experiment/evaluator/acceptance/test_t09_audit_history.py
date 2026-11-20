"""T09 audit history: handle_audit_log()."""

from conftest import create, item

from orders.wiring import build_app


def test_placements_and_views_in_order_with_sequence_numbers(app):
    a = create(app, "alice", [item(unit_price_cents=15000)])
    app.handle_get(a["order_id"])
    b = create(app, "bob")

    response = app.handle_audit_log()

    assert response.status == 200
    assert response.body == {"events": [
        {"sequence": 1, "event": "order_placed", "order_id": a["order_id"], "customer_id": "alice",
         "total_cents": 13500},
        {"sequence": 2, "event": "order_viewed", "order_id": a["order_id"]},
        {"sequence": 3, "event": "order_placed", "order_id": b["order_id"], "customer_id": "bob",
         "total_cents": 1000},
    ]}


def test_failed_requests_record_nothing(app):
    app.handle_create({"customer_id": "", "items": []})
    app.handle_get("ord-9999")

    assert app.handle_audit_log().body == {"events": []}


def test_each_app_instance_has_its_own_log(app):
    create(app, "alice")

    assert build_app().handle_audit_log().body == {"events": []}
