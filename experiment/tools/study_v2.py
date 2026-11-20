"""Pure logic for the version 2 study (experiment/protocol-v2.md).

No I/O here: the preparation, driver, evaluator and summarizer call these
functions, and the unit tests exercise them directly.

- ``accept_reviewed_exceptions``: the study's gate and evaluator accept an
  ignored import on a required rule only when a person has reviewed that exact
  ``ignore_imports`` entry (``experiment/v2/reviewed-exceptions.json``). The
  sensor itself reports every ignored import as a violation that needs review.
- ``upper_bound`` / ``lower_bound``: exact one-sided 95% binomial bounds
  (Clopper-Pearson), the protocol's reporting rule for slip rates.
- ``plan_sessions``: the frozen run order.
- ``split_turns`` / ``turn_outcomes``: per-turn slip, catch and repair from
  the hook log (gated arms) or the turn-end snapshots (arm A).
- ``summarize_cells``: per-cell denominators, slip counts and bounds.
"""

from __future__ import annotations

import math
import random
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import replace
from typing import Any

from gates.result import SensorResult, Status

REVIEWED_SCHEMA = "coding-agent-gates/reviewed-exceptions/v1"
CONFIDENCE = 0.95


# --- reviewed exceptions --------------------------------------------------------

def parse_reviewed(data: Any) -> dict[str, tuple[str, ...]]:
    """Validate a reviewed-exceptions document; raise ``ValueError`` if malformed."""
    if not isinstance(data, dict) or data.get("schema") != REVIEWED_SCHEMA:
        raise ValueError("not a reviewed-exceptions document")
    exceptions = data.get("exceptions")
    if not isinstance(exceptions, dict):
        raise ValueError("exceptions must be an object")
    out: dict[str, tuple[str, ...]] = {}
    for rule, entries in exceptions.items():
        if not isinstance(rule, str) or not isinstance(entries, list) or not all(
                isinstance(e, str) for e in entries):
            raise ValueError(f"invalid exceptions for {rule!r}")
        out[rule] = tuple(entries)
    return out


def accept_reviewed_exceptions(result: SensorResult,
                               reviewed: Mapping[str, Sequence[str]]) -> SensorResult:
    """Drop ignored-import violations whose exact entry is reviewed for that rule.

    Broken edges are never accepted, and neither is an ignored import whose
    entry could not be read. If nothing else remains the result is a pass.
    """
    if result.status is not Status.VIOLATION:
        return result

    def accepted(v) -> bool:
        entry = f"{v.edge.importer} -> {v.edge.imported}"
        return v.kind == "ignored" and entry in reviewed.get(v.rule, ())

    remaining = tuple(v for v in result.violations if not accepted(v))
    if len(remaining) == len(result.violations):
        return result
    if remaining:
        return replace(result, violations=remaining)
    return replace(result, status=Status.PASS, violations=())


# --- exact binomial bounds ------------------------------------------------------

def _cdf(k: int, n: int, p: float) -> float:
    return sum(math.comb(n, i) * p**i * (1 - p) ** (n - i) for i in range(k + 1))


def _check(k: int, n: int) -> None:
    if type(k) is not int or type(n) is not int or n < 1 or not 0 <= k <= n:
        raise ValueError(f"need 0 <= k <= n and n >= 1, got k={k!r}, n={n!r}")


def _bisect(f, target: float, increasing: bool) -> float:
    lo, hi = 0.0, 1.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if (f(mid) < target) == increasing:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def upper_bound(k: int, n: int, confidence: float = CONFIDENCE) -> float:
    """Exact one-sided upper confidence bound for a rate after k events in n trials.

    The p at which seeing k or fewer events has probability 1 - confidence.
    For k = 0 this is 1 - (1 - confidence) ** (1 / n): 0/10 gives about 0.259.
    """
    _check(k, n)
    if k == n:
        return 1.0
    if k == 0:
        return 1 - (1 - confidence) ** (1 / n)
    return _bisect(lambda p: _cdf(k, n, p), 1 - confidence, increasing=False)


def lower_bound(k: int, n: int, confidence: float = CONFIDENCE) -> float:
    """Exact one-sided lower confidence bound (0 when k = 0)."""
    _check(k, n)
    if k == 0:
        return 0.0
    if k == n:
        return (1 - confidence) ** (1 / n)
    return _bisect(lambda p: 1 - _cdf(k - 1, n, p), 1 - confidence, increasing=True)


