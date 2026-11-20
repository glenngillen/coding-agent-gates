"""The canonical architecture sensor.

Runs ``lint-imports`` over the whole ``orders`` package with this example's
``.importlinter`` contract, then classifies the outcome as pass, violation or
checker error. Every gate placement (Claude Code Stop hook, pre-commit, CI)
calls this same code through ``integrations/check_architecture.py``.

Why classification needs the report text: lint-imports 2.17 exits 1 for broken
contracts *and* for syntax errors, invalid configuration and missing packages
(observed 2026-11-19). Treating "exit 1" as "violation" would misreport a
broken checker as an agent mistake; treating "exit 0" as "pass" without a
parsed summary would let an empty or misconfigured run through.
"""

from __future__ import annotations

import configparser
import hashlib
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path

from gates.cache import ResultCache
from gates.linter_output import Edge, LintReport, parse_lint_imports_output
from gates.result import SensorResult, Status, Violation
from gates.rules import REQUIRED_RULES

# Part of the fingerprint. Not bumped when ignored imports became violations:
# the old sensor reported them as checker errors, which are never cached, so no
# stored result can disagree with the new classification, and snapshot ids
# quoted in the walkthrough and the animations stay valid.
SENSOR_VERSION = "1"
CONFIG_FILE = ".importlinter"
SOURCE_DIR = "src"
CHECKED_PACKAGE = "orders"
TIMEOUT_SECONDS = 120


@dataclass(frozen=True)
class ProcessOutput:
    returncode: int
    stdout: str
    stderr: str


Runner = Callable[..., ProcessOutput]


def subprocess_runner(argv: list[str], *, cwd: Path, env: dict[str, str], timeout: float) -> ProcessOutput:
    completed = subprocess.run(
        argv, cwd=cwd, env=env, timeout=timeout, capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False,
    )
    return ProcessOutput(completed.returncode, completed.stdout, completed.stderr)


def locate_lint_imports() -> str | None:
    """Find lint-imports in the running interpreter's environment only.

    Falling back to whatever is on PATH could silently run a different
    version from the one pinned in requirements.lock.
    """
    return shutil.which("lint-imports", path=str(Path(sys.executable).parent))


def installed_import_linter_version() -> str | None:
    try:
        return metadata.version("import-linter")
    except metadata.PackageNotFoundError:
        return None


def _checked_files(root: Path) -> Iterable[Path]:
    package = root / SOURCE_DIR / CHECKED_PACKAGE
    if not package.is_dir():
        return []
    return sorted(
        p for p in package.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"
    )


def fingerprint(root: Path, *, tool_version: str | None, config: Path | None = None) -> str:
    """SHA-256 over everything that can change the sensor's answer.

    Includes each checked file's relative path and bytes (so additions, renames
    and deletions all change it), the contract configuration, the Import Linter
    version and this sensor's version. Also serves as the recorded identity of
    the snapshot a result describes. ``config`` defaults to ``root/.importlinter``.
    """
    digest = hashlib.sha256()

    def add(label: str, payload: bytes) -> None:
        digest.update(label.encode() + b"\0" + len(payload).to_bytes(8, "big") + payload)

    add("sensor", SENSOR_VERSION.encode())
    add("tool", (tool_version or "unknown").encode())
    config = Path(config) if config is not None else root / CONFIG_FILE
    add("config", config.read_bytes() if config.is_file() else b"<missing>")
    for path in _checked_files(root):
        add("file:" + path.relative_to(root).as_posix(), path.read_bytes())
    return digest.hexdigest()


_IGNORE_ENTRY = re.compile(r"^(?P<importer>\S+)\s*->\s*(?P<imported>\S+)$")
UNLISTED = "(entry not readable from the contract file)"


def ignored_imports_from_config(text: str) -> dict[str, tuple[str, ...]]:
    """Map each contract ``name`` to its ``ignore_imports`` entries, as written.

    Used only to *name* ignored imports in a diagnostic. lint-imports' report
    gives just a count, and it remains the authority on whether any import was
    ignored; an unreadable file therefore yields ``{}`` rather than an error.
    """
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    try:
        parser.read_string(text)
    except (configparser.Error, ValueError):
        return {}
    found: dict[str, tuple[str, ...]] = {}
    for section in parser.sections():
        if not section.startswith("importlinter:contract:"):
            continue
        name = parser.get(section, "name", fallback="").strip()
        raw = parser.get(section, "ignore_imports", fallback="")
        entries = tuple(line.strip() for line in raw.splitlines() if line.strip())
        if name and entries:
            found[name] = entries
    return found


def _ignored_violations(rule: str, count: int, entries: Iterable[str]) -> list[Violation]:
    violations = []
    for entry in entries:
        if match := _IGNORE_ENTRY.match(entry):
            edge = Edge(match.group("importer"), match.group("imported"))
        else:
            edge = Edge(entry, UNLISTED)
        violations.append(Violation(rule, edge, "ignored"))
    if not violations:
        noun = "import" if count == 1 else "imports"
        violations.append(Violation(rule, Edge(f"{count} ignored {noun}", UNLISTED), "ignored"))
    return violations


