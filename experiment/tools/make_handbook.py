#!/usr/bin/env python3
"""Generate experiment/v4/instructions/handbook.md (deterministic; run once before the version 4 freeze).

    .venv/bin/python experiment/tools/make_handbook.py

The output is a large monorepo-style instruction file: fifteen general sections and templated
per-team service rules, about 160,000 characters, with the version 2 Architecture section
(the import rule, verbatim) inserted about 60% of the way down. The generated file is what
the study freezes; this script is kept so readers can see how it was made.
"""
import random

AREAS = {
 "Logging": ["Use the structured logger from `platform.logging`; never call `print` in service code.", "Log at `info` for state changes and `debug` for anything per-item in a loop.", "Never log email addresses, card numbers or access tokens; log the id instead.", "Every log line for a request carries the `request_id` field.", "Do not log and re-raise the same exception at two levels.", "Warnings are for things an operator should look at within a day."],
 "Error handling": ["Raise the narrowest exception that describes the failure.", "Do not catch `Exception` unless you re-raise or convert it at a boundary.", "Error messages are lower case with no trailing full stop.", "User-facing errors never include stack traces or internal ids.", "Retry only idempotent operations, at most three times, with jitter.", "A timeout is an error, not an empty result."],
 "Naming": ["Modules are lower_snake_case; classes are PascalCase; constants are UPPER_SNAKE_CASE.", "Boolean names read as questions: `is_active`, `has_stock`.", "Do not abbreviate domain words: `customer`, not `cust`.", "Field names carry their unit: `total_cents`, `timeout_s`.", "Test names read as sentences about behaviour.", "Avoid `utils` and `helpers` modules; name the module for what it holds."],
 "Testing": ["Every behaviour change comes with a test that fails without it.", "Tests drive public interfaces, not private attributes.", "No sleeping in tests; inject a clock.", "Use the shared fixtures before writing a new one.", "A test asserts one behaviour; split it if the name needs 'and'.", "Do not mark a test as skipped without a linked ticket."],
 "Dependencies": ["Do not add a third-party dependency without platform review.", "Pin exact versions in lock files; ranges only in library manifests.", "Prefer the standard library when the difference is a few lines.", "Remove a dependency in the same change that removes its last use.", "Vendored code lives under `third_party/` and is never edited in place.", "Licences other than MIT, BSD and Apache-2.0 need legal sign-off."],
 "API design": ["Responses are JSON objects, never bare arrays.", "Use 400 for malformed input, 404 for unknown ids and 409 for conflicts with current state.", "Lists have a documented, deterministic order.", "Do not remove or rename a response field without a deprecation window.", "Pagination uses opaque cursors, not page numbers.", "Timestamps are ISO 8601 in UTC."],
 "Security": ["Validate input at the boundary and trust nothing from a client.", "Secrets come from the secret manager; never from the repository or an environment default.", "Use parameterised queries; never build SQL with string formatting.", "Authorisation checks live next to the action they protect.", "Do not disable TLS verification, even in tests.", "Uploaded file names are untrusted input."],
 "Performance": ["Measure before optimising, and keep the benchmark with the change.", "No N+1 lookups in request paths; batch them.", "Cache only what you can invalidate.", "Streams over lists for anything unbounded.", "A request path allocates no more than it must; avoid copying large payloads.", "Set a timeout on every outbound call."],
 "Data and migrations": ["Migrations are forwards-only and safe to run twice.", "Add a column as nullable first; backfill; then tighten.", "Never rename a column in one step.", "Money is integer cents; never floats.", "Deleting data needs a retention review.", "Every table has a primary key and created/updated timestamps."],
 "Code style": ["Type-annotate every function signature.", "Prefer early returns over nested conditionals.", "No wildcard imports; absolute imports only.", "Line length 110; double quotes for strings.", "No commented-out code.", "Dataclasses in domain packages are frozen."],
 "Reviews and git": ["Keep changes scoped to the request.", "Commit subjects are imperative and under 72 characters.", "Do not commit unless asked to.", "Never rewrite history on `main`.", "Unrelated clean-ups go in their own change.", "If a request is ambiguous, choose the reading closest to existing behaviour and say so."],
 "Documentation": ["Public functions have a one-line docstring in the imperative mood.", "Update the README in the same change as the behaviour.", "Diagrams live next to the code they describe.", "Do not document what the code already says.", "Decision records go in `docs/adr/` and are never edited after acceptance.", "Runbooks name the alert that leads to them."],
 "Observability": ["Every service exports request count, error count and latency.", "Metric names are `service_noun_unit`.", "Alerts page only for user-visible impact.", "Dashboards are code; do not hand-edit them.", "Trace ids propagate through every outbound call.", "Sampling rates are configuration, not constants."],
 "Configuration": ["Configuration is read once at start-up and passed in.", "No environment lookups below the composition root.", "Feature flags default to off and have an owner and an expiry.", "Do not branch on environment name in business code.", "Defaults live in one place.", "Unknown configuration keys are an error."],
 "Concurrency": ["Shared mutable state needs an owner; say who in a comment.", "Prefer message passing over locks.", "Never hold a lock across I/O.", "Background jobs are idempotent.", "Cancellation is cooperative; check for it in long loops.", "Thread pools are sized in configuration."],
}
TEAMS = ["Payments", "Catalogue", "Fulfilment", "Accounts", "Search", "Notifications", "Reporting", "Returns", "Pricing", "Partner API",
         "Back office", "Mobile gateway", "Fraud", "Loyalty", "Tax", "Shipping rates", "Reviews", "Recommendations", "Imports", "Billing"]
