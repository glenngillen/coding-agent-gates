"""T08 status updates: handle_update_status(order_id, request)."""

import pytest

from conftest import create


def test_order_moves_forward_one_step_at_a_time(app):
    order = create(app, "alice")

    for status in ("paid", "shipped", "delivered"):
        response = app.handle_update_status(order["order_id"], {"status": status})
        assert response.status == 200
        assert response.body == {**order, "status": status}
        assert app.handle_get(order["order_id"]).body["status"] == status


@pytest.mark.parametrize("target", ["shipped", "delivered", "placed"])
def test_skipping_or_repeating_a_step_is_a_conflict(app, target):
    order = create(app, "alice")

    response = app.handle_update_status(order["order_id"], {"status": target})

    assert response.status == 409
    assert response.body == {"error": f"cannot change status from placed to {target}"}
    assert app.handle_get(order["order_id"]).body["status"] == "placed"


def test_moving_backwards_is_a_conflict(app):
    order = create(app, "alice")
    app.handle_update_status(order["order_id"], {"status": "paid"})

    response = app.handle_update_status(order["order_id"], {"status": "placed"})

    assert (response.status, response.body) == (409, {"error": "cannot change status from paid to placed"})


@pytest.mark.parametrize("request_body", [{}, {"status": "lost"}, {"status": None}, {"status": 3}])
def test_unknown_status_is_a_bad_request(app, request_body):
    order = create(app, "alice")

    response = app.handle_update_status(order["order_id"], request_body)

    assert (response.status, response.body) == (400, {"error": "unknown status"})


def test_unknown_order_is_not_found(app):
    response = app.handle_update_status("ord-9999", {"status": "paid"})

    assert (response.status, response.body) == (404, {"error": "order not found"})
