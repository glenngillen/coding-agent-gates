def order(api, customer_id, *items):
    return api.orders.handle_create({"customer_id": customer_id,
                                     "items": [{"sku": s, "quantity": q} for s, q in items]})


def test_order_counts(shop):
    order(shop, "c1", ("BOOK", 1))
    cancelled = order(shop, "c1", ("PEN", 1)).body["order_id"]
    shop.orders.handle_cancel(cancelled)
    assert shop.reports.handle_order_counts().body == {"counts": {"cancelled": 1, "placed": 1}}


def test_units_by_sku_ignores_cancelled_orders(shop):
    order(shop, "c1", ("BOOK", 2), ("PEN", 1))
    order(shop, "c2", ("BOOK", 1))
    cancelled = order(shop, "c2", ("PEN", 5)).body["order_id"]
    shop.orders.handle_cancel(cancelled)
    assert shop.reports.handle_units_by_sku().body == {"units": {"BOOK": 3, "PEN": 1}}
