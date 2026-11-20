from conftest import place


def test_summary_counts_open_orders_units_and_low_stock_products(shop):
    place(shop, "c1", ("BOOK", 2), ("PEN", 3))
    place(shop, "c2", ("LAMP", 1))
    cancelled = place(shop, "c3", ("PEN", 10))
    shop.orders.handle_cancel(cancelled)
    response = shop.fulfilment.handle_fulfilment_summary()
    assert response.status == 200
    # LAMP 4 and MUG 2 are under the low-stock line of 5 units; BOOK 48 and PEN 97 are not.
    assert response.body == {"open_orders": 2, "units_to_pick": 6, "low_stock_products": 2}


def test_summary_of_an_empty_shop(shop):
    assert shop.fulfilment.handle_fulfilment_summary().body == {
        "open_orders": 0, "units_to_pick": 0, "low_stock_products": 1}


def test_restocking_changes_the_low_stock_count(shop):
    shop.fulfilment.handle_restock({"sku": "MUG", "quantity": 3})
    assert shop.fulfilment.handle_fulfilment_summary().body["low_stock_products"] == 0
