"""Customer data."""

from __future__ import annotations

from dataclasses import dataclass

TIERS = ("standard", "gold")


@dataclass(frozen=True)
class Customer:
    customer_id: str
    name: str
    email: str
    tier: str = "standard"
