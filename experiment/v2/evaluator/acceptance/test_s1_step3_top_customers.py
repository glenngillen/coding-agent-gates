import pytest
from conftest import place


def test_top_customers_by_lifetime_value(shop):
    place(shop, "c1", ("BOOK", 1))                  # c1: 2500
    place(shop, "c2", ("LAMP", 2))                  # c2: 10200
    place(shop, "c3", ("BOOK", 1))                  # c3: 2500 (ties with c1; c1 first)
    response = shop.insights.handle_top_customers(2)
    assert response.status == 200
    assert response.body == {"customers": [
        {"customer_id": "c2", "name": "Grace", "lifetime_value_cents": 10200},
        {"customer_id": "c1", "name": "Ada", "lifetime_value_cents": 2500},
    ]}


def test_customers_with_no_value_are_left_out(shop):
    place(shop, "c1", ("PEN", 1))
    cancelled = place(shop, "c2", ("BOOK", 1))
    shop.orders.handle_cancel(cancelled)
    assert shop.insights.handle_top_customers(10).body == {"customers": [
        {"customer_id": "c1", "name": "Ada", "lifetime_value_cents": 300}]}


@pytest.mark.parametrize("limit", [0, -1, "3", None, 2.5, True])
def test_invalid_limit_is_400(shop, limit):
    response = shop.insights.handle_top_customers(limit)
    assert response.status == 400
    assert "error" in response.body


def test_earlier_endpoints_still_work(shop):
    place(shop, "c1", ("BOOK", 1))
    assert shop.insights.handle_lifetime_value("c1").body["lifetime_value_cents"] == 2500
