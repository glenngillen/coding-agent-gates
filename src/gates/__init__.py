"""Architecture sensor and gate adapters for the order-service example.

This package is deliberately *outside* the ``orders`` root package that the
import contract checks. It contains:

- ``linter_output``: parser for lint-imports' text report.
- ``result``: the sensor result model, JSON form and diagnostic text.
- ``sensor``: the canonical full-package sensor (runs lint-imports, classifies).
- ``cache``: an optional result cache keyed by the checked-input fingerprint.
- ``stop_hook``: Claude Code Stop-hook adapter logic (bounded repair requests).
- ``semantic``: the optional semantic-judge boundary (rubric, verdict parsing).

Adapters translate a sensor result into their event's protocol; they never
turn a checker error into a pass.
"""
