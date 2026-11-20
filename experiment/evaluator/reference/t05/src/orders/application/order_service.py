# Reference implementation for T05: evaluator only, never copied into an agent workspace.
# Derived from the baseline module; only the T05 change differs.
"""Order application service.

This module owns business policy (discount eligibility) and is the only layer
that talks to the repository. It imports the repository module directly, which
makes controller -> service -> repository a legal *indirect* dependency for
controllers under the architecture contract.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace

from orders.domain import LineItem, Order, OrderSummary
from orders.infrastructure.repository import InMemoryOrderRepository

DISCOUNT_THRESHOLD_CENTS = 10_000
DISCOUNT_RATE_PERCENT = 10


class OrderNotFound(LookupError):
    """No order exists with the requested id."""


class OrderAlreadyCancelled(ValueError):
    """The order was cancelled before."""


def discount_for(subtotal_cents: int) -> int:
    """Subtotals of $100.00 or more get 10% off, rounded down to the cent."""
    if subtotal_cents < DISCOUNT_THRESHOLD_CENTS:
        return 0
    return subtotal_cents * DISCOUNT_RATE_PERCENT // 100


class OrderService:
    def __init__(self, repository: InMemoryOrderRepository) -> None:
        self._repository = repository

    def place_order(self, customer_id: str, items: Iterable[LineItem]) -> Order:
        order = Order(
            order_id=self._repository.next_id(),
            customer_id=customer_id,
            items=tuple(items),
        )
        self._repository.add(order)
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

    def cancel(self, order_id: str) -> Order:
        order = self.get_order(order_id)
        if order.status == "cancelled":
            raise OrderAlreadyCancelled(order_id)
        cancelled = replace(order, status="cancelled")
        self._repository.add(cancelled)  # add() replaces the stored order with the same id
        return cancelled