# --- planning --------------------------------------------------------------------

def run_id(scenario_id: str, arm: str, model_key: str, repeat: int) -> str:
    return f"{scenario_id}__{arm}__{model_key}__r{repeat}"


def plan_sessions(scenarios: Sequence[str], arms: Sequence[str], models: Sequence[str], *,
                  repeats: int, seed: int) -> list[dict[str, Any]]:
    """Every (scenario, arm, model) cell once per repeat, shuffled within each repeat block."""
    rng = random.Random(seed)
    plan: list[dict[str, Any]] = []
    for repeat in range(1, repeats + 1):
        block = [(s, a, m) for s in scenarios for m in models for a in arms]
        rng.shuffle(block)
        for s, a, m in block:
            plan.append({"sequence": len(plan) + 1, "repeat": repeat, "scenario_id": s, "arm": a,
                         "model_key": m, "run_id": run_id(s, a, m, repeat)})
    return plan


# --- per-turn outcomes -------------------------------------------------------------

def split_turns(events: Iterable[Mapping[str, Any]], n_steps: int) -> list[list[Mapping[str, Any]]]:
    """Stop events grouped by turn; each UserPromptSubmit starts the next turn."""
    turns: list[list[Mapping[str, Any]]] = [[] for _ in range(n_steps)]
    index = -1
    for event in events:
        name = event.get("hook_event_name") if isinstance(event, Mapping) else None
        if name == "UserPromptSubmit":
            index += 1
        elif name == "Stop" and 0 <= index < n_steps:
            turns[index].append(event)
    return turns


def _status(event: Mapping[str, Any] | None) -> str | None:
    sensor = event.get("sensor") if isinstance(event, Mapping) else None
    return sensor.get("status") if isinstance(sensor, Mapping) else None


def _slip(status: str | None) -> bool | None:
    return {"violation": True, "pass": False}.get(status or "")


Edge = tuple[str, str]


def _edges(violations: Any) -> set[Edge] | None:
    if not isinstance(violations, list):
        return None
    out = set()
    for v in violations:
        if isinstance(v, Mapping) and isinstance(v.get("importer"), str) and isinstance(v.get("imported"), str):
            out.add((v["importer"], v["imported"]))
    return out


def _as_edges(items: Iterable[Any] | None) -> set[Edge] | None:
    if items is None:
        return None
    return {(str(a), str(b)) for a, b in items}


