"""Customer registration and lookup."""

from __future__ import annotations

from orders.application.errors import Conflict, CustomerNotFound
from orders.domain.customers import TIERS, Customer
from orders.infrastructure.customers import InMemoryCustomerRepository


class CustomerService:
    def __init__(self, customers: InMemoryCustomerRepository) -> None:
        self._customers = customers

    def register(self, customer_id: str, name: str, email: str, tier: str = "standard") -> Customer:
        if tier not in TIERS:
            raise ValueError(f"unknown tier {tier!r}")
        if self._customers.get(customer_id) is not None:
            raise Conflict(f"customer {customer_id} already exists")
        customer = Customer(customer_id, name, email, tier)
        self._customers.add(customer)
        return customer

    def get(self, customer_id: str) -> Customer:
        customer = self._customers.get(customer_id)
        if customer is None:
            raise CustomerNotFound(customer_id)
        return customer
