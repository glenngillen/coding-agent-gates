from conftest import place


def test_customers_without_orders_in_registration_order(shop):
    place(shop, "c2", ("PEN", 1))
    response = shop.insights.handle_customers_without_orders()
    assert response.status == 200
    assert response.body == {"customers": [
        {"customer_id": "c1", "name": "Ada", "email": "c1@example.com"},
        {"customer_id": "c3", "name": "Linus", "email": "c3@example.com"},
    ]}


def test_a_customer_whose_only_order_was_cancelled_counts_as_without_orders(shop):
    for cid in ("c2", "c3"):
        place(shop, cid, ("PEN", 1))
    cancelled = place(shop, "c1", ("BOOK", 1))
    shop.orders.handle_cancel(cancelled)
    assert [c["customer_id"] for c in shop.insights.handle_customers_without_orders().body["customers"]] == ["c1"]


def test_newly_registered_customers_appear(shop):
    for cid in ("c1", "c2", "c3"):
        place(shop, cid, ("PEN", 1))
    shop.customers.handle_register({"customer_id": "c9", "name": "New", "email": "n@example.com"})
    assert shop.insights.handle_customers_without_orders().body == {"customers": [
        {"customer_id": "c9", "name": "New", "email": "n@example.com"}]}


def test_earlier_endpoints_still_work(shop):
    place(shop, "c2", ("LAMP", 2))
    assert shop.insights.handle_top_customers(1).body["customers"][0]["customer_id"] == "c2"
