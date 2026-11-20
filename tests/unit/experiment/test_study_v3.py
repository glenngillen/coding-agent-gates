"""Version 3 planning and workspace preparation (experiment/tools/run_study_v3.py)."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "experiment" / "tools"), str(ROOT / "experiment")]

import prepare_v2 as pv  # noqa: E402
import run_study_v3 as v3  # noqa: E402
import summarize_v3  # noqa: E402

STUDY = v3.load_study()


def test_plan_covers_every_cell_once_per_repeat():
    plan = v3.plan_sessions(list(STUDY["guidance"]), STUDY["scenarios"], sorted(STUDY["arms"]), list(STUDY["models"]),
                            repeats=STUDY["repeats"], seed=STUDY["seed"])
    assert len(plan) == 72
    assert [p["sequence"] for p in plan] == list(range(1, 73))
    assert len({p["run_id"] for p in plan}) == 72
    cells = Counter((p["guidance"], p["scenario_id"], p["model_key"], p["arm"]) for p in plan)
    assert len(cells) == 24 and set(cells.values()) == {3}
    for repeat in (1, 2, 3):
        block = [p for p in plan if p["repeat"] == repeat]
        assert len(block) == 24 and [p["sequence"] for p in block] == sorted(p["sequence"] for p in block)


def test_plan_is_reproducible_and_seed_dependent():
    args = (["stated", "unstated"], ["S1"], ["A", "B"], ["haiku"])
    assert v3.plan_sessions(*args, repeats=2, seed=7) == v3.plan_sessions(*args, repeats=2, seed=7)
    orders = {tuple(p["run_id"] for p in v3.plan_sessions(*args, repeats=2, seed=s)) for s in range(20)}
    assert len(orders) > 1


def test_run_id_names_the_guidance_level():
    assert v3.run_id("unstated", "S1-customer-insights", "B", "haiku", 2) == "unstated-S1-customer-insights__B__haiku__r2"


def test_arms_are_a_and_b_only_and_reuse_the_version_2_agent_configuration():
    v2 = pv.load_study()
    assert sorted(STUDY["arms"]) == ["A", "B"]
    assert STUDY["arms"]["A"]["stop_hook"] is None and STUDY["arms"]["B"]["stop_hook"] == {"semantic": False}
    assert STUDY["agent"] == v2["agent"] and STUDY["scenarios"] == v2["scenarios"]
    assert STUDY["prompt_suffix"] == v2["prompt_suffix"] and STUDY["max_repairs"] == v2["max_repairs"]
    for key, model in STUDY["models"].items():
        assert {k: v for k, v in model.items() if k != "max_budget_usd"} == {
            k: v for k, v in v2["models"][key].items() if k != "max_budget_usd"}


def test_guidance_files_differ_only_in_the_architecture_section():
    text = {g: (ROOT / spec["instruction_file"]).read_text() for g, spec in STUDY["guidance"].items()}
    assert text["stated"] == (ROOT / "experiment/v2/instruction.md").read_text()

    def outside(t: str) -> str:
        if "## Architecture" not in t:
            return t
        return t[: t.index("## Architecture")] + t[t.index("## Working"):]

    assert outside(text["stated"]) == outside(text["one-line"]) == text["unstated"]
    assert "orders.infrastructure" in text["stated"]
    for level in ("one-line", "unstated"):
        assert "infrastructure`" not in text[level] and "must not import" not in text[level]
    assert "Keep to the layering." in text["one-line"]
    assert "layer" not in text["unstated"].lower()


def test_history_swaps_only_claude_md():
    v2 = pv.load_json(ROOT / "experiment/v2/history/history.json")
    h = v3.history_for("experiment/v3/instructions/unstated.md")
    assert [c["message"] for c in h["commits"]] == [c["message"] for c in v2["commits"]]
    flat = lambda hist: [p for c in hist["commits"] for p in c["paths"]]  # noqa: E731
    changed = [(a, b) for a, b in zip(flat(v2), flat(h)) if a != b]
    assert changed == [("CLAUDE.md", {"path": "CLAUDE.md", "source": "experiment/v3/instructions/unstated.md"})]
    assert "CLAUDE.md" in flat(v2)  # the frozen history itself is not mutated


@pytest.mark.parametrize("level", ["stated", "one-line", "unstated"])
def test_workspace_gets_the_levels_instruction_file_and_the_version_2_code(tmp_path, level):
    instruction = STUDY["guidance"][level]["instruction_file"]
    ws = tmp_path / "ws"
    pv.build_workspace(ws, history=v3.history_for(instruction))
    assert (ws / "CLAUDE.md").read_bytes() == (ROOT / instruction).read_bytes()
    assert len(pv.git_log(ws)) == 4
    for rel in ("src/orders/controllers/reports.py", "src/orders/wiring.py", "tests/test_orders.py"):
        assert (ws / rel).read_bytes() == (ROOT / "experiment/v2/baseline" / rel).read_bytes()
    assert pv._git(pv.subprocess.run, ws, "status", "--porcelain") == ""


def test_frozen_manifest_matches_and_pins_the_version_2_manifest():
    v3.check_frozen()
    manifest = json.loads(v3.MANIFEST.read_text())
    assert set(manifest["files"]) >= {"experiment/protocol-v3.md", "experiment/v3/study.json",
                                      "experiment/tools/run_study_v3.py",
                                      "experiment/v3/instructions/unstated.md"}
    assert manifest["depends_on"]["experiment/v2/frozen-manifest.json"] == pv.sha256_file(
        ROOT / "experiment/v2/frozen-manifest.json")


def _record(guidance, arm, slips, final="pass", caught=None, repaired=None):
    turns = [{"step": i + 1, "reached": True, "slip": s, "caught": caught if s else None,
              "repaired": repaired if s else None, "repair_requests": (1 if s else 0) if arm == "B" else None,
              "new_edges": [["orders.controllers.x", "orders.infrastructure.repository"]] if s else [],
              "persisting_violation": False} for i, s in enumerate(slips)]
    return {"identity": {"run_id": f"{guidance}-{arm}-{id(slips)}", "guidance": guidance, "arm": arm,
                         "model_key": "haiku", "scenario_id": "S1"},
            "outcome": {"termination": "completed", "final_structural": final,
                        "behavior": {"steps_accepted": ["a", "b", "c", "d"], "all_steps_accepted": True},
                        "tampering_detected": False, "legacy_reports_modified": False},
            "turns": turns, "repair": {"applicable": arm == "B", "requests": sum(slips) if arm == "B" else None},
            "usage": {"agent": {"cost_usd": "0.02"}, "judge": {}}, "time": {"session_s": 60.0}}


def test_summary_groups_by_guidance_and_arm():
    records = [_record("unstated", "A", [False, False, True, False], final="violation"),
               _record("unstated", "A", [False, False, False, False]),
               _record("unstated", "B", [False, False, True, False], caught=True, repaired=True),
               _record("stated", "A", [False, False, False, False])]
    s = summarize_v3.summarize(records, plan=[])
    a, b = s["by_ga"][("unstated", "A")], s["by_ga"][("unstated", "B")]
    assert (a["sessions_with_slip"], a["sessions"], a["final_violations"]) == (1, 2, 1)
    assert (b["sessions_with_slip"], b["caught"], b["repaired"], b["final_violations"]) == (1, 1, 1, 0)
    assert s["by_ga"][("stated", "A")]["sessions_with_slip"] == 0
    assert len(s["slips"]) == 2
    text = summarize_v3.render("demo", records, [], s)
    assert "| Rule unstated, no gate | 1/2" in text and "| Rule unstated, gate | 1/1" in text
    assert "| One-line hint, no gate | no sessions" in text


def test_version_4_reuses_the_version_3_runner_with_its_own_study_and_manifest():
    import run_study_v4 as v4

    study = json.loads(v4.STUDY_PATH.read_text())
    assert list(study["guidance"]) == ["one-line", "handbook"]
    assert sorted(study["arms"]) == ["A", "B"] and study["agent"] == STUDY["agent"]
    lean = (ROOT / study["guidance"]["one-line"]["instruction_file"]).read_bytes()
    assert lean == (ROOT / "experiment/v3/instructions/one-line.md").read_bytes()
    handbook = (ROOT / study["guidance"]["handbook"]["instruction_file"]).read_text()
    stated = (ROOT / "experiment/v2/instruction.md").read_text()
    arch = stated[stated.index("## Architecture"): stated.index("## Working")]
    assert handbook.count(arch.strip()) == 1 and handbook.count("orders.infrastructure") == 1
    assert len(handbook) > 150_000 and 0.4 < handbook.index("## Architecture") / len(handbook) < 0.7
    plan = v3.plan_sessions(list(study["guidance"]), study["scenarios"], sorted(study["arms"]), list(study["models"]),
                            repeats=study["repeats"], seed=study["seed"])
    assert len(plan) == 48 == study["budget"]["sessions"]
    v4.check_frozen()
    assert v3.STUDY_PATH.parent.name == "v3"  # importing version 4 does not repoint version 3


def test_version_5_adds_request_suffixes_and_extra_files_without_repointing_version_3():
    import run_study_v5 as v5

    study = json.loads(v5.STUDY_PATH.read_text())
    assert list(study["guidance"]) == ["stated", "one-line", "stated+shortcut", "stated+conflict"]
    assert {m["model"] for m in study["models"].values()} == {"claude-haiku-4-5", "claude-haiku-5-5"}
    stated = (ROOT / "experiment/v2/instruction.md").read_bytes()
    for level in ("stated", "stated+shortcut", "stated+conflict"):
        assert (ROOT / study["guidance"][level]["instruction_file"]).read_bytes() == stated
    scenario = pv.load_scenarios()[study["scenarios"][0]]
    suffix = study["guidance"]["stated+shortcut"]["request_suffix"]
    pressed = v5.scenario_for(scenario, {"guidance": "stated+shortcut"}, study)
    assert all(p["request"] == s["request"] + suffix for p, s in zip(pressed["steps"], scenario["steps"]))
    assert v5.scenario_for(scenario, {"guidance": "stated"}, study) == scenario
    conflict = study["guidance"]["stated+conflict"]["instruction_file"]
    assert v5.extra_files_for(conflict, study) == {"src/orders/controllers/CLAUDE.md": "experiment/v5/nested-controllers-CLAUDE.md"}
    assert v5.extra_files_for(study["guidance"]["stated"]["instruction_file"], study) == {}
    plan = v3.plan_sessions(list(study["guidance"]), study["scenarios"], sorted(study["arms"]), list(study["models"]),
                            repeats=study["repeats"], seed=study["seed"])
    assert len(plan) == 96
    v5.check_frozen()
    assert v3.STUDY_PATH.parent.name == "v3"  # importing version 5 does not repoint version 3
