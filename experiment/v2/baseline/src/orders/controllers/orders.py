"""Order endpoints."""

from __future__ import annotations

from typing import Any

from orders.application.errors import Conflict, CustomerNotFound, OrderNotFound, ProductNotFound
from orders.application.order_service import OrderService
from orders.controllers.http import (InvalidRequest, Response, bad_request, conflict, not_found,
                                     require_positive_int, require_str)
from orders.domain.orders import Order, OrderSummary


def decode_items(raw: Any) -> list[tuple[str, int]]:
    if not isinstance(raw, list) or not raw:
        raise InvalidRequest("items must be a non-empty list")
    items = []
    for entry in raw:
        if not isinstance(entry, dict):
            raise InvalidRequest("each item must be an object")
        items.append((require_str(entry, "sku"), require_positive_int(entry.get("quantity"), "quantity")))
    return items


def order_body(order: Order) -> dict[str, Any]:
    return {
        "order_id": order.order_id,
        "customer_id": order.customer_id,
        "status": order.status,
        "items": [{"sku": i.sku, "quantity": i.quantity, "unit_price_cents": i.unit_price_cents}
                  for i in order.items],
    }


def summary_body(summary: OrderSummary) -> dict[str, Any]:
    return {**order_body(summary.order), "subtotal_cents": summary.subtotal_cents,
            "discount_cents": summary.discount_cents, "total_cents": summary.total_cents}


class OrderController:
    def __init__(self, service: OrderService) -> None:
        self._service = service

    def handle_create(self, request: dict[str, Any]) -> Response:
        try:
            customer_id = require_str(request, "customer_id")
            items = decode_items(request.get("items"))
        except InvalidRequest as exc:
            return bad_request(exc)
        try:
            order = self._service.place_order(customer_id, items)
        except CustomerNotFound:
            return not_found("customer")
        except ProductNotFound as exc:
            return bad_request(InvalidRequest(f"unknown product {exc.args[0]}"))
        except Conflict as exc:
            return conflict(exc)
        return Response(201, order_body(order))

    def handle_get(self, order_id: str) -> Response:
        try:
            return Response(200, summary_body(self._service.get_order_summary(order_id)))
        except OrderNotFound:
            return not_found("order")

    def handle_list_for_customer(self, customer_id: str) -> Response:
        try:
            orders = self._service.list_for_customer(customer_id)
        except CustomerNotFound:
            return not_found("customer")
        return Response(200, {"orders": [order_body(o) for o in orders]})

    def handle_cancel(self, order_id: str) -> Response:
        try:
            order = self._service.cancel_order(order_id)
        except OrderNotFound:
            return not_found("order")
        except Conflict as exc:
            return conflict(exc)
        return Response(200, order_body(order))
