"""In-memory order repository."""

from __future__ import annotations

from dataclasses import replace

from orders.domain.orders import Order


class InMemoryOrderRepository:
    def __init__(self) -> None:
        self._orders: dict[str, Order] = {}
        self._next_id = 1

    def next_id(self) -> str:
        order_id = f"ord-{self._next_id:04d}"
        self._next_id += 1
        return order_id

    def add(self, order: Order) -> None:
        self._orders[order.order_id] = order

    def get(self, order_id: str) -> Order | None:
        return self._orders.get(order_id)

    def set_status(self, order_id: str, status: str) -> Order:
        order = replace(self._orders[order_id], status=status)
        self._orders[order_id] = order
        return order

    def list_for_customer(self, customer_id: str) -> list[Order]:
        # dicts preserve insertion order, so this is creation order.
        return [o for o in self._orders.values() if o.customer_id == customer_id]

    def list_all(self) -> list[Order]:
        return list(self._orders.values())
