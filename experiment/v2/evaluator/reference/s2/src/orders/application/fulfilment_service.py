"""Fulfilment: packing slips, stock levels and the warehouse summary (reference implementation)."""

from __future__ import annotations

from dataclasses import dataclass

from orders.application.errors import Conflict, OrderNotFound, ProductNotFound
from orders.domain.catalog import Product
from orders.infrastructure.catalog import InMemoryProductCatalog
from orders.infrastructure.customers import InMemoryCustomerRepository
from orders.infrastructure.repository import InMemoryOrderRepository
from orders.infrastructure.stock import InMemoryStockRepository

LOW_STOCK_LINE = 5


@dataclass(frozen=True)
class SlipLine:
    sku: str
    name: str
    quantity: int


@dataclass(frozen=True)
class PackingSlip:
    order_id: str
    customer_name: str
    lines: tuple[SlipLine, ...]


@dataclass(frozen=True)
class FulfilmentSummary:
    open_orders: int
    units_to_pick: int
    low_stock_products: int


class FulfilmentService:
    def __init__(self, orders: InMemoryOrderRepository, customers: InMemoryCustomerRepository,
                 catalog: InMemoryProductCatalog, stock: InMemoryStockRepository) -> None:
        self._orders = orders
        self._customers = customers
        self._catalog = catalog
        self._stock = stock

    def packing_slip(self, order_id: str) -> PackingSlip:
        order = self._orders.get(order_id)
        if order is None:
            raise OrderNotFound(order_id)
        if order.status == "cancelled":
            raise Conflict(f"order {order_id} is cancelled")
        customer = self._customers.get(order.customer_id)
        lines = []
        for item in order.items:
            product = self._catalog.get(item.sku)
            lines.append(SlipLine(item.sku, product.name if product else item.sku, item.quantity))
        return PackingSlip(order_id, customer.name if customer else order.customer_id, tuple(lines))

    def low_stock(self, threshold: int) -> list[tuple[Product, int]]:
        found = [(p, self._stock.get(p.sku)) for p in self._catalog.list_all() if p.active]
        low = [(p, n) for p, n in found if n < threshold]
        return sorted(low, key=lambda pair: (pair[1], pair[0].sku))

    def restock(self, sku: str, quantity: int) -> int:
        if self._catalog.get(sku) is None:
            raise ProductNotFound(sku)
        level = self._stock.get(sku) + quantity
        self._stock.set(sku, level)
        return level

    def summary(self) -> FulfilmentSummary:
        live = [o for o in self._orders.list_all() if o.status != "cancelled"]
        return FulfilmentSummary(
            open_orders=len(live),
            units_to_pick=sum(i.quantity for o in live for i in o.items),
            low_stock_products=len(self.low_stock(LOW_STOCK_LINE)),
        )
