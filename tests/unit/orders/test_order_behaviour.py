"""Behavioural tests for the order service, exercised through the controller.

These tests deliberately go through ``build_app()`` and the controller's public
handlers only. They describe what a caller observes (status codes and response
bodies), not how the layers are wired, so they keep passing when an agent
rewires the controller to read straight from the repository. That is the point
of the example: behaviour tests cannot see the architecture rule, so the rule
needs its own sensor.
"""

import pytest

from orders.wiring import build_app


@pytest.fixture
def controller():
    return build_app()


def create(controller, customer_id="cust-1", items=None):
    if items is None:
        items = [{"sku": "BOOK", "quantity": 2, "unit_price_cents": 1500}]
    return controller.handle_create({"customer_id": customer_id, "items": items})


class TestCreateOrder:
    def test_valid_request_creates_an_order(self, controller):
        response = create(controller)

        assert response.status == 201
        assert response.body["customer_id"] == "cust-1"
        assert response.body["status"] == "placed"
        assert response.body["items"] == [
            {"sku": "BOOK", "quantity": 2, "unit_price_cents": 1500}
        ]

    def test_each_order_gets_a_distinct_id(self, controller):
        first = create(controller).body["order_id"]
        second = create(controller).body["order_id"]

        assert first != second

    @pytest.mark.parametrize(
        "request_body",
        [
            {},
            {"customer_id": "", "items": [{"sku": "A", "quantity": 1, "unit_price_cents": 1}]},
            {"customer_id": "cust-1", "items": []},
            {"customer_id": "cust-1", "items": [{"sku": "A", "quantity": 0, "unit_price_cents": 1}]},
            {"customer_id": "cust-1", "items": [{"sku": "A", "quantity": 1, "unit_price_cents": -1}]},
            {"customer_id": "cust-1", "items": [{"sku": "", "quantity": 1, "unit_price_cents": 1}]},
            {"customer_id": "cust-1", "items": [{"sku": "A", "quantity": "2", "unit_price_cents": 1}]},
            {"customer_id": "cust-1", "items": "not-a-list"},
        ],
    )
    def test_invalid_requests_are_rejected_without_creating_an_order(
        self, controller, request_body
    ):
        response = controller.handle_create(request_body)

        assert response.status == 400
        assert "error" in response.body
        assert controller.handle_list_for_customer("cust-1").body["orders"] == []


class TestGetOrder:
    def test_returns_the_order_with_its_price_summary(self, controller):
        order_id = create(controller).body["order_id"]

        response = controller.handle_get(order_id)

        assert response.status == 200
        assert response.body["order_id"] == order_id
        assert response.body["subtotal_cents"] == 3000
        assert response.body["discount_cents"] == 0
        assert response.body["total_cents"] == 3000

    def test_unknown_order_is_not_found(self, controller):
        response = controller.handle_get("does-not-exist")

        assert response.status == 404
        assert response.body == {"error": "order not found"}


class TestDiscount:
    """Business policy: subtotals of $100.00 or more get 10% off (rounded down)."""

    @pytest.mark.parametrize(
        ("unit_price_cents", "quantity", "discount", "total"),
        [
            (9_999, 1, 0, 9_999),
            (10_000, 1, 1_000, 9_000),
            (5_000, 3, 1_500, 13_500),
            (10_005, 1, 1_000, 9_005),
        ],
    )
    def test_discount_applies_from_the_threshold(
        self, controller, unit_price_cents, quantity, discount, total
    ):
        items = [{"sku": "X", "quantity": quantity, "unit_price_cents": unit_price_cents}]
        order_id = create(controller, items=items).body["order_id"]

        body = controller.handle_get(order_id).body

        assert body["discount_cents"] == discount
        assert body["total_cents"] == total


class TestListForCustomer:
    def test_lists_only_that_customers_orders_in_creation_order(self, controller):
        first = create(controller, customer_id="cust-1").body["order_id"]
        create(controller, customer_id="cust-2")
        second = create(controller, customer_id="cust-1").body["order_id"]

        response = controller.handle_list_for_customer("cust-1")

        assert response.status == 200
        assert [o["order_id"] for o in response.body["orders"]] == [first, second]

    def test_customer_without_orders_gets_an_empty_list(self, controller):
        assert controller.handle_list_for_customer("nobody").body == {"orders": []}
