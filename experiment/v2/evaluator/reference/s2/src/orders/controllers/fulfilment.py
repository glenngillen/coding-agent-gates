"""Fulfilment endpoints (reference implementation)."""

from __future__ import annotations

from typing import Any

from orders.application.errors import Conflict, OrderNotFound, ProductNotFound
from orders.application.fulfilment_service import FulfilmentService
from orders.controllers.http import (InvalidRequest, Response, bad_request, conflict, not_found,
                                     require_non_negative_int, require_positive_int, require_str)


class FulfilmentController:
    def __init__(self, service: FulfilmentService) -> None:
        self._service = service

    def handle_packing_slip(self, order_id: str) -> Response:
        try:
            slip = self._service.packing_slip(order_id)
        except OrderNotFound:
            return not_found("order")
        except Conflict as exc:
            return conflict(exc)
        return Response(200, {"order_id": slip.order_id, "customer_name": slip.customer_name, "lines": [
            {"sku": line.sku, "name": line.name, "quantity": line.quantity} for line in slip.lines]})

    def handle_low_stock(self, threshold: Any) -> Response:
        try:
            threshold = require_non_negative_int(threshold, "threshold")
        except InvalidRequest as exc:
            return bad_request(exc)
        return Response(200, {"products": [
            {"sku": p.sku, "name": p.name, "on_hand": n} for p, n in self._service.low_stock(threshold)]})

    def handle_restock(self, request: dict[str, Any]) -> Response:
        try:
            sku = require_str(request, "sku")
            quantity = require_positive_int(request.get("quantity"), "quantity")
        except InvalidRequest as exc:
            return bad_request(exc)
        try:
            level = self._service.restock(sku, quantity)
        except ProductNotFound:
            return not_found("product")
        return Response(200, {"sku": sku, "on_hand": level})

    def handle_fulfilment_summary(self) -> Response:
        s = self._service.summary()
        return Response(200, {"open_orders": s.open_orders, "units_to_pick": s.units_to_pick,
                              "low_stock_products": s.low_stock_products})
