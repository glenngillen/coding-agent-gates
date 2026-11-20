"""Customer insights: order history and lifetime value (reference implementation)."""

from __future__ import annotations

from dataclasses import dataclass

from orders.application.errors import CustomerNotFound
from orders.application.order_service import OrderService
from orders.domain.customers import Customer
from orders.domain.orders import OrderSummary
from orders.infrastructure.customers import InMemoryCustomerRepository
from orders.infrastructure.repository import InMemoryOrderRepository


@dataclass(frozen=True)
class LifetimeValue:
    customer: Customer
    order_count: int
    value_cents: int


class InsightsService:
    def __init__(self, orders: InMemoryOrderRepository, customers: InMemoryCustomerRepository,
                 order_service: OrderService) -> None:
        self._orders = orders
        self._customers = customers
        self._order_service = order_service

    def _customer(self, customer_id: str) -> Customer:
        customer = self._customers.get(customer_id)
        if customer is None:
            raise CustomerNotFound(customer_id)
        return customer

    def history(self, customer_id: str) -> list[OrderSummary]:
        self._customer(customer_id)
        orders = self._orders.list_for_customer(customer_id)
        return [self._order_service.summarize(o) for o in reversed(orders)]

    def _value(self, customer: Customer) -> LifetimeValue:
        live = [self._order_service.summarize(o) for o in self._orders.list_for_customer(customer.customer_id)
                if o.status != "cancelled"]
        return LifetimeValue(customer, len(live), sum(s.total_cents for s in live))

    def lifetime_value(self, customer_id: str) -> LifetimeValue:
        return self._value(self._customer(customer_id))

    def top_customers(self, limit: int) -> list[LifetimeValue]:
        values = [v for v in (self._value(c) for c in self._customers.list_all()) if v.value_cents > 0]
        values.sort(key=lambda v: (-v.value_cents, v.customer.customer_id))
        return values[:limit]

    def customers_without_orders(self) -> list[Customer]:
        return [c for c in self._customers.list_all() if self._value(c).order_count == 0]
