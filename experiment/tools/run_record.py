"""Run records: parse raw run outputs into one record per attempted run.

Pure functions only; ``run_pilot.py`` does the I/O. A record keeps outcomes
separate (completion, behaviour, structure, the semantic judge's output,
tampering, termination) and keeps missing data missing:

- usage the CLI did not report is ``None`` with a reason, never zero;
- a repair loop that did not converge is ``censored``, never zero cycles;
- arm A has no development feedback, so its repair fields are "not
  applicable", not zero;
- the semantic label is always ``None`` (no independent human labels).

``evidence_kind`` separates real pilot records from synthetic records built
by the unit tests; summaries refuse to mix them.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from decimal import Decimal, InvalidOperation
from typing import Any

SCHEMA = "coding-agent-gates/run-record/v1"
EVIDENCE_KINDS = ("real", "synthetic-test")
TERMINATIONS = ("completed", "budget_exhausted", "wall_timeout", "cli_error", "not_started_cap",
                "not_runnable")
GATE_STATES = ("no_gate", "passed", "unresolved", "semantic_inconclusive", "interrupted", "missing")
COST_BASIS = ("total_cost_usd / costUSD reported by the Claude Code CLI: API-equivalent list-price "
              "estimates; under a subscription login they are notional, not an invoice")
SETTINGS_NOT_CHECKED = "not_checked"
CI_QUEUE_NOTE = "not applicable: the end-of-turn placement has no CI queue"
TRUNCATE_AT = 4000

# --- stream-json transcript ------------------------------------------------------


def parse_stream(lines: Iterable[str]) -> tuple[list[dict], dict | None, list[str]]:
    """Parse ``--output-format stream-json`` lines. Returns (events, the final
    ``result`` event or None, unparseable lines). Never raises."""
    events, bad, result = [], [], None
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except (json.JSONDecodeError, RecursionError, ValueError):
            bad.append(line[:200])
            continue
        if not isinstance(obj, dict):
            bad.append(line[:200])
            continue
        events.append(obj)
        if obj.get("type") == "result":
            result = obj
    return events, result, bad


def _int(value: Any) -> int | None:
    return value if type(value) is int and value >= 0 else None


def _money(value: Any) -> Decimal | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        amount = Decimal(str(value))
    except InvalidOperation:
        return None
    return amount if amount.is_finite() and amount >= 0 else None


def agent_usage(result: Mapping[str, Any] | None) -> dict[str, Any]:
    """Usage categories per model from the CLI's result event. Missing stays missing."""
    if not isinstance(result, Mapping):
        return {"missing": "no result event: the CLI reported no usage", "cost_usd": None,
                "by_model": None, "cost_basis": COST_BASIS}
    by_model = {}
    model_usage = result.get("modelUsage")
    if isinstance(model_usage, Mapping):
        for model, u in sorted(model_usage.items()):
            if not isinstance(u, Mapping):
                by_model[model] = None
                continue
            cost = _money(u.get("costUSD"))
            by_model[model] = {
                "input_tokens": _int(u.get("inputTokens")),
                "output_tokens": _int(u.get("outputTokens")),
                "cache_read_input_tokens": _int(u.get("cacheReadInputTokens")),
                "cache_creation_input_tokens": _int(u.get("cacheCreationInputTokens")),
                "cost_usd": None if cost is None else str(cost),
            }
    cost = _money(result.get("total_cost_usd"))
    return {
        "missing": None if cost is not None else "result event has no usable total_cost_usd",
        "cost_usd": None if cost is None else str(cost),
        "by_model": by_model or None,
        "num_turns": _int(result.get("num_turns")),
        "cost_basis": COST_BASIS,
    }


def termination(result: Mapping[str, Any] | None, *, timed_out: bool, exit_code: int | None) -> str:
    if timed_out:
        return "wall_timeout"
    if not isinstance(result, Mapping):
        return "cli_error"
    subtype = result.get("subtype")
    if subtype == "error_max_budget_usd":
        return "budget_exhausted"
    if subtype == "success" and result.get("is_error") is False and exit_code == 0:
        return "completed"
    return "cli_error"


