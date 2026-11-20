import io
import json

from gates.cli import main
from gates.linter_output import Edge
from gates.result import SensorResult, Status, Violation

RULE = "Controllers must not import infrastructure repositories directly"


def fake(result):
    calls = []

    def sensor(root, *, cache):
        calls.append({"root": root, "cache": cache})
        return result

    return sensor, calls


def violation():
    return SensorResult(Status.VIOLATION, {RULE: "BROKEN"},
                        (Violation(RULE, Edge("a.controllers.x", "a.infrastructure.y", (3,))),),
                        None, "ab" * 32, "2.17", 1, "RAW REPORT")


def test_exit_status_follows_the_result():
    for result, code in [
        (SensorResult(Status.PASS, {RULE: "KEPT"}, (), None, "ab" * 32, "2.17", 0, "ok"), 0),
        (violation(), 1),
        (SensorResult.checker_error("boom", fingerprint=None), 3),
    ]:
        sensor, _ = fake(result)
        assert main([], sensor=sensor, out=io.StringIO()) == code


def test_prints_the_diagnostic_and_raw_report_for_failures():
    sensor, _ = fake(violation())
    out = io.StringIO()

    main([], sensor=sensor, out=out)

    text = out.getvalue()
    assert text.startswith("ARCHITECTURE VIOLATION")
    assert "a.controllers.x -> a.infrastructure.y (line 3)" in text
    assert "RAW REPORT" in text


def test_json_output_roundtrips(tmp_path):
    sensor, calls = fake(violation())
    out = io.StringIO()

    main(["--json", "--root", str(tmp_path), "--cache-dir", str(tmp_path / "c")],
         sensor=sensor, out=out)

    assert SensorResult.from_dict(json.loads(out.getvalue())) == violation()
    assert calls[0]["root"] == tmp_path
    assert calls[0]["cache"].directory == tmp_path / "c"


def test_cache_is_off_by_default():
    sensor, calls = fake(violation())
    main([], sensor=sensor, out=io.StringIO())
    assert calls[0]["cache"] is None
