"""T07 bulk retrieval: handle_get_many(order_ids)."""

import pytest

from conftest import create, item

ERROR = {"error": "order_ids must be a list of 1 to 100 strings"}


def test_found_and_missing_in_requested_order_without_duplicates(app):
    a = create(app, "alice", [item(unit_price_cents=20000)])
    b = create(app, "bob")

    response = app.handle_get_many([b["order_id"], "ord-0404", a["order_id"], b["order_id"], "ord-0404"])

    assert response.status == 200
    assert response.body == {
        "orders": [app.handle_get(b["order_id"]).body, app.handle_get(a["order_id"]).body],
        "missing": ["ord-0404"],
    }
    assert response.body["orders"][1]["discount_cents"] == 2000


def test_one_hundred_ids_are_allowed(app):
    response = app.handle_get_many([f"ord-{n:04d}" for n in range(100)])

    assert response.status == 200
    assert len(response.body["missing"]) == 100


@pytest.mark.parametrize("ids", [[], "ord-0001", None, [1], ["ord-0001", None],
                                 [f"ord-{n:04d}" for n in range(101)]])
def test_invalid_id_lists(app, ids):
    response = app.handle_get_many(ids)

    assert (response.status, response.body) == (400, ERROR)
