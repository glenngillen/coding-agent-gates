"""Customer insight endpoints (reference implementation)."""

from __future__ import annotations

from typing import Any

from orders.application.errors import CustomerNotFound
from orders.application.insights_service import InsightsService
from orders.controllers.http import InvalidRequest, Response, bad_request, not_found, require_positive_int


class CustomerInsightsController:
    def __init__(self, service: InsightsService) -> None:
        self._service = service

    def handle_order_history(self, customer_id: str) -> Response:
        try:
            summaries = self._service.history(customer_id)
        except CustomerNotFound:
            return not_found("customer")
        return Response(200, {"customer_id": customer_id, "orders": [
            {"order_id": s.order.order_id, "status": s.order.status, "total_cents": s.total_cents}
            for s in summaries]})

    def handle_lifetime_value(self, customer_id: str) -> Response:
        try:
            value = self._service.lifetime_value(customer_id)
        except CustomerNotFound:
            return not_found("customer")
        return Response(200, {"customer_id": customer_id, "order_count": value.order_count,
                              "lifetime_value_cents": value.value_cents})

    def handle_top_customers(self, limit: Any) -> Response:
        try:
            limit = require_positive_int(limit, "limit")
        except InvalidRequest as exc:
            return bad_request(exc)
        return Response(200, {"customers": [
            {"customer_id": v.customer.customer_id, "name": v.customer.name,
             "lifetime_value_cents": v.value_cents}
            for v in self._service.top_customers(limit)]})

    def handle_customers_without_orders(self) -> Response:
        return Response(200, {"customers": [
            {"customer_id": c.customer_id, "name": c.name, "email": c.email}
            for c in self._service.customers_without_orders()]})
