"""In-memory product catalogue."""

from __future__ import annotations

from orders.domain.catalog import Product


class InMemoryProductCatalog:
    def __init__(self) -> None:
        self._products: dict[str, Product] = {}

    def add(self, product: Product) -> None:
        self._products[product.sku] = product

    def get(self, sku: str) -> Product | None:
        return self._products.get(sku)

    def list_all(self) -> list[Product]:
        return list(self._products.values())
