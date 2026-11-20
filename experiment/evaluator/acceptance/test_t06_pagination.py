"""T06 pagination: handle_list_for_customer(customer_id, limit=..., offset=...)."""

import pytest

from conftest import create


@pytest.fixture
def five(app):
    return [create(app, "alice") for _ in range(5)]


def test_pages_walk_the_orders_in_creation_order(app, five):
    first = app.handle_list_for_customer("alice", limit=2)
    second = app.handle_list_for_customer("alice", limit=2, offset=2)
    last = app.handle_list_for_customer("alice", limit=2, offset=4)

    assert first.status == 200
    assert first.body == {"orders": five[0:2], "next_offset": 2}
    assert second.body == {"orders": five[2:4], "next_offset": 4}
    assert last.body == {"orders": five[4:5], "next_offset": None}


def test_exact_final_page_and_offset_past_the_end(app, five):
    assert app.handle_list_for_customer("alice", limit=5).body == {"orders": five, "next_offset": None}
    assert app.handle_list_for_customer("alice", limit=3, offset=9).body == {"orders": [], "next_offset": None}


@pytest.mark.parametrize(("limit", "offset"), [(0, 0), (51, 0), (-1, 0), (2, -1), ("2", 0), (2.0, 0), (2, "0")])
def test_invalid_pagination(app, five, limit, offset):
    response = app.handle_list_for_customer("alice", limit=limit, offset=offset)

    assert (response.status, response.body) == (400, {"error": "invalid pagination"})


def test_limit_fifty_is_allowed_and_no_limit_is_unchanged(app, five):
    assert app.handle_list_for_customer("alice", limit=50).status == 200
    assert app.handle_list_for_customer("alice").body == {"orders": five}
