# Reference implementation for T03: evaluator only, never copied into an agent workspace.
# Derived from the baseline module; only the T03 change differs.
"""Order controller: request decoding and response mapping only.

Business decisions (such as discount eligibility) belong to the application
service, and the controller never imports a repository.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from orders.application.order_service import OrderNotFound, OrderService
from orders.domain import LineItem, Order, OrderSummary


@dataclass(frozen=True)
class Response:
    status: int
    body: dict[str, Any]


class InvalidRequest(ValueError):
    pass


def _decode_items(raw: Any) -> list[LineItem]:
    if not isinstance(raw, list) or not raw:
        raise InvalidRequest("items must be a non-empty list")
    items = []
    for entry in raw:
        if not isinstance(entry, dict):
            raise InvalidRequest("each item must be an object")
        sku = entry.get("sku")
        quantity = entry.get("quantity")
        price = entry.get("unit_price_cents")
        if not isinstance(sku, str) or not sku:
            raise InvalidRequest("sku must be a non-empty string")
        if type(quantity) is not int or quantity < 1:
            raise InvalidRequest("quantity must be a positive integer")
        if type(price) is not int or price < 0:
            raise InvalidRequest("unit_price_cents must be a non-negative integer")
        items.append(LineItem(sku, quantity, price))
    return items


def _order_body(order: Order) -> dict[str, Any]:
    return {
        "order_id": order.order_id,
        "customer_id": order.customer_id,
        "status": order.status,
        "items": [
            {"sku": i.sku, "quantity": i.quantity, "unit_price_cents": i.unit_price_cents}
            for i in order.items
        ],
    }


def _summary_body(summary: OrderSummary) -> dict[str, Any]:
    return {
        **_order_body(summary.order),
        "subtotal_cents": summary.subtotal_cents,
        "discount_cents": summary.discount_cents,
        "total_cents": summary.total_cents,
    }


class OrderController:
    def __init__(self, service: OrderService) -> None:
        self._service = service

    def handle_create(self, request: dict[str, Any]) -> Response:
        try:
            customer_id = request.get("customer_id")
            if not isinstance(customer_id, str) or not customer_id:
                raise InvalidRequest("customer_id must be a non-empty string")
            items = _decode_items(request.get("items"))
        except InvalidRequest as exc:
            return Response(400, {"error": str(exc)})
        order = self._service.place_order(customer_id, items)
        return Response(201, _order_body(order))

    def handle_get(self, order_id: str) -> Response:
        try:
            summary = self._service.get_order_summary(order_id)
        except OrderNotFound:
            return Response(404, {"error": "order not found"})
        return Response(200, _summary_body(summary))

    def handle_list_for_customer(self, customer_id: str) -> Response:
        orders = self._service.list_for_customer(customer_id)
        return Response(200, {"orders": [_order_body(o) for o in orders]})

    def handle_customer_totals(self, customer_id: str) -> Response:
        totals = self._service.customer_totals(customer_id)
        return Response(200, {"customer_id": customer_id, **totals})
