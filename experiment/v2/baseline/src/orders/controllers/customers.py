"""Customer endpoints."""

from __future__ import annotations

from typing import Any

from orders.application.customer_service import CustomerService
from orders.application.errors import Conflict, CustomerNotFound
from orders.controllers.http import (InvalidRequest, Response, bad_request, conflict, not_found,
                                     require_str)
from orders.domain.customers import TIERS, Customer


def customer_body(customer: Customer) -> dict[str, Any]:
    return {"customer_id": customer.customer_id, "name": customer.name, "email": customer.email,
            "tier": customer.tier}


class CustomerController:
    def __init__(self, service: CustomerService) -> None:
        self._service = service

    def handle_register(self, request: dict[str, Any]) -> Response:
        try:
            customer_id = require_str(request, "customer_id")
            name = require_str(request, "name")
            email = require_str(request, "email")
            tier = request.get("tier", "standard")
            if tier not in TIERS:
                raise InvalidRequest(f"tier must be one of {', '.join(TIERS)}")
        except InvalidRequest as exc:
            return bad_request(exc)
        try:
            customer = self._service.register(customer_id, name, email, tier)
        except Conflict as exc:
            return conflict(exc)
        return Response(201, customer_body(customer))

    def handle_get(self, customer_id: str) -> Response:
        try:
            return Response(200, customer_body(self._service.get(customer_id)))
        except CustomerNotFound:
            return not_found("customer")
