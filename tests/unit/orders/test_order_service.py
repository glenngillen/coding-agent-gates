"""Application-service tests: the service owns business policy and repository access."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from orders.application.order_service import (
    DISCOUNT_RATE_PERCENT,
    DISCOUNT_THRESHOLD_CENTS,
    OrderNotFound,
    OrderService,
    discount_for,
)
from orders.domain import LineItem
from orders.infrastructure.repository import InMemoryOrderRepository


def make_service():
    return OrderService(InMemoryOrderRepository())


def test_place_order_persists_through_the_repository():
    repository = InMemoryOrderRepository()
    service = OrderService(repository)

    order = service.place_order("cust-1", [LineItem("A", 1, 100)])

    assert repository.get(order.order_id) == order


def test_get_order_raises_for_unknown_ids():
    with pytest.raises(OrderNotFound):
        make_service().get_order("missing")


def test_summary_applies_the_discount_policy():
    service = make_service()
    order = service.place_order("cust-1", [LineItem("A", 2, 6_000)])

    summary = service.get_order_summary(order.order_id)

    assert summary.subtotal_cents == 12_000
    assert summary.discount_cents == 1_200
    assert summary.total_cents == 10_800


class TestProperties:
    @given(st.integers(min_value=0, max_value=10**12))
    def test_discount_is_bounded_and_only_applies_at_or_above_threshold(self, subtotal):
        discount = discount_for(subtotal)

        assert 0 <= discount <= subtotal
        if subtotal < DISCOUNT_THRESHOLD_CENTS:
            assert discount == 0
        else:
            assert discount == subtotal * DISCOUNT_RATE_PERCENT // 100
