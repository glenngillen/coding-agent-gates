"""Composition root: the one place that constructs every layer.

Importing the repository here is legal; the contract restricts controller
modules only.
"""

from __future__ import annotations

from orders.application.order_service import OrderService
from orders.controllers.orders import OrderController
from orders.infrastructure.repository import InMemoryOrderRepository


def build_app() -> OrderController:
    return OrderController(OrderService(InMemoryOrderRepository()))