# --- hook events -----------------------------------------------------------------


def parse_events(lines: Iterable[str]) -> tuple[list[dict], int]:
    """Hook event log lines -> (events, number of unparseable lines)."""
    events, bad = [], 0
    for line in lines:
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except (json.JSONDecodeError, RecursionError, ValueError):
            bad += 1
            continue
        if isinstance(obj, dict):
            events.append(obj)
        else:
            bad += 1
    return events, bad


def gate_state(arm_has_gate: bool, events: list[Mapping[str, Any]]) -> str:
    """The development gate's last word on the run."""
    if not arm_has_gate:
        return "no_gate"
    stops = [e for e in events if e.get("hook_event_name") == "Stop" or "sensor" in e]
    if not stops:
        return "missing"
    last = stops[-1]
    if last.get("decision") == "block":
        return "interrupted"  # the run ended while a repair was requested
    message = json.dumps(last.get("output", {}))
    semantic = last.get("semantic")
    if "UNRESOLVED" in message or last.get("adapter_error"):
        return "unresolved"
    if isinstance(semantic, Mapping) and semantic.get("status") != "pass":
        return "semantic_inconclusive"
    sensor = last.get("sensor")
    if isinstance(sensor, Mapping) and sensor.get("status") == "pass":
        return "passed"
    return "unresolved"


def repair_summary(arm_has_gate: bool, events: list[Mapping[str, Any]], state: str) -> dict[str, Any]:
    if not arm_has_gate:
        return {"applicable": False, "cycles": None, "censored": None,
                "note": "arm A receives no development-time architecture feedback",
                "checker_invocations": {"sensor": 0, "judge": 0}}
    blocks = sum(1 for e in events if e.get("decision") == "block")
    sensor_runs = sum(1 for e in events if isinstance(e.get("sensor"), Mapping))
    judge_calls = sum(len(e["semantic"].get("calls") or []) for e in events
                      if isinstance(e.get("semantic"), Mapping))
    converged = state == "passed"
    return {"applicable": True, "cycles": blocks, "censored": not converged,
            "note": None if converged else
            f"did not converge (gate state {state}); cycles is a lower bound, not a completed count",
            "checker_invocations": {"sensor": sensor_runs, "judge": judge_calls}}


TOKEN_CATEGORIES = ("input_tokens", "output_tokens", "cache_read_input_tokens",
                    "cache_creation_input_tokens")


def call_ledger_charge(call: Mapping[str, Any]) -> Decimal | None:
    """What the ledger kept as the charge for one started call.

    A call that recorded ``ledger_charged_usd`` says so directly. Otherwise the
    ledger's rule applies: a call whose cost is unknown keeps its whole
    reservation as the charge. Returns None only when neither is usable."""
    charged = _money(call.get("ledger_charged_usd"))
    if charged is not None:
        return charged
    cost = _money(call.get("cost_usd"))
    if cost is not None:
        return cost
    return _money(call.get("reservation_usd"))