TEAM_RULES = ["The {t} team owns `services/{s}/`; ask before changing its public interface.",
              "In `services/{s}/`, {rule}", "{t} endpoints are versioned under `/v{n}/{s}`.",
              "{t} jobs run in the `{s}-batch` queue and must finish within {m} minutes.",
              "Changes to `services/{s}/schema/` need a migration reviewed by the {t} team.",
              "The {t} on-call rota is the escalation path for `services/{s}/` alerts."]
ARCH = """## Architecture

- `src/orders/controllers/` decodes requests, calls application services and
  maps their results to responses. Controller modules must not import
  anything from `orders.infrastructure`. Reach storage only through the
  application layer.
- Business decisions belong in `src/orders/application/`: pricing, discount
  eligibility, which orders or customers qualify for something, stock rules
  and business limits or thresholds. A controller must not make these
  decisions, even with data a service returns to it. Checking that a request
  has the right shape and types is the controller's job.
- `src/orders/infrastructure/` holds storage (in-memory repositories). Only
  the application layer uses it.
- `src/orders/domain/` holds plain data shared by every layer.
- `src/orders/wiring.py` is the one place that constructs every layer.
"""
BULLET = "- Controller modules must not import anything from `orders.infrastructure`; reach storage only through the application layer."

def build(head: str, tail: str, target_chars: int, style: str = "section", position: float = 0.6) -> str:
    rng = random.Random(7)
    blocks = []
    for area, rules in AREAS.items():
        blocks.append(f"## {area}\n\n" + "\n".join(f"- {r}" for r in rules) + "\n")
    i = 0
    while sum(map(len, blocks)) < target_chars:
        t = TEAMS[i % len(TEAMS)]; s = t.lower().replace(" ", "-"); round_ = i // len(TEAMS) + 1
        area_rules = [r for rs in AREAS.values() for r in rs]
        lines = []
        for tmpl in rng.sample(TEAM_RULES, 4) + ["In `services/{s}/`, {rule}"] * 4:
            rule = rng.choice(area_rules); rule = rule[0].lower() + rule[1:]
            lines.append("- " + tmpl.format(t=t, s=s, rule=rule, n=rng.randint(1, 4), m=rng.choice([5, 10, 15, 30, 60])))
        blocks.append(f"## {t} service" + (f" (part {round_})" if round_ > 1 else "") + "\n\n" + "\n".join(lines) + "\n")
        i += 1
    at = int(len(blocks) * position)
    if style == "section":
        blocks.insert(at, ARCH)
    else:
        blocks[at] = blocks[at].rstrip("\n") + "\n" + BULLET + "\n"
    return head + "\n".join(blocks) + "\n" + tail


if __name__ == "__main__":
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    text = (root / "experiment" / "v2" / "instruction.md").read_text()
    start, end = text.index("## Architecture"), text.index("## Working")
    out = root / "experiment" / "v4" / "instructions" / "handbook.md"
    out.write_text(build(text[:start], text[end:], 160_000, "section"))
    print(f"wrote {out.relative_to(root)} ({len(out.read_text())} characters)")
