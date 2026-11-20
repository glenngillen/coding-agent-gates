"""Shared spend ledger for every paid judge call and agent run in the experiment.

One JSON file (default ``experiment/runs/spend-ledger.json``) records every
piece of paid work against a single hard cap (US$100, decided 2026-11-19).
Every judge call and every agent run follows the same protocol:

1. ``begin``: reserve an upper bound on what the work can cost. The ledger
   refuses (``SpendCapExceeded``) if the amount already committed plus this
   reservation would exceed the cap, so work that might cross the cap never
   starts.
2. ``finish``: replace the reservation with the actual cost and usage.
3. ``fail``: the work stopped early. A known actual cost replaces the
   reservation; an unknown one keeps the reservation as a conservative charge
   and marks the usage as missing.

"Committed" is the sum of every entry's charge: its actual cost when known,
otherwise its reservation (open entries and failures with unknown usage). The
ledger's own guarantee is conditional: the cap holds as long as each actual
cost stays within its reservation. Making that true is the caller's job: a
paid adapter must reserve a worst case it can defend and constrain the work
so that the worst case holds. ``gates.claude_cli_judge`` derives its
reservation from capped input and output tokens, the highest model rates and
the CLI's documented budget overshoot. If an actual cost ever exceeds its
reservation it is still recorded (the money is already spent) and flagged,
and later work is refused accordingly; recording an overrun is accounting,
not prevention.

Amounts are ``decimal.Decimal`` US dollars, serialised as strings, so totals
are exact. The file layer serialises concurrent writers with an exclusive
``fcntl`` lock on a sibling ``.lock`` file (POSIX only) and replaces the file
atomically.
"""

from __future__ import annotations

import contextlib
import json
import os
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

SCHEMA = "coding-agent-gates/spend-ledger/v1"
CAP_USD = Decimal("100")
KINDS = ("judge", "agent")
STATUSES = ("open", "finished", "failed")
EXAMPLE_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PATH = EXAMPLE_ROOT / "experiment" / "runs" / "spend-ledger.json"


class LedgerError(Exception):
    """The ledger file or an operation on it is invalid."""


class SpendCapExceeded(Exception):
    """Starting this work could take committed spend over the cap."""

    def __init__(self, committed: Decimal, reserve: Decimal, cap: Decimal):
        self.committed, self.reserve, self.cap = committed, reserve, cap
        super().__init__(
            f"refused: committed US${committed} + reservation US${reserve} "
            f"would exceed the US${cap} cap (remaining US${cap - committed})")


def _money(value: Any, what: str) -> Decimal:
    try:
        amount = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise LedgerError(f"{what} is not a number: {value!r}") from None
    if not amount.is_finite() or amount < 0:
        raise LedgerError(f"{what} must be a finite, non-negative amount: {value!r}")
    return amount


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class Entry:
    id: str
    kind: str
    label: str
    status: str
    reserved_usd: Decimal
    started_at: str
    actual_usd: Decimal | None = None
    usage: dict | None = None
    finished_at: str | None = None
    note: str = ""

    @property
    def charged_usd(self) -> Decimal:
        return self.reserved_usd if self.actual_usd is None else self.actual_usd

    def to_json(self) -> dict:
        return {
            "id": self.id, "kind": self.kind, "label": self.label, "status": self.status,
            "reserved_usd": str(self.reserved_usd),
            "actual_usd": None if self.actual_usd is None else str(self.actual_usd),
            "charged_usd": str(self.charged_usd),
            "usage": self.usage, "started_at": self.started_at,
            "finished_at": self.finished_at, "note": self.note,
        }

    @classmethod
    def from_json(cls, data: Any) -> "Entry":
        if not isinstance(data, dict):
            raise LedgerError("entry is not an object")
        try:
            kind, status = data["kind"], data["status"]
            entry = cls(
                id=str(data["id"]), kind=kind, label=str(data["label"]), status=status,
                reserved_usd=_money(data["reserved_usd"], "reserved_usd"),
                started_at=str(data["started_at"]),
                actual_usd=(None if data.get("actual_usd") is None
                            else _money(data["actual_usd"], "actual_usd")),
                usage=data.get("usage"), finished_at=data.get("finished_at"),
                note=str(data.get("note", "")),
            )
        except KeyError as exc:
            raise LedgerError(f"entry missing field {exc}") from None
        if kind not in KINDS or status not in STATUSES:
            raise LedgerError(f"entry has unknown kind/status {kind!r}/{status!r}")
        if entry.usage is not None and not isinstance(entry.usage, dict):
            raise LedgerError("entry usage must be an object or null")
        return entry


