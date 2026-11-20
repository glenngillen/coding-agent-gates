import pytest
from conftest import place


def test_restock_adds_to_stock_and_reports_the_new_level(shop):
    response = shop.fulfilment.handle_restock({"sku": "MUG", "quantity": 10})
    assert response.status == 200
    assert response.body == {"sku": "MUG", "on_hand": 12}
    assert shop.catalog.handle_get("MUG").body["on_hand"] == 12


def test_restocked_items_can_be_ordered_and_leave_low_stock(shop):
    shop.fulfilment.handle_restock({"sku": "LAMP", "quantity": 5})
    place(shop, "c1", ("LAMP", 8))
    assert [p["sku"] for p in shop.fulfilment.handle_low_stock(3).body["products"]] == ["LAMP", "MUG"]
    shop.fulfilment.handle_restock({"sku": "MUG", "quantity": 1})
    assert [p["sku"] for p in shop.fulfilment.handle_low_stock(3).body["products"]] == ["LAMP"]


def test_unknown_product_is_404(shop):
    response = shop.fulfilment.handle_restock({"sku": "NOPE", "quantity": 1})
    assert response.status == 404
    assert response.body == {"error": "product not found"}


@pytest.mark.parametrize("request_body", [
    {"sku": "MUG", "quantity": 0}, {"sku": "MUG", "quantity": -2}, {"sku": "MUG", "quantity": "5"},
    {"sku": "MUG"}, {"quantity": 1}, {"sku": "", "quantity": 1}, {"sku": "MUG", "quantity": True},
])
def test_invalid_restock_is_400_and_changes_nothing(shop, request_body):
    assert shop.fulfilment.handle_restock(request_body).status == 400
    assert shop.catalog.handle_get("MUG").body["on_hand"] == 2