def judge_usage(calls: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Sum judge calls' reported cost and usage.

    A call with unknown cost keeps the complete total unavailable, and the
    ledger charge held for it (its reservation, unless the call recorded a
    different charge) is kept in ``unknown_cost_held_usd``. Token categories
    are summed over the calls that reported them; ``tokens_missing_calls``
    counts, per category, the started calls that did not, so a partial sum is
    never mistaken for a complete one."""
    calls = list(calls)
    started = [c for c in calls if c.get("ledger_entry_id")]
    known = [_money(c.get("cost_usd")) for c in started]
    unknown_calls = [c for c, k in zip(started, known) if k is None]
    subtotal = sum((k for k in known if k is not None), Decimal(0))
    held_parts = [call_ledger_charge(c) for c in unknown_calls]
    held = sum((h for h in held_parts if h is not None), Decimal(0))
    tokens: dict[str, int] = {}
    missing = {key: 0 for key in TOKEN_CATEGORIES}
    for c in started:
        usage = c.get("usage")
        for key in TOKEN_CATEGORIES:
            v = _int(usage.get(key)) if isinstance(usage, Mapping) else None
            if v is None:
                missing[key] += 1
            else:
                tokens[key] = tokens.get(key, 0) + v
    return {"calls": len(calls), "started_calls": len(started), "unknown_cost_calls": len(unknown_calls),
            "cost_usd": None if unknown_calls else str(subtotal),
            "known_cost_subtotal_usd": str(subtotal),
            "unknown_cost_held_usd": str(held),
            "unknown_cost_unrecorded_charge_calls": sum(1 for h in held_parts if h is None),
            "tokens": tokens or None, "tokens_missing_calls": missing,
            "models": sorted({m for c in started for m in (c.get("models_reported") or [])}),
            "cost_basis": COST_BASIS}


def attempt_judge_usage(arm_has_gate: bool, events: Iterable[Mapping[str, Any]],
                        evaluation: Mapping[str, Any] | None) -> dict[str, Any]:
    """Development- and evaluation-judge usage for one attempt.

    Used for the final attempt and for every retried attempt, so judge spend
    incurred by work that was later retried is never dropped."""
    dev_calls = [c for e in events if isinstance(e.get("semantic"), Mapping)
                 for c in (e["semantic"].get("calls") or [])]
    return {
        "development_judge": judge_usage(dev_calls) if arm_has_gate else None,
        "evaluation_judge": judge_usage((evaluation or {}).get("semantic_judge_calls") or [])
        if evaluation else None,
    }


def check_seconds(events: Iterable[Mapping[str, Any]]) -> dict[str, float | None]:
    events = list(events)
    sensor = [e["sensor"]["seconds"] for e in events if isinstance(e.get("sensor"), Mapping)
              and isinstance(e["sensor"].get("seconds"), (int, float))]
    semantic = [e["semantic"]["seconds"] for e in events if isinstance(e.get("semantic"), Mapping)
                and isinstance(e["semantic"].get("seconds"), (int, float))]
    return {"sensor_s": round(sum(sensor), 3) if sensor else None,
            "judge_s": round(sum(semantic), 3) if semantic else None}


def judge_unavailable(events: Iterable[Mapping[str, Any]]) -> bool:
    return any(isinstance(e.get("semantic"), Mapping) and e["semantic"].get("provider_failed")
               for e in events)


# --- redaction ---------------------------------------------------------------------

SECRET_PATTERNS = (
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{10,}"),
    re.compile(r"(?i)(authorization|x-api-key|api[_-]?key|token)(\"?\s*[:=]\s*\"?)[A-Za-z0-9_\-\.]{16,}"),
)


def redact(text: str, replacements: Mapping[str, str]) -> str:
    """Replace local absolute paths (longest first) and anything secret-shaped."""
    for old in sorted(replacements, key=len, reverse=True):
        if old:
            text = text.replace(old, replacements[old])
    text = SECRET_PATTERNS[0].sub("<redacted-secret>", text)
    return SECRET_PATTERNS[1].sub(lambda m: m.group(1) + m.group(2) + "<redacted-secret>", text)


def redact_json(value: Any, replacements: Mapping[str, str]) -> Any:
    """``redact`` applied to every string in a JSON value."""
    if isinstance(value, str):
        return redact(value, replacements)
    if isinstance(value, list):
        return [redact_json(v, replacements) for v in value]
    if isinstance(value, dict):
        return {k: redact_json(v, replacements) for k, v in value.items()}
    return value


INIT_KEEP = ("type", "subtype", "cwd", "session_id", "tools", "model", "permissionMode",
             "apiKeySource", "claude_code_version", "output_style")


def sanitize_event(event: Mapping[str, Any]) -> dict[str, Any]:
    """Drop environment-specific listings (MCP servers, skills, plugins, agents)
    from the transcript's init event; they describe the building machine, not the run."""
    if event.get("type") == "system" and event.get("subtype") == "init":
        kept = {k: event[k] for k in INIT_KEEP if k in event}
        kept["omitted"] = sorted(k for k in event if k not in INIT_KEEP)
        return kept
    return dict(event)


def compact(value: Any, limit: int = TRUNCATE_AT) -> Any:
    """Truncate long strings in a JSON value, keeping the original's length and hash."""
    if isinstance(value, str):
        if len(value) <= limit:
            return value
        digest = hashlib.sha256(value.encode("utf-8", "surrogatepass")).hexdigest()
        return (value[:limit] + f"\n[truncated: {len(value)} characters, sha256 {digest}]")
    if isinstance(value, list):
        return [compact(v, limit) for v in value]
    if isinstance(value, dict):
        return {k: compact(v, limit) for k, v in value.items()}
    return value


# --- the record ----------------------------------------------------------------------


def build_record(*, evidence_kind: str, prepared: Mapping[str, Any], result: Mapping[str, Any] | None,
                 timed_out: bool, exit_code: int | None, attempt_s: float | None,
                 events: list[Mapping[str, Any]], evaluation: Mapping[str, Any] | None,
                 started_at: str | None, finished_at: str | None, environment: Mapping[str, Any],
                 ledger: Mapping[str, Any] | None, artifacts: Mapping[str, str],
                 infrastructure_retries: list[Mapping[str, Any]] | None = None,
                 interventions: list[Mapping[str, Any]] | None = None,
                 blind_id: str | None = None, not_runnable: str | None = None,
                 final_tree_sha256: str | None = None, notes: list[str] | None = None,
                 settings_integrity: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if evidence_kind not in EVIDENCE_KINDS:
        raise ValueError(f"evidence_kind must be one of {EVIDENCE_KINDS}")
    arm_has_gate = bool((prepared.get("settings") or {}).get("hooks"))
    state = gate_state(arm_has_gate, events)
    if not_runnable is None and judge_unavailable(events):
        not_runnable = "the live judge could not run during the run (provider failure)"
    # Whether the agent process ran at all, and how it ended, are kept apart
    # from the run's classification: an arm whose development judge was
    # unavailable never received its intended feedback, so the run is not
    # runnable even when the agent itself returned success. Its usage,
    # spend and artifacts stay in the record.
    not_started = bool(prepared.get("_not_started"))
    agent_started = not not_started and (result is not None or timed_out or exit_code is not None)
    agent_term = termination(result, timed_out=timed_out, exit_code=exit_code) if agent_started else None
    if not_started:
        term = "not_started_cap"
    elif not_runnable:
        term = "not_runnable"
    else:
        term = agent_term or termination(result, timed_out=timed_out, exit_code=exit_code)
    usage = agent_usage(result)
    plan = prepared.get("plan") or {}
    ev_judge = (evaluation or {}).get("semantic_judge") or None
    behavior = ((evaluation or {}).get("behavior") or {}).get("status")
    structural = ((evaluation or {}).get("structural") or {}).get("status")
    tampering = (evaluation or {}).get("tampering") or {}
    settings_detected = (settings_integrity or {}).get("detected")
    evaluator_detected = tampering.get("detected") if tampering else None
    if evaluator_detected is None and settings_detected is None:
        tampering_detected = None
    else:
        tampering_detected = bool(evaluator_detected or settings_detected)
    checks = check_seconds(events)
    judges = attempt_judge_usage(arm_has_gate, events, evaluation)
    return {
        "schema": SCHEMA,
        "evidence_kind": evidence_kind,
        "identity": {
            "pilot": prepared.get("pilot"), "run_id": prepared.get("run_id"),
            "task_id": prepared.get("task_id"), "arm": prepared.get("arm"),
            "repeat": prepared.get("repeat"), "sequence": plan.get("sequence"),
            "position_in_task": plan.get("position_in_task"), "blind_id": blind_id,
            "baseline_commit": prepared.get("baseline_commit"),
            "baseline_tree_sha256": prepared.get("workspace_tree_sha256"),
            "final_tree_sha256": final_tree_sha256 or (evaluation or {}).get("snapshot_tree_sha256"),
            "prompt_sha256": prepared.get("prompt_sha256"), "task_sha256": prepared.get("task_sha256"),
            "instruction_sha256": prepared.get("instruction_sha256"),
            "arms_sha256": prepared.get("arms_sha256"), "settings_sha256": prepared.get("settings_sha256"),
            "frozen_manifest_sha256": (evaluation or {}).get("frozen_manifest_sha256"),
            "agent_model_requested": (prepared.get("agent_config") or {}).get("model"),
            "agent_models_reported": sorted((usage.get("by_model") or {}).keys()) or None,
            "agent_effort": (prepared.get("agent_config") or {}).get("effort"),
            "seed": "unsupported by the Claude Code CLI; not set",
            "session": "fresh process, --no-session-persistence",
            "started_at": started_at, "finished_at": finished_at,
            "environment": dict(environment),
        },
        "outcome": {
            "termination": term,
            "completed_within_budget": term == "completed",
            "not_runnable": not_runnable,
            "agent_started": agent_started,
            "agent_termination": agent_term,
            "behavior": behavior,
            "structural": structural,
            "semantic_judge": ev_judge.get("status") if isinstance(ev_judge, Mapping) else None,
            "semantic_label": None,
            "semantic_label_note": "no independent human labels (Decisions, 2026-11-19)",
            "tampering_detected": tampering_detected,
            "settings_file_check": (settings_integrity or {}).get("status") or SETTINGS_NOT_CHECKED,
            "baseline_tests_modified": tampering.get("baseline_tests_modified") if tampering else None,
            "gate_final_state": state,
            "submission": "synthetic final submission; not a merge",
        },
        "repair": repair_summary(arm_has_gate, events, state),
        "usage": {
            "agent": usage,
            **judges,
        },
        "time": {
            "attempt_s": attempt_s,
            "agent_reported_s": (_int((result or {}).get("duration_ms")) or 0) / 1000
            if _int((result or {}).get("duration_ms")) is not None else None,
            "model_api_s": (_int((result or {}).get("duration_api_ms")) or 0) / 1000
            if _int((result or {}).get("duration_api_ms")) is not None else None,
            "check_sensor_s": checks["sensor_s"], "check_judge_s": checks["judge_s"],
            "ci_queue_s": None, "ci_queue_note": CI_QUEUE_NOTE,
            "clock": "time.monotonic() around the agent process; CLI-reported durations as given",
        },
        "interventions": list(interventions or []),
        "infrastructure_retries": list(infrastructure_retries or []),
        "ledger": dict(ledger) if ledger else None,
        "artifacts": dict(artifacts),
        "settings_integrity": dict(settings_integrity) if settings_integrity else None,
        "notes": list(notes or []),
    }


REQUIRED_TOP = ("schema", "evidence_kind", "identity", "outcome", "repair", "usage", "time",
                "interventions", "infrastructure_retries", "ledger", "artifacts", "notes")


def validate_record(record: Any) -> list[str]:
    """Structural checks used by the summarizer. Returns problems (empty = valid)."""
    if not isinstance(record, Mapping):
        return ["record is not an object"]
    problems = [f"missing {k}" for k in REQUIRED_TOP if k not in record]
    if record.get("schema") != SCHEMA:
        problems.append(f"schema is {record.get('schema')!r}")
    if record.get("evidence_kind") not in EVIDENCE_KINDS:
        problems.append("unknown evidence_kind")
    outcome = record.get("outcome")
    if isinstance(outcome, Mapping):
        if outcome.get("termination") not in TERMINATIONS:
            problems.append(f"unknown termination {outcome.get('termination')!r}")
        if outcome.get("gate_final_state") not in GATE_STATES:
            problems.append("unknown gate_final_state")
        if outcome.get("semantic_label") is not None:
            problems.append("semantic_label must stay null without independent labels")
    else:
        problems.append("outcome is not an object")
    repair = record.get("repair")
    if isinstance(repair, Mapping) and repair.get("applicable") and repair.get("censored") is None:
        problems.append("applicable repair must say whether it is censored")
    return problems


def dumps(record: Mapping[str, Any]) -> str:
    return json.dumps(record, indent=2, sort_keys=False) + "\n"


def loads(text: str) -> dict[str, Any]:
    record = json.loads(text)
    problems = validate_record(record)
    if problems:
        raise ValueError("invalid run record: " + "; ".join(problems))
    return record