def turn_outcomes(*, gated: bool, n_steps: int, turn_results: Sequence[Mapping[str, Any]],
                  end_statuses: Sequence[str | None], events: Sequence[Mapping[str, Any]],
                  end_edges: Sequence[Iterable[Any] | None] | None = None) -> list[dict[str, Any]]:
    """One entry per step.

    The first candidate completion of a turn is the first Stop event's sensor
    result in a gated arm, and the turn-end snapshot in arm A (where it is the
    only one). With ``end_edges`` (the violating edges of each turn-end
    snapshot), ``slip`` means the first candidate has a violating edge that was
    not present at the start of the turn (the previous turn's end, or the
    baseline for turn 1); a violation carried over unchanged is reported as
    ``persisting_violation`` instead. Without ``end_edges``, any violation in
    the first candidate counts. Unknown (checker error, missing event, unknown
    start state) is ``None``, never ``False``. ``caught``/``repaired`` apply
    only to gated arms with a slip.
    """
    end_sets = [_as_edges(e) for e in end_edges] if end_edges is not None else None
    by_turn = split_turns(events, n_steps) if gated else [[] for _ in range(n_steps)]
    out = []
    for i in range(n_steps):
        entry: dict[str, Any] = {"step": i + 1, "reached": i < len(turn_results)}
        if not entry["reached"]:
            entry.update({"censored": True, "cut_short": None, "result_subtype": None,
                          "first_structural": None, "end_structural": None, "slip": None,
                          "caught": None, "repaired": None, "repair_requests": None,
                          "semantic_first": None, "new_edges": None, "persisting_violation": None})
            out.append(entry)
            continue
        result = turn_results[i] if isinstance(turn_results[i], Mapping) else {}
        end = end_statuses[i] if i < len(end_statuses) else None
        stops = by_turn[i]
        first = (_status(stops[0]) if stops else None) if gated else end
        slip = _slip(first)
        new_edges: list[list[str]] | None = None
        persisting = None
        if end_sets is not None and slip:
            first_edges = (_edges((stops[0].get("sensor") or {}).get("violations")) if stops else None) \
                if gated else (end_sets[i] if i < len(end_sets) else None)
            start = set() if i == 0 else (end_sets[i - 1] if i - 1 < len(end_sets) else None)
            if first_edges is None or start is None:
                slip = None
            else:
                new = first_edges - start
                new_edges = [list(e) for e in sorted(new)]
                persisting = bool(first_edges & start)
                slip = bool(new)
        elif end_sets is not None and slip is False:
            persisting = False
        caught = repaired = None
        requests = None
        semantic_first = None
        if gated:
            requests = sum(1 for s in stops if s.get("decision") == "block")
            if slip:
                caught = stops[0].get("decision") == "block"
                if caught:
                    repaired = _status(stops[-1]) == "pass" and stops[-1].get("decision") != "block"
            semantic_first = next((s["semantic"].get("status") for s in stops
                                   if isinstance(s.get("semantic"), Mapping)), None)
        entry.update({"censored": False, "cut_short": result.get("subtype") != "success",
                      "result_subtype": result.get("subtype"), "first_structural": first,
                      "end_structural": end, "slip": slip, "caught": caught, "repaired": repaired,
                      "repair_requests": requests, "semantic_first": semantic_first,
                      "new_edges": new_edges, "persisting_violation": persisting})
        out.append(entry)
    return out


# --- summaries -------------------------------------------------------------------

def _bounds(k: int, n: int) -> tuple[float | None, float | None]:
    return (lower_bound(k, n), upper_bound(k, n)) if n else (None, None)


def summarize_cells(records: Iterable[Mapping[str, Any]],
                    key=lambda r: (r["identity"]["scenario_id"], r["identity"]["arm"],
                                   r["identity"]["model_key"])) -> dict[tuple, dict[str, Any]]:
    """Descriptive counts per cell. A session's slip outcome is known if any turn
    slipped, or if every step was reached with a known no-slip result."""
    cells: dict[tuple, dict[str, Any]] = {}
    for record in records:
        c = cells.setdefault(key(record), {"attempted": 0, "not_started": 0, "sessions": 0,
                                           "sessions_with_slip": 0, "sessions_unknown": 0,
                                           "turns": 0, "turn_slips": 0, "turns_unknown": 0,
                                           "caught": 0, "repaired": 0, "final_violations": 0,
                                           "final_known": 0, "judge_unavailable": 0})
        c["attempted"] += 1
        if (record.get("outcome") or {}).get("judge_unavailable"):
            c["judge_unavailable"] += 1  # arm C without its judge: reported, never counted as C (or B)
            continue
        turns = record.get("turns") or []
        if not any(t.get("reached") for t in turns):
            c["not_started"] += 1
            continue
        slips = [t.get("slip") for t in turns]
        if any(s is True for s in slips):
            c["sessions"] += 1
            c["sessions_with_slip"] += 1
        elif all(s is False for s in slips):
            c["sessions"] += 1
        else:
            c["sessions_unknown"] += 1
        for t in turns:
            if t.get("slip") is None:
                c["turns_unknown"] += 1
                continue
            c["turns"] += 1
            c["turn_slips"] += bool(t["slip"])
            c["caught"] += bool(t.get("caught"))
            c["repaired"] += bool(t.get("repaired"))
        final = (record.get("outcome") or {}).get("final_structural")
        if final in ("pass", "violation"):
            c["final_known"] += 1
            c["final_violations"] += final == "violation"
    for c in cells.values():
        c["session_slip_lower95"], c["session_slip_upper95"] = _bounds(c["sessions_with_slip"], c["sessions"])
        c["turn_slip_lower95"], c["turn_slip_upper95"] = _bounds(c["turn_slips"], c["turns"])
        c["final_violation_lower95"], c["final_violation_upper95"] = _bounds(c["final_violations"],
                                                                             c["final_known"])
    return cells
