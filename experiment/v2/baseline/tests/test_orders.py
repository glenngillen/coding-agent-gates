def order(api, customer_id="c1", *items):
    return api.orders.handle_create({"customer_id": customer_id,
                                     "items": [{"sku": s, "quantity": q} for s, q in items]})


def test_place_order_uses_catalogue_prices(shop):
    response = order(shop, "c1", ("BOOK", 2))
    assert response.status == 201
    assert response.body["items"] == [{"sku": "BOOK", "quantity": 2, "unit_price_cents": 2500}]
    assert response.body["order_id"] == "ord-0001"


def test_summary_applies_standard_and_gold_discounts(shop):
    standard = order(shop, "c1", ("LAMP", 2)).body["order_id"]
    gold = order(shop, "c2", ("LAMP", 2)).body["order_id"]
    assert shop.orders.handle_get(standard).body["discount_cents"] == 1200
    assert shop.orders.handle_get(gold).body["discount_cents"] == 1800
    assert shop.orders.handle_get(gold).body["total_cents"] == 10200


def test_no_discount_below_threshold(shop):
    oid = order(shop, "c1", ("BOOK", 3)).body["order_id"]
    assert shop.orders.handle_get(oid).body["discount_cents"] == 0


def test_stock_is_checked_and_decremented(shop):
    assert order(shop, "c1", ("LAMP", 6)).status == 409
    order(shop, "c1", ("LAMP", 5))
    assert shop.catalog.handle_get("LAMP").body["on_hand"] == 0


def test_cancel_restores_stock(shop):
    oid = order(shop, "c1", ("LAMP", 2)).body["order_id"]
    assert shop.orders.handle_cancel(oid).body["status"] == "cancelled"
    assert shop.catalog.handle_get("LAMP").body["on_hand"] == 5
    assert shop.orders.handle_cancel(oid).status == 409


def test_errors(shop):
    assert order(shop, "nobody", ("BOOK", 1)).status == 404
    assert order(shop, "c1", ("NOPE", 1)).status == 400
    assert shop.orders.handle_create({"customer_id": "c1", "items": []}).status == 400
    assert shop.orders.handle_get("ord-9999").status == 404
    assert shop.orders.handle_list_for_customer("nobody").status == 404


def test_list_for_customer_in_creation_order(shop):
    first = order(shop, "c1", ("BOOK", 1)).body["order_id"]
    order(shop, "c2", ("PEN", 1))
    second = order(shop, "c1", ("PEN", 2)).body["order_id"]
    body = shop.orders.handle_list_for_customer("c1").body
    assert [o["order_id"] for o in body["orders"]] == [first, second]
