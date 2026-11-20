"""T01 lookup: handle_get_for_customer(customer_id, order_id)."""

from conftest import create, item


def test_own_order_returns_the_same_body_as_handle_get(app):
    order = create(app, "alice", [item(unit_price_cents=12000)])

    response = app.handle_get_for_customer("alice", order["order_id"])

    assert response.status == 200
    assert response.body == app.handle_get(order["order_id"]).body
    assert response.body["discount_cents"] == 1200


def test_another_customers_order_is_indistinguishable_from_a_missing_one(app):
    order = create(app, "alice")

    other = app.handle_get_for_customer("bob", order["order_id"])
    missing = app.handle_get_for_customer("bob", "ord-9999")

    assert (other.status, other.body) == (404, {"error": "order not found"})
    assert (missing.status, missing.body) == (404, {"error": "order not found"})
