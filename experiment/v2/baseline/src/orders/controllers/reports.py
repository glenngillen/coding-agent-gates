"""Operational reports for the back office."""

from __future__ import annotations

from collections import Counter

from orders.controllers.http import Response
from orders.infrastructure.repository import InMemoryOrderRepository


class ReportsController:
    def __init__(self, orders: InMemoryOrderRepository) -> None:
        self._orders = orders

    def handle_order_counts(self) -> Response:
        """How many orders exist in each status."""
        counts = Counter(order.status for order in self._orders.list_all())
        return Response(200, {"counts": {status: counts[status] for status in sorted(counts)}})

    def handle_units_by_sku(self) -> Response:
        """Units ordered per SKU across all orders that are not cancelled."""
        units: Counter[str] = Counter()
        for order in self._orders.list_all():
            if order.status != "cancelled":
                for item in order.items:
                    units[item.sku] += item.quantity
        return Response(200, {"units": {sku: units[sku] for sku in sorted(units)}})
