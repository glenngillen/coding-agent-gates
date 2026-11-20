"""Frozen version 2 acceptance-test support. Runs against a snapshot, never this package.

The v2 evaluator copies this file and the selected step tests into a fresh work
directory and runs them with ``PYTHONPATH=<snapshot>/src`` and
``EVAL_SNAPSHOT_SRC`` set. The guard fails every test if ``orders`` was
imported from anywhere else.
"""

import os
from pathlib import Path

import pytest

import orders
from orders.wiring import build_app

_EXPECTED = os.environ.get("EVAL_SNAPSHOT_SRC")


@pytest.fixture(autouse=True)
def _snapshot_guard():
    assert _EXPECTED, "EVAL_SNAPSHOT_SRC is not set: run through the evaluator"
    imported = Path(orders.__file__).resolve()
    assert Path(_EXPECTED).resolve() in imported.parents, f"orders imported from {imported}"


@pytest.fixture
def shop():
    """Three customers (one gold) and four products, as the baseline tests set them up."""
    api = build_app()
    for cid, name, tier in (("c1", "Ada", "standard"), ("c2", "Grace", "gold"), ("c3", "Linus", "standard")):
        assert api.customers.handle_register(
            {"customer_id": cid, "name": name, "email": f"{cid}@example.com", "tier": tier}).status == 201
    for sku, name, price, on_hand in (("BOOK", "Book", 2_500, 50), ("LAMP", "Desk lamp", 6_000, 5),
                                      ("PEN", "Pen", 300, 100), ("MUG", "Mug", 1_200, 2)):
        assert api.catalog.handle_add_product(
            {"sku": sku, "name": name, "unit_price_cents": price, "on_hand": on_hand}).status == 201
    return api


def place(api, customer_id, *items):
    response = api.orders.handle_create(
        {"customer_id": customer_id, "items": [{"sku": s, "quantity": q} for s, q in items]})
    assert response.status == 201, response.body
    return response.body["order_id"]
