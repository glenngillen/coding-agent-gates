"""T10 validation: business limits on order creation."""

import pytest

from conftest import item


def _post(app, items):
    return app.handle_create({"customer_id": "alice", "items": items})


@pytest.mark.parametrize(("items", "message"), [
    ([item(sku=f"S{n}") for n in range(21)], "too many line items"),
    ([item(quantity=101)], "quantity exceeds limit"),
    ([item(quantity=100, unit_price_cents=10001)], "order total exceeds limit"),
    ([item(sku=f"S{n}", quantity=101) for n in range(21)], "too many line items"),
    ([item(quantity=101, unit_price_cents=100000)], "quantity exceeds limit"),
])
def test_limits_are_rejected_with_422_and_no_order(app, items, message):
    response = _post(app, items)

    assert (response.status, response.body) == (422, {"error": message})
    assert app.handle_list_for_customer("alice").body == {"orders": []}


def test_orders_at_the_limits_are_created(app):
    items = [item(sku=f"S{n}", quantity=100, unit_price_cents=500) for n in range(20)]  # 1,000,000

    response = _post(app, items)

    assert response.status == 201
    assert len(response.body["items"]) == 20


@pytest.mark.parametrize("items", [[], [item(quantity=0)], [{"sku": "X"}]])
def test_malformed_requests_still_get_400(app, items):
    assert _post(app, items).status == 400
