"""The rules this example's sensor requires, with the repair hint for each.

Names must match the ``name`` of contracts in ``.importlinter``. A required rule
that does not appear in lint-imports' report is a checker error, never a pass:
deleting or renaming a contract must not read as a clean bill of health.
"""

CONTROLLERS_NOT_REPOSITORIES = "Controllers must not import infrastructure repositories directly"

REQUIRED_RULES: tuple[str, ...] = (CONTROLLERS_NOT_REPOSITORIES,)

REPAIR_HINTS: dict[str, str] = {
    CONTROLLERS_NOT_REPOSITORIES: (
        "Controllers may decode requests, call orders.application services and map "
        "responses. Route the data access through the application service (add a "
        "service method if needed) and remove the controller's import of "
        "orders.infrastructure."
    ),
}
