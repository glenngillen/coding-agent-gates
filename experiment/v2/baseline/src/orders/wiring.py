"""Composition root: the one place that constructs every layer."""

from __future__ import annotations

from dataclasses import dataclass

from orders.application.catalog_service import CatalogService
from orders.application.customer_service import CustomerService
from orders.application.order_service import OrderService
from orders.controllers.catalog import CatalogController
from orders.controllers.customers import CustomerController
from orders.controllers.orders import OrderController
from orders.controllers.reports import ReportsController
from orders.infrastructure.catalog import InMemoryProductCatalog
from orders.infrastructure.customers import InMemoryCustomerRepository
from orders.infrastructure.repository import InMemoryOrderRepository
from orders.infrastructure.stock import InMemoryStockRepository


@dataclass(frozen=True)
class Api:
    customers: CustomerController
    catalog: CatalogController
    orders: OrderController
    reports: ReportsController


def build_app() -> Api:
    orders = InMemoryOrderRepository()
    customers = InMemoryCustomerRepository()
    catalog = InMemoryProductCatalog()
    stock = InMemoryStockRepository()
    return Api(
        customers=CustomerController(CustomerService(customers)),
        catalog=CatalogController(CatalogService(catalog, stock)),
        orders=OrderController(OrderService(orders, customers, catalog, stock)),
        reports=ReportsController(orders),
    )
