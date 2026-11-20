"""Real sensor runs over every fixture scenario, plus the behavioural tests."""

import pytest
from integration_helpers import PYTHON, make_copy, run, scenarios, sensor_json

pytestmark = pytest.mark.integration

EXIT = {"pass": 0, "violation": 1, "checker_error": 3}


@pytest.mark.parametrize("scenario", scenarios(), ids=lambda s: s["id"])
def test_sensor_reports_the_expected_outcome(tmp_path, scenario):
    root = make_copy(tmp_path, scenario["overlay"])

    code, result = sensor_json(root)

    assert result["status"] == scenario["expected_status"]
    assert code == EXIT[scenario["expected_status"]]
    edges = [{"importer": v["importer"], "imported": v["imported"]} for v in result["violations"]]
    assert edges == scenario["expected_edges"]
    if scenario["expected_status"] == "checker_error":
        assert result["error"]


@pytest.mark.parametrize("scenario", scenarios(), ids=lambda s: s["id"])
def test_behaviour_tests_cannot_see_the_architecture_rule(tmp_path, scenario):
    root = make_copy(tmp_path, scenario["overlay"])

    proc = run([PYTHON, "-m", "pytest", "-q", "tests/unit/orders", "--basetemp", tmp_path / "bt"], root)

    assert (proc.returncode == 0) == (scenario["behaviour_tests"] == "pass"), proc.stdout


def test_repairing_the_direct_import_passes_with_the_same_command(tmp_path):
    root = make_copy(tmp_path, "fixtures/direct_import")
    assert sensor_json(root)[1]["status"] == "violation"

    clean = make_copy(tmp_path / "clean")  # one clean copy, created once
    for rel in ("src/orders/controllers/orders.py", "src/orders/wiring.py"):
        (root / rel).write_text((clean / rel).read_text())

    assert sensor_json(root)[1]["status"] == "pass"


@pytest.mark.parametrize(
    "config",
    [
        "[importlinter]\nroot_packages =\n    orders\n",  # no contracts
        "garbage [[[\n",  # unparseable
        "[importlinter]\nroot_packages =\n    orders\n[importlinter:contract:x]\n"
        "name = Controllers must not import infrastructure repositories directly\n"
        "type = forbidden\nsource_modules =\n    orders.controllers\n",  # missing field
    ],
)
def test_invalid_configuration_is_a_checker_error(tmp_path, config):
    root = make_copy(tmp_path)
    (root / ".importlinter").write_text(config)

    code, result = sensor_json(root)

    assert (code, result["status"]) == (3, "checker_error")


def test_renamed_contract_is_a_checker_error_not_a_pass(tmp_path):
    root = make_copy(tmp_path)
    config = root / ".importlinter"
    config.write_text(config.read_text().replace(
        "name = Controllers must not import infrastructure repositories directly", "name = Renamed"))

    code, result = sensor_json(root)

    assert (code, result["status"]) == (3, "checker_error")
    assert "required rule not evaluated" in result["error"]


def test_an_ignored_import_on_the_required_rule_is_a_violation_needing_review(tmp_path):
    root = make_copy(tmp_path, "fixtures/direct_import")
    config = root / ".importlinter"
    config.write_text(
        config.read_text()
        + "ignore_imports =\n    orders.controllers.orders -> orders.infrastructure.repository\n"
    )

    code, result = sensor_json(root)

    assert (code, result["status"]) == (1, "violation")
    assert "KEPT (1 ignored import)" in result["raw_output"]
    assert [(v["kind"], v["importer"], v["imported"]) for v in result["violations"]] == [
        ("ignored", "orders.controllers.orders", "orders.infrastructure.repository")
    ]
