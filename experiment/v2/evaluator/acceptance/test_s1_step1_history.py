from conftest import place


def test_history_is_newest_first_with_summary_totals(shop):
    first = place(shop, "c2", ("LAMP", 2))          # 12000, gold 15% -> 10200
    place(shop, "c1", ("PEN", 1))
    second = place(shop, "c2", ("BOOK", 1))         # 2500, no discount
    response = shop.insights.handle_order_history("c2")
    assert response.status == 200
    assert response.body == {"customer_id": "c2", "orders": [
        {"order_id": second, "status": "placed", "total_cents": 2500},
        {"order_id": first, "status": "placed", "total_cents": 10200},
    ]}


def test_history_includes_cancelled_orders_with_their_status(shop):
    oid = place(shop, "c1", ("PEN", 2))
    shop.orders.handle_cancel(oid)
    assert shop.insights.handle_order_history("c1").body["orders"] == [
        {"order_id": oid, "status": "cancelled", "total_cents": 600}]


def test_history_for_a_customer_without_orders_is_empty(shop):
    assert shop.insights.handle_order_history("c3").body == {"customer_id": "c3", "orders": []}


def test_unknown_customer_is_404(shop):
    response = shop.insights.handle_order_history("nobody")
    assert response.status == 404
    assert response.body == {"error": "customer not found"}
