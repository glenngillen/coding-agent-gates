"""In-memory stock levels, keyed by SKU."""

from __future__ import annotations


class InMemoryStockRepository:
    def __init__(self) -> None:
        self._on_hand: dict[str, int] = {}

    def get(self, sku: str) -> int:
        return self._on_hand.get(sku, 0)

    def set(self, sku: str, on_hand: int) -> None:
        self._on_hand[sku] = on_hand

    def all_levels(self) -> dict[str, int]:
        return dict(self._on_hand)
