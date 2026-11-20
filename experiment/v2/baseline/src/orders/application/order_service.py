"""Order placement, lookup and cancellation.

Prices come from the catalogue, stock is checked and decremented when an
order is placed, and restored when it is cancelled.
"""

from __future__ import annotations

from collections.abc import Iterable

from orders.application.errors import Conflict, CustomerNotFound, OrderNotFound, ProductNotFound
from orders.application.pricing import discount_for
from orders.domain.orders import LineItem, Order, OrderSummary
from orders.infrastructure.catalog import InMemoryProductCatalog
from orders.infrastructure.customers import InMemoryCustomerRepository
from orders.infrastructure.repository import InMemoryOrderRepository
from orders.infrastructure.stock import InMemoryStockRepository


class OrderService:
    def __init__(self, orders: InMemoryOrderRepository, customers: InMemoryCustomerRepository,
                 catalog: InMemoryProductCatalog, stock: InMemoryStockRepository) -> None:
        self._orders = orders
        self._customers = customers
        self._catalog = catalog
        self._stock = stock

    def place_order(self, customer_id: str, requested: Iterable[tuple[str, int]]) -> Order:
        """Place an order for ``(sku, quantity)`` pairs at current catalogue prices."""
        if self._customers.get(customer_id) is None:
            raise CustomerNotFound(customer_id)
        items = []
        for sku, quantity in requested:
            product = self._catalog.get(sku)
            if product is None or not product.active:
                raise ProductNotFound(sku)
            if self._stock.get(sku) < quantity:
                raise Conflict(f"insufficient stock for {sku}")
            items.append(LineItem(sku, quantity, product.unit_price_cents))
        for item in items:
            self._stock.set(item.sku, self._stock.get(item.sku) - item.quantity)
        order = Order(self._orders.next_id(), customer_id, tuple(items))
        self._orders.add(order)
        return order

    def get_order(self, order_id: str) -> Order:
        order = self._orders.get(order_id)
        if order is None:
            raise OrderNotFound(order_id)
        return order

    def summarize(self, order: Order) -> OrderSummary:
        customer = self._customers.get(order.customer_id)
        tier = customer.tier if customer is not None else "standard"
        subtotal = order.subtotal_cents
        discount = discount_for(subtotal, tier)
        return OrderSummary(order, subtotal, discount, subtotal - discount)

    def get_order_summary(self, order_id: str) -> OrderSummary:
        return self.summarize(self.get_order(order_id))

    def list_for_customer(self, customer_id: str) -> list[Order]:
        if self._customers.get(customer_id) is None:
            raise CustomerNotFound(customer_id)
        return self._orders.list_for_customer(customer_id)

    def cancel_order(self, order_id: str) -> Order:
        order = self.get_order(order_id)
        if order.status == "cancelled":
            raise Conflict(f"order {order_id} is already cancelled")
        for item in order.items:
            self._stock.set(item.sku, self._stock.get(item.sku) + item.quantity)
        return self._orders.set_status(order_id, "cancelled")