def classify(
    report: LintReport,
    exit_code: int,
    required_rules: Iterable[str],
    *,
    raw_output: str,
    fingerprint: str | None = None,
    tool_version: str | None = None,
    ignored_entries: Mapping[str, Iterable[str]] | None = None,
) -> SensorResult:
    """Classify a parsed report.

    ``ignored_entries`` (contract name -> ``ignore_imports`` lines) only names
    ignored imports; whether a rule has any comes from lint-imports' report.
    """
    required_rules = tuple(required_rules)
    def error(reason: str) -> SensorResult:
        return SensorResult.checker_error(
            reason, fingerprint=fingerprint, tool_version=tool_version,
            exit_code=exit_code, raw_output=raw_output,
        )

    if report.kept is None or report.broken is None:
        first = next((line.strip() for line in raw_output.splitlines() if line.strip()), "")
        return error(f"lint-imports did not produce a contract report: {first or 'no output'}")
    if not report.analyzed_files:
        return error("lint-imports analysed no files")
    missing = [rule for rule in required_rules if rule not in report.contracts]
    if missing:
        return error("required rule not evaluated: " + "; ".join(missing))

    broken = [name for name, state in report.contracts.items() if state == "BROKEN"]
    if broken and exit_code != 1:
        return error(f"contracts reported broken but lint-imports exited {exit_code}")
    if not broken and (exit_code != 0 or report.broken != 0):
        return error(f"contracts reported kept but lint-imports exited {exit_code}")

    violations: list[Violation] = []
    for name in broken:
        edges = report.edges.get(name, ())
        if not edges:
            return error(f"rule '{name}' reported broken but no offending import was parsed")
        violations.extend(Violation(name, edge) for edge in edges)
    entries = ignored_entries or {}
    for rule in required_rules:
        if count := report.ignored.get(rule, 0):
            violations.extend(_ignored_violations(rule, count, entries.get(rule, ())))

    if not violations:
        return SensorResult(Status.PASS, dict(report.contracts), (), None, fingerprint,
                            tool_version, exit_code, raw_output)
    return SensorResult(Status.VIOLATION, dict(report.contracts), tuple(violations), None,
                        fingerprint, tool_version, exit_code, raw_output)


def run_sensor(
    root: Path,
    *,
    runner: Runner = subprocess_runner,
    locate_tool: Callable[[], str | None] = locate_lint_imports,
    tool_version: Callable[[], str | None] = installed_import_linter_version,
    required_rules: Iterable[str] = REQUIRED_RULES,
    cache: ResultCache | None = None,
    timeout: float = TIMEOUT_SECONDS,
    config: Path | None = None,
) -> SensorResult:
    """Check ``root/src/orders`` against a contract file.

    ``config`` defaults to ``root/.importlinter``. The experiment passes a
    contract kept outside the checked copy (the development gate's or the
    independent evaluator's), so an edit inside the copy cannot change it.
    """
    root = Path(root)
    config = Path(config) if config is not None else root / CONFIG_FILE
    version = tool_version()
    try:
        snapshot = fingerprint(root, tool_version=version, config=config)
    except OSError as exc:
        return SensorResult.checker_error(f"could not read checked files: {exc}",
                                          fingerprint=None, tool_version=version)

    def error(reason: str, **extra) -> SensorResult:
        return SensorResult.checker_error(reason, fingerprint=snapshot, tool_version=version, **extra)

    if not config.is_file():
        return error(f"contract configuration {config.name} not found at {config}")
    if not (root / SOURCE_DIR / CHECKED_PACKAGE).is_dir():
        return error(f"checked package {SOURCE_DIR}/{CHECKED_PACKAGE} not found in {root}")
    tool = locate_tool()
    if not tool:
        return error(
            "lint-imports not found in this Python environment "
            f"({Path(sys.executable).parent}); install requirements.lock into .venv"
        )

    if cache is not None and (cached := cache.get(snapshot)) is not None:
        return cached

    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(root / SOURCE_DIR)] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else [])
    )
    # Wide, colourless output so the report is never wrapped mid-line.
    env.update({"COLUMNS": "1000", "NO_COLOR": "1", "TERM": "dumb"})
    argv = [tool, "--no-cache", "--no-logo", str(config)]
    try:
        output = runner(argv, cwd=root, env=env, timeout=timeout)
    except subprocess.TimeoutExpired:
        return error(f"lint-imports timed out after {timeout:g}s")
    except OSError as exc:
        return error(f"could not start lint-imports: {exc}")

    raw = output.stdout + (("\n" + output.stderr) if output.stderr else "")
    try:
        ignored_entries = ignored_imports_from_config(config.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError):
        ignored_entries = {}
    result = classify(
        parse_lint_imports_output(output.stdout + "\n" + output.stderr),
        output.returncode,
        required_rules,
        raw_output=raw,
        fingerprint=snapshot,
        tool_version=version,
        ignored_entries=ignored_entries,
    )
    if cache is not None:
        cache.put(result)
    return result
