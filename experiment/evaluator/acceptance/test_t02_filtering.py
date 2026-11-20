"""T02 filtering: handle_list_for_customer(customer_id, sku=...)."""

from conftest import create, item


def _ids(response):
    return [o["order_id"] for o in response.body["orders"]]


def test_only_orders_with_the_sku_in_creation_order(app):
    first = create(app, "alice", [item("BOOK"), item("PEN")])
    create(app, "alice", [item("PEN")])
    third = create(app, "alice", [item("BOOK")])
    create(app, "bob", [item("BOOK")])

    response = app.handle_list_for_customer("alice", sku="BOOK")

    assert response.status == 200
    assert _ids(response) == [first["order_id"], third["order_id"]]
    assert response.body["orders"][0] == first


def test_sku_match_is_exact(app):
    create(app, "alice", [item("BOOKS")])

    response = app.handle_list_for_customer("alice", sku="BOOK")

    assert (response.status, response.body) == (200, {"orders": []})


def test_without_sku_the_response_is_unchanged(app):
    a = create(app, "alice", [item("BOOK")])
    b = create(app, "alice", [item("PEN")])

    assert app.handle_list_for_customer("alice").body == {"orders": [a, b]}
