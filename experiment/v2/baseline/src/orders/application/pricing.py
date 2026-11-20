"""Pricing policy: discount eligibility and amounts."""

from __future__ import annotations

DISCOUNT_THRESHOLD_CENTS = 10_000
STANDARD_DISCOUNT_PERCENT = 10
GOLD_DISCOUNT_PERCENT = 15


def discount_for(subtotal_cents: int, tier: str = "standard") -> int:
    """Subtotals of $100.00 or more get 10% off (15% for gold customers), rounded down."""
    if subtotal_cents < DISCOUNT_THRESHOLD_CENTS:
        return 0
    percent = GOLD_DISCOUNT_PERCENT if tier == "gold" else STANDARD_DISCOUNT_PERCENT
    return subtotal_cents * percent // 100
