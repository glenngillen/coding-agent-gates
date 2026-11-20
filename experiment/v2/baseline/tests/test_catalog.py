def test_add_and_get_product(api):
    assert api.catalog.handle_add_product({"sku": "BOOK", "name": "Book", "unit_price_cents": 2500,
                                           "on_hand": 3}).status == 201
    assert api.catalog.handle_get("BOOK").body == {"sku": "BOOK", "name": "Book",
                                                   "unit_price_cents": 2500, "active": True, "on_hand": 3}


def test_list_products(shop):
    assert [p["sku"] for p in shop.catalog.handle_list().body["products"]] == ["BOOK", "LAMP", "PEN"]


def test_invalid_and_duplicate_products(api):
    assert api.catalog.handle_add_product({"sku": "X", "name": "X", "unit_price_cents": -1}).status == 400
    api.catalog.handle_add_product({"sku": "X", "name": "X", "unit_price_cents": 1})
    assert api.catalog.handle_add_product({"sku": "X", "name": "X", "unit_price_cents": 1}).status == 409


def test_unknown_product(api):
    assert api.catalog.handle_get("NOPE").status == 404