@dataclass(frozen=True)
class Ledger:
    cap_usd: Decimal = CAP_USD
    entries: tuple[Entry, ...] = field(default_factory=tuple)

    @property
    def committed_usd(self) -> Decimal:
        return sum((e.charged_usd for e in self.entries), Decimal(0))

    @property
    def actual_usd(self) -> Decimal:
        return sum((e.actual_usd for e in self.entries if e.actual_usd is not None), Decimal(0))

    @property
    def remaining_usd(self) -> Decimal:
        return self.cap_usd - self.committed_usd

    def totals_by_kind(self) -> dict[str, str]:
        return {k: str(sum((e.charged_usd for e in self.entries if e.kind == k), Decimal(0)))
                for k in KINDS}

    def entry(self, entry_id: str) -> Entry:
        for e in self.entries:
            if e.id == entry_id:
                return e
        raise LedgerError(f"no ledger entry {entry_id!r}")

    def to_json(self) -> dict:
        return {
            "schema": SCHEMA, "currency": "USD", "cap_usd": str(self.cap_usd),
            "committed_usd": str(self.committed_usd), "actual_usd": str(self.actual_usd),
            "remaining_usd": str(self.remaining_usd),
            "committed_by_kind_usd": self.totals_by_kind(),
            "entries": [e.to_json() for e in self.entries],
        }

    @classmethod
    def from_json(cls, data: Any) -> "Ledger":
        if not isinstance(data, dict) or data.get("schema") != SCHEMA:
            raise LedgerError(f"not a {SCHEMA} document")
        entries = data.get("entries")
        if not isinstance(entries, list):
            raise LedgerError("entries must be a list")
        parsed = tuple(Entry.from_json(e) for e in entries)
        if len({e.id for e in parsed}) != len(parsed):
            raise LedgerError("duplicate entry ids")
        return cls(_money(data.get("cap_usd"), "cap_usd"), parsed)


# --- pure operations -------------------------------------------------------

def check(ledger: Ledger, reserve: Decimal) -> None:
    """Raise ``SpendCapExceeded`` unless ``reserve`` more can be committed."""
    reserve = _money(reserve, "reservation")
    if ledger.committed_usd + reserve > ledger.cap_usd:
        raise SpendCapExceeded(ledger.committed_usd, reserve, ledger.cap_usd)


def begin(ledger: Ledger, kind: str, label: str, reserve: Decimal, *,
          entry_id: str | None = None, now: str | None = None) -> tuple[Ledger, str]:
    if kind not in KINDS:
        raise LedgerError(f"unknown kind {kind!r}")
    reserve = _money(reserve, "reservation")
    if reserve == 0:
        raise LedgerError("reservation must be positive: paid work always has an upper bound")
    check(ledger, reserve)
    entry_id = entry_id or uuid.uuid4().hex
    if any(e.id == entry_id for e in ledger.entries):
        raise LedgerError(f"duplicate entry id {entry_id!r}")
    entry = Entry(entry_id, kind, label, "open", reserve, now or _now())
    return replace(ledger, entries=ledger.entries + (entry,)), entry_id


def _close(ledger: Ledger, entry_id: str, status: str, actual: Decimal | None,
           usage: dict | None, note: str, now: str | None) -> Ledger:
    current = ledger.entry(entry_id)
    if current.status != "open":
        raise LedgerError(f"entry {entry_id!r} is already {current.status}")
    if actual is not None:
        actual = _money(actual, "actual cost")
        if actual > current.reserved_usd:
            note = (note + "; " if note else "") + (
                f"actual US${actual} exceeded reservation US${current.reserved_usd}")
    closed = replace(current, status=status, actual_usd=actual, usage=usage,
                     finished_at=now or _now(), note=note)
    return replace(ledger, entries=tuple(closed if e.id == entry_id else e for e in ledger.entries))


