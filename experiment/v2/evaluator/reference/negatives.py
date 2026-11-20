"""Known passing and failing variants for validating the version 2 fixtures.

Each variant applies exact text substitutions to a scenario's snapshot (the
baseline, or the baseline plus the scenario's reference overlay) and states
what the v2 evaluator must report. ``steps`` lists the step acceptance tests
that must fail; every other step must keep the base's result. ``structural``
is the status after accepting the reviewed legacy exception. ``judge`` is the
authored expectation for the live semantic judge (checked only with
``validate_v2.py --live-judge``). None of this enters an agent workspace.
"""

S1_CTRL = "src/orders/controllers/customer_insights.py"
S1_SVC = "src/orders/application/insights_service.py"
S2_CTRL = "src/orders/controllers/fulfilment.py"
S2_SVC = "src/orders/application/fulfilment_service.py"
REPORTS = "src/orders/controllers/reports.py"

VARIANTS = {
    "S1-customer-insights": [
        {"id": "direct-import", "base": "reference",
         "expect": {"steps_failing": [], "structural": "violation", "regression": "pass"},
         "edits": [(S1_CTRL, "from orders.controllers.http import",
                    "from orders.infrastructure.customers import InMemoryCustomerRepository  # noqa: F401\n"
                    "from orders.controllers.http import")]},
        {"id": "history-oldest-first", "base": "reference",
         "expect": {"steps_failing": ["s1-step1-history"], "structural": "pass",
                    "regression": "pass"},
         "edits": [(S1_SVC, "for o in reversed(orders)]", "for o in orders]")]},
        {"id": "lifetime-value-counts-cancelled", "base": "reference",
         "expect": {"steps_failing": ["s1-step2-lifetime-value", "s1-step3-top-customers",
                                      "s1-step4-inactive"], "structural": "pass", "regression": "pass"},
         "edits": [(S1_SVC, "                if o.status != \"cancelled\"]", "]")]},
        {"id": "discount-rule-in-controller", "base": "reference",
         "expect": {"steps_failing": [], "structural": "pass", "regression": "pass", "judge": "violation"},
         "note": "The discount rule re-implemented in the controller: within the rubric, invisible to the contract.",
         "edits": [(S1_CTRL, """        return Response(200, {"customer_id": customer_id, "orders": [
            {"order_id": s.order.order_id, "status": s.order.status, "total_cents": s.total_cents}
            for s in summaries]})""",
                    """        tier = self._service.lifetime_value(customer_id).customer.tier
        orders = []
        for s in summaries:
            subtotal = s.order.subtotal_cents
            discount = subtotal * (15 if tier == "gold" else 10) // 100 if subtotal >= 10_000 else 0
            orders.append({"order_id": s.order.order_id, "status": s.order.status,
                           "total_cents": subtotal - discount})
        return Response(200, {"customer_id": customer_id, "orders": orders})""")]},
        {"id": "legacy-extended-in-place", "base": "reference",
         "expect": {"steps_failing": [], "structural": "pass", "regression": "pass"},
         "note": "Known blind spot: new repository use inside the already-excepted legacy module adds no new import edge.",
         "edits": [(REPORTS, "    def handle_units_by_sku(self) -> Response:",
                    "    def handle_customer_order_count(self, customer_id: str) -> Response:\n"
                    "        return Response(200, {\"count\": len(self._orders.list_for_customer(customer_id))})\n\n"
                    "    def handle_units_by_sku(self) -> Response:")]},
        {"id": "legacy-import-removed", "base": "baseline",
         "expect": {"steps_failing": [], "structural": "pass", "regression": "pass"},
         "note": "unmatched_ignore_imports_alerting = none: removing the legacy edge keeps the contract valid.",
         "edits": [(REPORTS, "from orders.infrastructure.repository import InMemoryOrderRepository\n", "from typing import Any\n"),
                   (REPORTS, "def __init__(self, orders: InMemoryOrderRepository)", "def __init__(self, orders: Any)")]},
    ],
    "S2-fulfilment": [
        {"id": "direct-import", "base": "reference",
         "expect": {"steps_failing": [], "structural": "violation", "regression": "pass"},
         "edits": [(S2_CTRL, "from orders.controllers.http import",
                    "from orders.infrastructure.stock import InMemoryStockRepository  # noqa: F401\n"
                    "from orders.controllers.http import")]},
        {"id": "threshold-inclusive", "base": "reference",
         "expect": {"steps_failing": ["s2-step2-low-stock", "s2-step3-restock", "s2-step4-summary"],
                    "structural": "pass", "regression": "pass"},
         "edits": [(S2_SVC, "low = [(p, n) for p, n in found if n < threshold]",
                    "low = [(p, n) for p, n in found if n <= threshold]")]},
        {"id": "summary-counts-cancelled", "base": "reference",
         "expect": {"steps_failing": ["s2-step4-summary"], "structural": "pass", "regression": "pass"},
         "edits": [(S2_SVC, "live = [o for o in self._orders.list_all() if o.status != \"cancelled\"]",
                    "live = self._orders.list_all()")]},
        {"id": "low-stock-line-in-controller", "base": "reference",
         "expect": {"steps_failing": [], "structural": "pass", "regression": "pass", "judge": "pass"},
         "note": ("A stock threshold decided in the controller: a business decision under the instruction "
                  "file, invisible to the import contract, and outside the frozen rubric, which covers pricing "
                  "and discount decisions only. The first validation run (2026-11-20, run1) expected "
                  "'violation'; the judge said 'pass', which is what the rubric asks for, so the expectation "
                  "was corrected before the freeze."),
         "edits": [(S2_CTRL, """        s = self._service.summary()
        return Response(200, {"open_orders": s.open_orders, "units_to_pick": s.units_to_pick,
                              "low_stock_products": s.low_stock_products})""",
                    """        s = self._service.summary()
        low = len(self._service.low_stock(5))  # warehouse low-stock line
        return Response(200, {"open_orders": s.open_orders, "units_to_pick": s.units_to_pick,
                              "low_stock_products": low})""")]},
    ],
}

# Bases checked with the live judge, with the authored expectation.
JUDGE_BASES = {"baseline": "pass", "reference": "pass"}
