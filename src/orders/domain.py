"""Plain domain data shared by every layer. Money is integer cents."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LineItem:
    sku: str
    quantity: int
    unit_price_cents: int

    @property
    def line_total_cents(self) -> int:
        return self.quantity * self.unit_price_cents


@dataclass(frozen=True)
class Order:
    order_id: str
    customer_id: str
    items: tuple[LineItem, ...]
    status: str = "placed"

    @property
    def subtotal_cents(self) -> int:
        return sum(item.line_total_cents for item in self.items)


@dataclass(frozen=True)
class OrderSummary:
    order: Order
    subtotal_cents: int
    discount_cents: int
    total_cents: int