def finish(ledger: Ledger, entry_id: str, actual: Decimal, usage: dict | None = None, *,
           note: str = "", now: str | None = None) -> Ledger:
    if actual is None:
        raise LedgerError("finish needs the actual cost; use fail() when it is unknown")
    return _close(ledger, entry_id, "finished", actual, usage, note, now)


def fail(ledger: Ledger, entry_id: str, actual: Decimal | None = None,
         usage: dict | None = None, *, note: str = "", now: str | None = None) -> Ledger:
    if actual is None:
        note = (note + "; " if note else "") + "usage unknown: reservation kept as the charge"
    return _close(ledger, entry_id, "failed", actual, usage, note, now)


# --- file layer --------------------------------------------------------------

@contextlib.contextmanager
def _locked(path: Path) -> Iterator[None]:
    import fcntl  # POSIX only; imported lazily so the pure core works everywhere

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path.with_name(path.name + ".lock"), "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def load(path: Path = DEFAULT_PATH, cap: Decimal = CAP_USD) -> Ledger:
    path = Path(path)
    if not path.exists():
        return Ledger(_money(cap, "cap"))
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LedgerError(f"cannot read ledger {path}: {exc}") from None
    ledger = Ledger.from_json(data)
    if ledger.cap_usd != _money(cap, "cap"):
        raise LedgerError(f"ledger cap US${ledger.cap_usd} differs from requested US${cap}")
    return ledger


def _save(path: Path, ledger: Ledger) -> None:
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(ledger.to_json(), indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


@contextlib.contextmanager
def transaction(path: Path = DEFAULT_PATH, cap: Decimal = CAP_USD) -> Iterator[list[Ledger]]:
    """Lock, load, let the caller replace ``box[0]``, then save atomically."""
    path = Path(path)
    with _locked(path):
        box = [load(path, cap)]
        yield box
        _save(path, box[0])


def begin_run(path: Path, kind: str, label: str, reserve: Decimal, cap: Decimal = CAP_USD) -> str:
    with transaction(path, cap) as box:
        box[0], entry_id = begin(box[0], kind, label, reserve)
    return entry_id


def finish_run(path: Path, entry_id: str, actual: Decimal, usage: dict | None = None,
               note: str = "", cap: Decimal = CAP_USD) -> None:
    with transaction(path, cap) as box:
        box[0] = finish(box[0], entry_id, actual, usage, note=note)


def fail_run(path: Path, entry_id: str, actual: Decimal | None = None, usage: dict | None = None,
             note: str = "", cap: Decimal = CAP_USD) -> None:
    with transaction(path, cap) as box:
        box[0] = fail(box[0], entry_id, actual, usage, note=note)


@dataclass(frozen=True)
class FileSpendGuard:
    """The begin/finish/fail protocol bound to one ledger file and kind of work.

    Paid adapters (the live judge, the agent runner) take one of these, so they
    cannot start work without consulting the shared ledger.
    """

    path: Path = DEFAULT_PATH
    kind: str = "judge"
    cap: Decimal = CAP_USD

    def begin(self, label: str, reserve: Decimal) -> str:
        return begin_run(self.path, self.kind, label, reserve, self.cap)

    def finish(self, entry_id: str, actual: Decimal, usage: dict | None = None, note: str = "") -> None:
        finish_run(self.path, entry_id, actual, usage, note, self.cap)

    def fail(self, entry_id: str, actual: Decimal | None = None, usage: dict | None = None,
             note: str = "") -> None:
        fail_run(self.path, entry_id, actual, usage, note, self.cap)

    def remaining(self) -> Decimal:
        with _locked(Path(self.path)):
            return load(self.path, self.cap).remaining_usd
