"""Claude Code Stop-hook adapter logic: bounded repair requests from the sensor.

Protocol (Claude Code hooks reference, retrieved 2026-11-19; see
``integrations/claude-code.md``):

- A ``Stop`` hook runs when the main agent finishes responding. It does not run
  after a user interrupt, and API errors fire ``StopFailure`` instead.
- Printing ``{"decision": "block", "reason": ...}`` on stdout with exit 0 keeps
  the conversation going; Claude receives ``reason`` as the explanation.
- Claude Code caps consecutive stop-hook continuations at 8, but the count
  resets whenever Claude calls a tool, so it does not bound a loop in which
  the agent edits files each round. This adapter keeps its own per-session
  budget (``max_repairs``) and resets it on the next ``UserPromptSubmit``.
- ``systemMessage`` is shown to the user as a warning.

Optional semantic stage (``run_semantic``, used by the experiment's arm C):
only after a structural pass. A semantic violation requests a repair from the
same budget; an abstention or a judge failure ends the loop with a warning
and records ``semantic_inconclusive``, never ``passed``.

Outcomes:

- pass: allow the stop; record ``passed``.
- violation or checker error with budget left: block with the diagnostic.
- budget exhausted: allow the stop (the loop must end) but report UNRESOLVED
  to the user and record ``unresolved``. Ending the loop is not passing.
- malformed input: the budget cannot be keyed to a session, so blocking could
  loop without bound. Report UNRESOLVED and do not run the check.
- state cannot be read or written (for example an unwritable state directory):
  a repair request that is not recorded would not count against the budget, so
  report UNRESOLVED and do not block. A failed reset on ``UserPromptSubmit``
  warns but never blocks the prompt.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

from gates.result import SensorResult, Status, format_diagnostic
from gates.semantic import JudgeOutcome, format_outcome

DEFAULT_MAX_REPAIRS = 3
_STATE_FILE = re.compile(r"^[0-9a-f]{32}\.json$")


@dataclass(frozen=True)
class HookOutcome:
    exit_code: int
    stdout: str = ""
    stderr: str = ""


@dataclass
class SessionState:
    repairs_requested: int = 0
    outcome: str = "open"  # open | passed | unresolved | semantic_inconclusive
    last_status: str | None = None
    last_fingerprint: str | None = None


class CorruptState(Exception):
    pass


def session_key(session_id: str) -> str:
    """A filesystem-safe, collision-resistant key for a session id."""
    return hashlib.sha256(session_id.encode("utf-8", "surrogatepass")).hexdigest()[:32]


class FileStateStore:
    """One small JSON file per session under ``directory``."""

    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)

    def _path(self, key: str) -> Path:
        return self.directory / f"{key}.json"

    def load(self, key: str) -> SessionState:
        path = self._path(key)
        if not path.exists():
            return SessionState()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            state = SessionState(**data)
            if type(state.repairs_requested) is not int or state.repairs_requested < 0:
                raise ValueError("bad repair count")
            return state
        except (OSError, ValueError, TypeError) as exc:
            raise CorruptState(str(exc)) from exc

    def save(self, key: str, state: SessionState) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self._path(key)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(state), indent=2), encoding="utf-8")
        tmp.replace(path)

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def reset_all(self) -> int:
        """Remove every session state file (and nothing else). Returns the count."""
        if not self.directory.is_dir():
            return 0
        removed = 0
        for path in self.directory.iterdir():
            if path.is_file() and _STATE_FILE.match(path.name):
                path.unlink()
                removed += 1
        return removed


def _json(payload: dict) -> str:
    return json.dumps(payload)


def _unresolved_message(detail: str) -> str:
    return (
        f"Architecture gate UNRESOLVED: {detail} This candidate has not passed the "
        "architecture check. Do not treat it as complete; fix it and run "
        "integrations/check_architecture.py, or rely on the CI check before merging."
    )


def handle_event(
    raw: str,
    *,
    run_sensor: Callable[[], SensorResult],
    store: FileStateStore,
    max_repairs: int = DEFAULT_MAX_REPAIRS,
    run_semantic: Callable[[], JudgeOutcome] | None = None,
) -> HookOutcome:
    try:
        event = json.loads(raw)
    except (json.JSONDecodeError, RecursionError, ValueError):
        event = None
    session_id = event.get("session_id") if isinstance(event, dict) else None
    name = event.get("hook_event_name") if isinstance(event, dict) else None
    if not isinstance(session_id, str) or not session_id or not isinstance(name, str):
        return HookOutcome(0, _json({"systemMessage": _unresolved_message(
            "the hook input could not be read, so the architecture check did not run."
        )}))

    key = session_key(session_id)

    if name == "UserPromptSubmit":
        # A new user turn gets a fresh repair budget.
        try:
            store.delete(key)
        except Exception as exc:  # never block the user's prompt over state
            return HookOutcome(0, _json({"systemMessage": (
                f"Architecture gate could not reset its repair budget ({exc!r}). "
                "Stop checks this turn may report UNRESOLVED instead of requesting repairs."
            )}))
        return HookOutcome(0)
    if name != "Stop":
        return HookOutcome(0)

    try:
        result = run_sensor()
    except Exception as exc:  # the adapter must translate, never crash into a pass
        result = SensorResult.checker_error(f"sensor crashed: {exc!r}", fingerprint=None)

    diagnostic = format_diagnostic(result)

    if result.status is Status.PASS and run_semantic is not None:
        # Optional semantic stage: only a structurally passing candidate is judged.
        try:
            semantic = run_semantic()
        except Exception as exc:  # a crashed judge is unresolved, never a pass
            semantic = JudgeOutcome("inconclusive", f"semantic stage crashed: {exc!r}",
                                    provider_failed=True)
        semantic_text = format_outcome(semantic)
        if semantic.status == "violation":
            return _request_repair(key, store, max_repairs, "semantic violation",
                                   semantic_text, result, semantic.status)
        if semantic.status != "pass":
            # Abstentions and judge failures end the loop without a pass: asking
            # for repairs against an unanswered question could loop and spend.
            state = SessionState(0, "semantic_inconclusive", result.status.value, result.fingerprint)
            try:
                store.save(key, state)
            except Exception:
                pass  # the message below is the record
            return HookOutcome(0, _json({"systemMessage": (
                f"{diagnostic.splitlines()[0]}\n{semantic_text}\n"
                "Architecture gate: the structural check passed but the semantic check did not "
                "produce a verdict, so this candidate has not passed the semantic rule."
            )}))
        diagnostic = f"{diagnostic}\n{semantic_text}"

    if result.status is Status.PASS:
        try:
            store.save(key, SessionState(0, "passed", result.status.value, result.fingerprint))
        except Exception as exc:
            diagnostic += (
                f"\n(Architecture gate: the pass could not be recorded in session state: {exc!r}.)"
            )
        return HookOutcome(0, _json({"systemMessage": diagnostic}))

    label = "violation" if result.status is Status.VIOLATION else "checker error"
    return _request_repair(key, store, max_repairs, label, diagnostic, result, result.status.value)


def _request_repair(key: str, store: FileStateStore, max_repairs: int, label: str,
                    diagnostic: str, result: SensorResult, last_status: str) -> HookOutcome:
    """Block with ``diagnostic`` while the session's repair budget lasts."""
    first_line = diagnostic.splitlines()[0]

    try:
        state = store.load(key)
    except CorruptState:
        # Fail closed: a corrupt budget cannot be trusted to stay bounded.
        state = SessionState(repairs_requested=max_repairs, outcome="unresolved")
    except Exception as exc:
        return _storage_failure(label, first_line, exc)

    state.last_status = last_status
    state.last_fingerprint = result.fingerprint

    if state.repairs_requested >= max_repairs:
        state.outcome = "unresolved"
        try:
            store.save(key, state)
        except Exception:
            pass  # the loop is ending anyway; the message below is the record
        return HookOutcome(0, _json({"systemMessage": _unresolved_message(
            f"still a {label} after {max_repairs} repair request(s) this turn. "
            f"Last result: {first_line}"
        )}))

    state.repairs_requested += 1
    state.outcome = "open"
    try:
        # Record the request *before* making it: an unrecorded request would not
        # count against the budget, so the loop could continue without bound.
        store.save(key, state)
    except Exception as exc:
        return _storage_failure(label, first_line, exc)
    reason = (
        f"{diagnostic}\n\n"
        f"(Architecture gate: repair request {state.repairs_requested} of {max_repairs} "
        "this turn. Fix the code and finish again; the check reruns on the whole package.)"
    )
    return HookOutcome(0, _json({"decision": "block", "reason": reason}))


def _storage_failure(label: str, first_line: str, exc: BaseException) -> HookOutcome:
    """The repair budget cannot be read or recorded: end the loop, UNRESOLVED."""
    return HookOutcome(0, _json({"systemMessage": _unresolved_message(
        f"a {label} was found, but the repair budget could not be read or recorded "
        f"({exc!r}), so no repair was requested. Last result: {first_line}"
    )}))
