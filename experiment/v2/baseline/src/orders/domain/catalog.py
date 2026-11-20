"""Catalogue data."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Product:
    sku: str
    name: str
    unit_price_cents: int
    active: bool = True
