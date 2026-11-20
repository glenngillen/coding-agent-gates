"""Frozen acceptance-test support. Runs against a final snapshot, never the baseline package.

The evaluator copies this directory into a fresh work directory and runs it
with ``PYTHONPATH=<snapshot>/src`` and ``EVAL_SNAPSHOT_SRC`` set. The guard
below fails every test if ``orders`` was imported from anywhere else, so a
misconfigured run cannot silently test the wrong code.
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
def app():
    return build_app()


def item(sku="BOOK", quantity=1, unit_price_cents=1000):
    return {"sku": sku, "quantity": quantity, "unit_price_cents": unit_price_cents}


def create(app, customer_id="cust-1", items=None):
    response = app.handle_create({"customer_id": customer_id,
                                  "items": items if items is not None else [item()]})
    assert response.status == 201, response.body
    return response.body
