# Reference implementation for T08: evaluator only, never copied into an agent workspace.
# Derived from the baseline module; only the T08 change differs.
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
NEXT_STATUS = {"placed": "paid", "paid": "shipped", "shipped": "delivered"}
STATUSES = ("placed", "paid", "shipped", "delivered")


class OrderNotFound(LookupError):
    """No order exists with the requested id."""


class UnknownStatus(ValueError):
    """The requested status is not one of STATUSES."""


class InvalidStatusChange(ValueError):
    """The requested status is not the order's next step."""


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

    def change_status(self, order_id: str, status: str) -> Order:
        if status not in STATUSES:
            raise UnknownStatus(status)
        order = self.get_order(order_id)
        if NEXT_STATUS.get(order.status) != status:
            raise InvalidStatusChange(f"cannot change status from {order.status} to {status}")
        updated = replace(order, status=status)
        self._repository.add(updated)
        return updated
