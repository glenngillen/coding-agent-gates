from conftest import place


def test_lifetime_value_sums_totals_of_orders_that_are_not_cancelled(shop):
    place(shop, "c1", ("LAMP", 2))                  # 12000 -> 10800
    place(shop, "c1", ("BOOK", 1))                  # 2500
    cancelled = place(shop, "c1", ("PEN", 3))
    shop.orders.handle_cancel(cancelled)
    response = shop.insights.handle_lifetime_value("c1")
    assert response.status == 200
    assert response.body == {"customer_id": "c1", "order_count": 2, "lifetime_value_cents": 13300}


def test_gold_discount_is_reflected(shop):
    place(shop, "c2", ("LAMP", 2))
    assert shop.insights.handle_lifetime_value("c2").body["lifetime_value_cents"] == 10200


def test_customer_without_orders_has_zero(shop):
    assert shop.insights.handle_lifetime_value("c3").body == {
        "customer_id": "c3", "order_count": 0, "lifetime_value_cents": 0}


def test_unknown_customer_is_404(shop):
    assert shop.insights.handle_lifetime_value("nobody").status == 404


def test_order_history_still_works(shop):
    oid = place(shop, "c3", ("PEN", 1))
    assert shop.insights.handle_order_history("c3").body["orders"][0]["order_id"] == oid
