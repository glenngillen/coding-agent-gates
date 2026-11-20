"""T04 discounts: handle_quote(request)."""

import pytest

from conftest import create, item


@pytest.mark.parametrize(("price", "discount"), [(9999, 0), (10000, 1000), (12345, 1234)])
def test_quote_matches_the_price_of_the_placed_order(app, price, discount):
    request = {"customer_id": "alice", "items": [item(unit_price_cents=price)]}

    quote = app.handle_quote(request)
    placed = app.handle_get(create(app, "alice", request["items"])["order_id"]).body

    assert quote.status == 200
    assert quote.body == {"subtotal_cents": price, "discount_cents": discount,
                          "total_cents": price - discount}
    assert quote.body["total_cents"] == placed["total_cents"]


def test_quoting_creates_no_order_and_uses_no_id(app):
    app.handle_quote({"customer_id": "alice", "items": [item()]})

    assert app.handle_list_for_customer("alice").body == {"orders": []}
    assert create(app, "alice")["order_id"] == "ord-0001"


@pytest.mark.parametrize("request_body", [
    {"customer_id": "alice", "items": []},
    {"customer_id": "", "items": [item()]},
    {"customer_id": "alice", "items": [item(quantity=0)]},
])
def test_invalid_requests_get_the_create_error(app, request_body):
    quote = app.handle_quote(request_body)

    assert quote.status == 400
    assert quote.body == app.handle_create(request_body).body
