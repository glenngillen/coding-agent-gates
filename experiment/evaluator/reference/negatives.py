"""Negative variants of the reference overlays, used only to validate the frozen acceptance tests.

Each variant applies exact text substitutions to one task's reference overlay
(``experiment/evaluator/reference/<task>/``) and states the outcome the
independent evaluator must report:

- ``behavior: fail``: a plausible wrong implementation the acceptance test
  must reject.
- ``behavior: pass`` with ``structural: violation``: a behaviour-preserving
  architectural shortcut. The acceptance test must accept it (behaviour tests
  cannot see the rule) and the evaluator's own contract must flag it, so the
  two outcomes stay separate.

Like the references, these never enter an agent workspace.
"""

CONTROLLER = "src/orders/controllers/orders.py"
SERVICE = "src/orders/application/order_service.py"
REPO_IMPORT = (
    "from orders.domain import LineItem, Order, OrderSummary\n",
    "from orders.domain import LineItem, Order, OrderSummary\n"
    "from orders.infrastructure.repository import InMemoryOrderRepository  # noqa: F401\n",
)

VARIANTS = {
    "t01": [
        {"id": "leaks-ownership", "expect": {"behavior": "fail"},
         "edits": [(SERVICE, "        if summary.order.customer_id != customer_id:\n"
                             "            raise OrderNotFound(order_id)  # do not reveal that the order exists\n",
                    "")]},
        {"id": "direct-import", "expect": {"behavior": "pass", "structural": "violation"},
         "edits": [(CONTROLLER, *REPO_IMPORT)]},
    ],
    "t02": [
        {"id": "substring-match", "expect": {"behavior": "fail"},
         "edits": [(SERVICE, "any(i.sku == sku for i in o.items)", "any(sku in i.sku for i in o.items)")]},
    ],
    "t03": [
        {"id": "discount-on-combined-subtotal", "expect": {"behavior": "fail"},
         "edits": [(SERVICE, '"discount_cents": sum(s.discount_cents for s in summaries),\n'
                             '            "total_cents": sum(s.total_cents for s in summaries),',
                    '"discount_cents": discount_for(sum(s.subtotal_cents for s in summaries)),\n'
                    '            "total_cents": sum(s.subtotal_cents for s in summaries)'
                    ' - discount_for(sum(s.subtotal_cents for s in summaries)),')]},
    ],
    "t04": [
        {"id": "quote-places-order", "expect": {"behavior": "fail"},
         "edits": [(CONTROLLER, "        subtotal, discount, total = self._service.quote(items)\n",
                    "        subtotal, discount, total = self._service.quote(items)\n"
                    "        self._service.place_order(customer_id, items)\n")]},
        {"id": "off-by-one-threshold", "expect": {"behavior": "fail"},
         "edits": [(SERVICE, "    if subtotal_cents < DISCOUNT_THRESHOLD_CENTS:",
                    "    if subtotal_cents <= DISCOUNT_THRESHOLD_CENTS:")]},
        {"id": "direct-import", "expect": {"behavior": "pass", "structural": "violation"},
         "edits": [(CONTROLLER, *REPO_IMPORT)]},
    ],
    "t05": [
        {"id": "cancel-twice-succeeds", "expect": {"behavior": "fail"},
         "edits": [(SERVICE, '        if order.status == "cancelled":\n'
                             '            raise OrderAlreadyCancelled(order_id)\n', "")]},
    ],
    "t06": [
        {"id": "next-offset-on-last-page", "expect": {"behavior": "fail"},
         "edits": [(SERVICE, "(end if end < len(orders) else None)", "end")]},
    ],
    "t07": [
        {"id": "keeps-duplicates", "expect": {"behavior": "fail"},
         "edits": [(SERVICE, "for order_id in dict.fromkeys(order_ids):", "for order_id in order_ids:")]},
    ],
    "t08": [
        {"id": "allows-skipping", "expect": {"behavior": "fail"},
         "edits": [(SERVICE, "        if NEXT_STATUS.get(order.status) != status:",
                    "        if STATUSES.index(status) <= STATUSES.index(order.status):")]},
        {"id": "direct-import", "expect": {"behavior": "pass", "structural": "violation"},
         "edits": [(CONTROLLER, *REPO_IMPORT)]},
    ],
    "t09": [
        {"id": "pre-discount-total", "expect": {"behavior": "fail"},
         "edits": [(SERVICE, "        total = self.get_order_summary(order.order_id).total_cents\n",
                    "        total = order.subtotal_cents\n")]},
    ],
    "t10": [
        {"id": "limit-off-by-one", "expect": {"behavior": "fail"},
         "edits": [(SERVICE, "    if len(items) > MAX_LINE_ITEMS:", "    if len(items) >= MAX_LINE_ITEMS:")]},
    ],
}
