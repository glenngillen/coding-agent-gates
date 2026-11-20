"""T03 totals: handle_customer_totals(customer_id)."""

from conftest import create, item


def test_sums_each_orders_own_discount(app):
    create(app, "alice", [item(unit_price_cents=12000)])  # discounted: 1200
    create(app, "alice", [item(unit_price_cents=5000)])   # below threshold
    create(app, "alice", [item(unit_price_cents=6000)])   # below threshold
    create(app, "bob", [item(unit_price_cents=50000)])

    response = app.handle_customer_totals("alice")

    assert response.status == 200
    assert response.body == {"customer_id": "alice", "order_count": 3, "subtotal_cents": 23000,
                             "discount_cents": 1200, "total_cents": 21800}


def test_customer_without_orders_gets_zeros(app):
    response = app.handle_customer_totals("nobody")

    assert response.status == 200
    assert response.body == {"customer_id": "nobody", "order_count": 0, "subtotal_cents": 0,
                             "discount_cents": 0, "total_cents": 0}
