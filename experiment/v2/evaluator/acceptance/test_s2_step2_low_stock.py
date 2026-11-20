import pytest
from conftest import place


def test_low_stock_lists_products_under_the_threshold(shop):
    place(shop, "c1", ("LAMP", 4))                  # LAMP 5 -> 1
    response = shop.fulfilment.handle_low_stock(3)
    assert response.status == 200
    assert response.body == {"products": [
        {"sku": "LAMP", "name": "Desk lamp", "on_hand": 1},
        {"sku": "MUG", "name": "Mug", "on_hand": 2},
    ]}


def test_ties_are_ordered_by_sku_and_the_threshold_is_exclusive(shop):
    place(shop, "c1", ("LAMP", 3))                  # LAMP 2, MUG 2
    assert [p["sku"] for p in shop.fulfilment.handle_low_stock(2).body["products"]] == []
    assert [p["sku"] for p in shop.fulfilment.handle_low_stock(3).body["products"]] == ["LAMP", "MUG"]


@pytest.mark.parametrize("threshold", [-1, "3", None, 1.5, False])
def test_invalid_threshold_is_400(shop, threshold):
    assert shop.fulfilment.handle_low_stock(threshold).status == 400


def test_packing_slip_still_works(shop):
    oid = place(shop, "c1", ("MUG", 1))
    assert shop.fulfilment.handle_packing_slip(oid).body["lines"] == [{"sku": "MUG", "name": "Mug", "quantity": 1}]
