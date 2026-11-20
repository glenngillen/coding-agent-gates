"""In-memory customer repository."""

from __future__ import annotations

from orders.domain.customers import Customer


class InMemoryCustomerRepository:
    def __init__(self) -> None:
        self._customers: dict[str, Customer] = {}

    def add(self, customer: Customer) -> None:
        self._customers[customer.customer_id] = customer

    def get(self, customer_id: str) -> Customer | None:
        return self._customers.get(customer_id)

    def list_all(self) -> list[Customer]:
        return list(self._customers.values())
