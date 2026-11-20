#!/usr/bin/env python3
"""Exploratory probes on the Codex CLI (NOT study data).

Same workspace, scenarios and conditions as probe.py, with the instruction
file as AGENTS.md. Each step is one `codex exec` turn in the same thread.
arm A: guidance only. arm B: after each turn, run the import-contract sensor
and hand its diagnostic back (up to 3 repair requests), the outer loop the CI
section of the article describes.

    codex_probe.py TAG MODEL SCENARIO REPEATS VARIANTS ARMS
"""
from __future__ import annotations
import copy, json, re, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import probe  # noqa: E402
from probe import ROOT, pv  # noqa: E402

OUT = HERE / "codex-runs"
VARIANTS = {"stated": "base", "one-line": "vague", "unstated": "norule", "shortcut": "shortcut", "conflict": "conflict-nested"}
PY = str(ROOT / ".venv/bin/python")
MAX_REPAIRS = 3


def to_agents_md(ws: Path) -> None:
    for f in list(ws.rglob("CLAUDE.md")):
        f.write_text(f.read_text().replace("CLAUDE.md", "AGENTS.md"))
        pv._git(subprocess.run, ws, "mv", str(f.relative_to(ws)), str(f.relative_to(ws).with_name("AGENTS.md")))
    probe.commit(ws, "Rename the instruction file")


def codex(ws: Path, model: str, message: str, thread: str | None, log: Path) -> tuple[str | None, int]:
    base = ["codex", "exec"] + (["resume", thread] if thread else [])
    argv = base + ["--ignore-user-config", "--ignore-rules", "--skip-git-repo-check", "--json", "-m", model,
                   "-c", 'sandbox_mode="workspace-write"', "-c", 'approval_policy="never"', "-"]
    proc = subprocess.run(argv, cwd=ws, input=message, capture_output=True, text=True, timeout=1500)
    with log.open("a") as fh:
        fh.write(proc.stdout + ("\n[stderr] " + proc.stderr[-2000:] + "\n" if proc.returncode else ""))
    if not thread:
        m = re.search(r'"thread_id"\s*:\s*"([^"]+)"', proc.stdout)
        thread = m.group(1) if m else None
    return thread, proc.returncode


def sensor(ws: Path) -> tuple[bool, str]:
    """Pass unless a non-legacy controller imports orders.infrastructure (reports.py is the reviewed exception)."""
    found = probe.infra_imports(ws / "src")
    lines = [f"- src/orders/controllers/{f} imports {m}" for f, mods in found.items() for m in mods]
    return not found, ("Architecture check: VIOLATION\nRule: controllers must not import orders.infrastructure.\n"
                       + "\n".join(lines) + "\nFix: reach storage through a service in orders.application, "
                       "and have the controller depend on that service.")


def run_one(tag: str, variant: str, model: str, scenario_id: str, arm: str, n: int) -> dict:
    study = copy.deepcopy(pv.load_study())
    v = probe.VARIANTS[VARIANTS[variant]]
    scenario = copy.deepcopy(pv.load_scenarios()[scenario_id])
    rid = f"{variant}-{model}-{scenario_id}-{arm}-{n}"
    entry = {"arm": "A", "model_key": "haiku", "run_id": rid, "repeat": n, "scenario_id": scenario_id}
    prepared = pv.prepare(scenario, entry, study=study, study_name=tag, work_dir=OUT, runs_dir=OUT / "_retained")
    ws, base = Path(prepared["paths"]["workspace"]), Path(prepared["paths"]["base"])
    if "mutate" in v:
        v["mutate"](ws)
    to_agents_md(ws)
    log, thread, t0 = base / "codex.jsonl", None, time.time()
    turns = []
    for message in prepared["messages"]:
        message = message.replace(study["prompt_suffix"], v.get("suffix", "") + study["prompt_suffix"])
        before = probe.infra_imports(ws / "src")
        thread, rc = codex(ws, model, message, thread, log)
        first = probe.infra_imports(ws / "src")
        turn = {"rc": rc, "slip": first != before and bool(first), "first": first, "repairs": 0, "caught": None, "repaired": None}
        if arm == "B":
            ok, diag = sensor(ws)
            turn["caught"] = not ok
            while not ok and turn["repairs"] < MAX_REPAIRS and thread:
                turn["repairs"] += 1
                thread, _ = codex(ws, model, "The architecture check failed on your change. Fix it, then reply with a short "
                                  "summary.\n\n" + diag, thread, log)
                ok, diag = sensor(ws)
            turn["repaired"] = ok
        turns.append(turn)
        if rc != 0 or not thread:
            break
    tests = subprocess.run([PY, "-m", "pytest", "-q", "tests"], cwd=ws, capture_output=True, text=True)
    out = {"run_id": rid, "variant": variant, "model": model, "arm": arm, "turns": turns,
           "slipped": any(t["slip"] for t in turns), "final": probe.infra_imports(ws / "src"),
           "tests_ok": tests.returncode == 0, "seconds": round(time.time() - t0, 1)}
    (base / "probe-result.json").write_text(json.dumps(out, indent=2))
    return out


if __name__ == "__main__":
    tag, model, scenario_id, repeats = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
    jobs = [(tag, v, model, scenario_id, a, n) for n in range(1, repeats + 1) for v in sys.argv[5].split(",") for a in sys.argv[6].split(",")]

    def safe(j):
        try:
            return run_one(*j)
        except Exception as exc:  # noqa: BLE001
            return {"run_id": "-".join(map(str, j[1:])), "error": repr(exc)}

    with ThreadPoolExecutor(max_workers=3) as pool:
        for r in pool.map(safe, jobs):
            print(json.dumps({"run_id": r["run_id"], "error": r.get("error"), "slipped": r.get("slipped"),
                              "slips": [bool(t["slip"]) for t in r.get("turns", [])],
                              "repairs": [t["repairs"] for t in r.get("turns", [])], "final": r.get("final"),
                              "tests_ok": r.get("tests_ok"), "s": r.get("seconds")}), flush=True)
