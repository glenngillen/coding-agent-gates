# Reference implementation for T09: evaluator only, never copied into an agent workspace.
# Derived from the baseline module; only the T09 change differs.
"""Order application service.

This module owns business policy (discount eligibility) and is the only layer
that talks to the repository. It imports the repository module directly, which
makes controller -> service -> repository a legal *indirect* dependency for
controllers under the architecture contract.
"""

from __future__ import annotations

from collections.abc import Iterable

from orders.domain import LineItem, Order, OrderSummary
from orders.infrastructure.repository import InMemoryOrderRepository

DISCOUNT_THRESHOLD_CENTS = 10_000
DISCOUNT_RATE_PERCENT = 10


class OrderNotFound(LookupError):
    """No order exists with the requested id."""


def discount_for(subtotal_cents: int) -> int:
    """Subtotals of $100.00 or more get 10% off, rounded down to the cent."""
    if subtotal_cents < DISCOUNT_THRESHOLD_CENTS:
        return 0
    return subtotal_cents * DISCOUNT_RATE_PERCENT // 100


class OrderService:
    def __init__(self, repository: InMemoryOrderRepository) -> None:
        self._repository = repository
        self._audit: list[dict] = []  # per application instance

    def _record(self, event: str, **fields) -> None:
        self._audit.append({"sequence": len(self._audit) + 1, "event": event, **fields})

    def place_order(self, customer_id: str, items: Iterable[LineItem]) -> Order:
        order = Order(
            order_id=self._repository.next_id(),
            customer_id=customer_id,
            items=tuple(items),
        )
        self._repository.add(order)
        total = self.get_order_summary(order.order_id).total_cents
        self._record("order_placed", order_id=order.order_id, customer_id=customer_id, total_cents=total)
        return order

    def get_order(self, order_id: str) -> Order:
        order = self._repository.get(order_id)
        if order is None:
            raise OrderNotFound(order_id)
        return order

    def get_order_summary(self, order_id: str) -> OrderSummary:
        order = self.get_order(order_id)
        subtotal = order.subtotal_cents
        discount = discount_for(subtotal)
        return OrderSummary(
            order=order,
            subtotal_cents=subtotal,
            discount_cents=discount,
            total_cents=subtotal - discount,
        )

    def list_for_customer(self, customer_id: str) -> list[Order]:
        return self._repository.list_for_customer(customer_id)

    def view_order_summary(self, order_id: str) -> OrderSummary:
        summary = self.get_order_summary(order_id)
        self._record("order_viewed", order_id=order_id)
        return summary

    def audit_events(self) -> list[dict]:
        return [dict(event) for event in self._audit]
