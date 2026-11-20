"""T05 cancellation: handle_cancel(order_id)."""

from conftest import create


def test_placed_order_is_cancelled_and_reads_show_it(app):
    order = create(app, "alice")

    response = app.handle_cancel(order["order_id"])

    assert response.status == 200
    assert response.body == {**order, "status": "cancelled"}
    assert app.handle_get(order["order_id"]).body["status"] == "cancelled"
    assert app.handle_list_for_customer("alice").body["orders"][0]["status"] == "cancelled"


def test_cancelling_twice_is_a_conflict_and_changes_nothing(app):
    order = create(app, "alice")
    app.handle_cancel(order["order_id"])

    response = app.handle_cancel(order["order_id"])

    assert (response.status, response.body) == (409, {"error": "order already cancelled"})
    assert app.handle_get(order["order_id"]).body["status"] == "cancelled"


def test_unknown_order_is_not_found(app):
    response = app.handle_cancel("ord-9999")

    assert (response.status, response.body) == (404, {"error": "order not found"})


def test_other_orders_are_unaffected(app):
    first = create(app, "alice")
    second = create(app, "alice")

    app.handle_cancel(first["order_id"])

    assert app.handle_get(second["order_id"]).body["status"] == "placed"
