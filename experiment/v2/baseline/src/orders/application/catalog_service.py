"""Catalogue management and stock."""

from __future__ import annotations

from orders.application.errors import Conflict, ProductNotFound
from orders.domain.catalog import Product
from orders.infrastructure.catalog import InMemoryProductCatalog
from orders.infrastructure.stock import InMemoryStockRepository


class CatalogService:
    def __init__(self, catalog: InMemoryProductCatalog, stock: InMemoryStockRepository) -> None:
        self._catalog = catalog
        self._stock = stock

    def add_product(self, sku: str, name: str, unit_price_cents: int, on_hand: int = 0) -> Product:
        if self._catalog.get(sku) is not None:
            raise Conflict(f"product {sku} already exists")
        product = Product(sku, name, unit_price_cents)
        self._catalog.add(product)
        self._stock.set(sku, on_hand)
        return product

    def get_product(self, sku: str) -> Product:
        product = self._catalog.get(sku)
        if product is None:
            raise ProductNotFound(sku)
        return product

    def list_active(self) -> list[Product]:
        return [p for p in self._catalog.list_all() if p.active]

    def on_hand(self, sku: str) -> int:
        self.get_product(sku)
        return self._stock.get(sku)
