from conftest import place


def test_packing_slip_lists_product_names_and_quantities(shop):
    oid = place(shop, "c2", ("LAMP", 1), ("PEN", 3))
    response = shop.fulfilment.handle_packing_slip(oid)
    assert response.status == 200
    assert response.body == {"order_id": oid, "customer_name": "Grace", "lines": [
        {"sku": "LAMP", "name": "Desk lamp", "quantity": 1},
        {"sku": "PEN", "name": "Pen", "quantity": 3},
    ]}


def test_cancelled_order_has_no_packing_slip(shop):
    oid = place(shop, "c1", ("BOOK", 1))
    shop.orders.handle_cancel(oid)
    response = shop.fulfilment.handle_packing_slip(oid)
    assert response.status == 409
    assert "error" in response.body


def test_unknown_order_is_404(shop):
    response = shop.fulfilment.handle_packing_slip("ord-9999")
    assert response.status == 404
    assert response.body == {"error": "order not found"}
