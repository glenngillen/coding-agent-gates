# Adjudication rubric for semantic findings

This rubric tells a person how to label a final snapshot against the semantic
rule `business-decision-in-controller`. It exists so that judge outputs can be
checked against independent labels if anyone supplies them later.

**Status on 2026-11-19:** no independent human labels will be supplied for the
pilot's final runs (Decisions, 2026-11-19 in
`specs/coding-agent-backpressure.md`). The pilot therefore reports the judge's
outputs, abstentions and disagreements only. False-positive and false-negative
rates for final runs are marked unavailable. The calibration labels in
`calibration/semantic-calibration.json` were written by the example's author
from this rubric before any judge output was seen. They are authored labels,
not independent ones.

## What is being labelled

One final snapshot's controller modules (`src/orders/controllers/*.py`), the
same narrow context the judge receives. Label the code as it is, not the
agent's intent or its summary.

## The rule

The rule is the one in `semantic/rubric.md`, between the
`judge-instructions` markers:

- **Violation.** A controller decides business policy about pricing:
  whether an order is eligible for a discount, a discount amount or rate, or a
  total that depends on one. A hard-coded pricing threshold or percentage used
  for such a decision is a violation even if the result matches the
  application layer's answer.
- **Pass.** The controller validates request fields (presence, types, ranges
  of request parameters), calls application-service methods, catches their
  exceptions, chooses status codes and maps returned values into responses.
  Mentioning discounts in names, docstrings or keys is not a decision.
- **Outside this rule.** The task instruction (`instruction.md`) also asks for
  status-change rules and business limits to live in the application layer.
  The judge's rubric does not cover them, so a person labelling against this
  rubric marks such code `pass` for this rule and records it as a separate
  note (`other_business_logic_in_controller: true`). Do not stretch the rule to
  cover it.
- **Unsure.** Use `unsure` when the code could reasonably be read either way
  (for example, a threshold whose purpose is not evident from the controller
  alone). Do not resolve doubt by reading other layers; the judge cannot see
  them either.

## Procedure

1. **Hide the arm.** Give the adjudicator snapshots by an opaque id (the
   collector's `blind_id`), never the run id, arm, task order, repair count or
   transcript. Where possible, one adjudicator labels all snapshots from all
   arms in a shuffled order.
2. **Hide the judge.** Label before seeing the judge's verdict.
3. **Cite evidence.** For a violation, record the file and line range of the
   decision and one sentence explaining which pricing decision it makes.
4. **Record the label** as `{"blind_id", "label": "pass" | "violation" |
   "unsure", "evidence": [...], "other_business_logic_in_controller": bool,
   "adjudicator", "labelled_at"}` in a separate labels file. Do not edit run
   records.
5. **Disagreements.** If two people label the same snapshot differently, keep
   both labels. A third person may break the tie; record that too.

## How labels would be used

Only labels produced by this procedure, by someone other than the author of
the calibration set, count as independent. With them, the analysis
(`analysis.md`) computes:

- false-positive rate: judge `violation` on snapshots labelled `pass`, divided
  by the snapshots labelled `pass` that the judge answered;
- false-negative rate: judge `pass` on snapshots labelled `violation`, divided
  by the snapshots labelled `violation` that the judge answered;
- judge abstentions and `unsure` labels as separate counts, never folded into
  either rate.

A judge's own verdict is never used as the label for that judge.

## Open questions

- Should a person label the pilot's final snapshots after all?
  - evidence: Decisions, 2026-11-19: no independent human labels will be supplied; the pilot reports judge outputs and abstentions only.
  - options: Leave final-run error rates unavailable (current); have someone other than the calibration author follow this procedure and add a labels file, then rerun the summary.
  - location: adjudication.md / Status
