"""Catalogue endpoints."""

from __future__ import annotations

from typing import Any

from orders.application.catalog_service import CatalogService
from orders.application.errors import Conflict, ProductNotFound
from orders.controllers.http import (InvalidRequest, Response, bad_request, conflict, not_found,
                                     require_non_negative_int, require_str)
from orders.domain.catalog import Product


def product_body(product: Product) -> dict[str, Any]:
    return {"sku": product.sku, "name": product.name, "unit_price_cents": product.unit_price_cents,
            "active": product.active}


class CatalogController:
    def __init__(self, service: CatalogService) -> None:
        self._service = service

    def handle_add_product(self, request: dict[str, Any]) -> Response:
        try:
            sku = require_str(request, "sku")
            name = require_str(request, "name")
            price = require_non_negative_int(request.get("unit_price_cents"), "unit_price_cents")
            on_hand = require_non_negative_int(request.get("on_hand", 0), "on_hand")
        except InvalidRequest as exc:
            return bad_request(exc)
        try:
            product = self._service.add_product(sku, name, price, on_hand)
        except Conflict as exc:
            return conflict(exc)
        return Response(201, {**product_body(product), "on_hand": on_hand})

    def handle_get(self, sku: str) -> Response:
        try:
            product = self._service.get_product(sku)
        except ProductNotFound:
            return not_found("product")
        return Response(200, {**product_body(product), "on_hand": self._service.on_hand(sku)})

    def handle_list(self) -> Response:
        return Response(200, {"products": [product_body(p) for p in self._service.list_active()]})
