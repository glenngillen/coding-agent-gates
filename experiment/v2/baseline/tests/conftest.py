import pytest

from orders.wiring import build_app


@pytest.fixture
def api():
    return build_app()


@pytest.fixture
def shop(api):
    """An app with two customers and three products in stock."""
    api.customers.handle_register({"customer_id": "c1", "name": "Ada", "email": "ada@example.com"})
    api.customers.handle_register({"customer_id": "c2", "name": "Grace", "email": "grace@example.com",
                                   "tier": "gold"})
    api.catalog.handle_add_product({"sku": "BOOK", "name": "Book", "unit_price_cents": 2_500, "on_hand": 50})
    api.catalog.handle_add_product({"sku": "LAMP", "name": "Lamp", "unit_price_cents": 6_000, "on_hand": 5})
    api.catalog.handle_add_product({"sku": "PEN", "name": "Pen", "unit_price_cents": 300, "on_hand": 100})
    return api
