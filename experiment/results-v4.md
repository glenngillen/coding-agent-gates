# Version 4 results: a lean prompt with a gate, or a large handbook?

Study `handbook-v4-2026-11-20`, protocol [`protocol-v4.md`](protocol-v4.md). Written by `tools/summarize_v4.py` from 48 retained records (`runs/handbook-v4-2026-11-20/`); 48 sessions were planned.

Descriptive counts only. Costs are CLI-reported, API-equivalent and notional under a subscription login. Rates are `k/n` with exact one-sided 95% bounds. Judge verdicts are model outputs, not human labels.

## Primary outcome: cost, time and the judge's verdict on the final controllers

| Guidance, arm, agent | Sessions | Mean agent cost per session | Total agent cost | Median session time | Judge: violation / pass / not evaluated |
| --- | --- | --- | --- | --- | --- |
| Lean prompt, no gate, Sonnet 5.5 | 6 | US$0.297 | US$1.78 | 95 s | 1 / 5 / 0 |
| Lean prompt, no gate, Haiku 5.5 | 6 | US$0.022 | US$0.13 | 84 s | 2 / 4 / 0 |
| Lean prompt, gate, Sonnet 5.5 | 6 | US$0.304 | US$1.82 | 100 s | 0 / 6 / 0 |
| Lean prompt, gate, Haiku 5.5 | 6 | US$0.021 | US$0.13 | 85 s | 2 / 4 / 0 |
| Large handbook, no gate, Sonnet 5.5 | 6 | US$0.633 | US$3.80 | 105 s | 0 / 6 / 0 |
| Large handbook, no gate, Haiku 5.5 | 6 | US$0.067 | US$0.40 | 94 s | 0 / 6 / 0 |
| Large handbook, gate, Sonnet 5.5 | 6 | US$0.632 | US$3.79 | 105 s | 0 / 6 / 0 |
| Large handbook, gate, Haiku 5.5 | 6 | US$0.069 | US$0.42 | 103 s | 0 / 6 / 0 |

## Headline: guidance level × gate

Pooled over both scenarios and both agent configurations.

| Guidance, arm | Sessions with a slip | Turn slips | Caught by the gate | Repaired in the turn | Final snapshot violates the rule | All four steps accepted |
| --- | --- | --- | --- | --- | --- | --- |
| Lean prompt, no gate | 0/12 (upper 95% bound 22%) | 0/48 | n/a | n/a | 0/12 (upper 95% bound 22%) | 12/12 |
| Lean prompt, gate | 0/12 (upper 95% bound 22%) | 0/48 | 0/0 | 0/0 | 0/12 (upper 95% bound 22%) | 12/12 |
| Large handbook, no gate | 0/12 (upper 95% bound 22%) | 0/48 | n/a | n/a | 0/12 (upper 95% bound 22%) | 12/12 |
| Large handbook, gate | 0/12 (upper 95% bound 22%) | 0/48 | 0/0 | 0/0 | 0/12 (upper 95% bound 22%) | 12/12 |

## By agent configuration

| Guidance, arm, agent | Sessions with a slip | Turn slips | Caught by the gate | Repaired in the turn | Final snapshot violates the rule | All four steps accepted |
| --- | --- | --- | --- | --- | --- | --- |
| Lean prompt, no gate, Sonnet 5.5 | 0/6 (upper 95% bound 39%) | 0/24 | n/a | n/a | 0/6 (upper 95% bound 39%) | 6/6 |
| Lean prompt, no gate, Haiku 5.5 | 0/6 (upper 95% bound 39%) | 0/24 | n/a | n/a | 0/6 (upper 95% bound 39%) | 6/6 |
| Lean prompt, gate, Sonnet 5.5 | 0/6 (upper 95% bound 39%) | 0/24 | 0/0 | 0/0 | 0/6 (upper 95% bound 39%) | 6/6 |
| Lean prompt, gate, Haiku 5.5 | 0/6 (upper 95% bound 39%) | 0/24 | 0/0 | 0/0 | 0/6 (upper 95% bound 39%) | 6/6 |
| Large handbook, no gate, Sonnet 5.5 | 0/6 (upper 95% bound 39%) | 0/24 | n/a | n/a | 0/6 (upper 95% bound 39%) | 6/6 |
| Large handbook, no gate, Haiku 5.5 | 0/6 (upper 95% bound 39%) | 0/24 | n/a | n/a | 0/6 (upper 95% bound 39%) | 6/6 |
| Large handbook, gate, Sonnet 5.5 | 0/6 (upper 95% bound 39%) | 0/24 | 0/0 | 0/0 | 0/6 (upper 95% bound 39%) | 6/6 |
| Large handbook, gate, Haiku 5.5 | 0/6 (upper 95% bound 39%) | 0/24 | 0/0 | 0/0 | 0/6 (upper 95% bound 39%) | 6/6 |

## By scenario

| Guidance, arm, scenario | Sessions with a slip | Turn slips | Caught by the gate | Repaired in the turn | Final snapshot violates the rule | All four steps accepted |
| --- | --- | --- | --- | --- | --- | --- |
| Lean prompt, no gate, S1-customer-insights | 0/6 (upper 95% bound 39%) | 0/24 | n/a | n/a | 0/6 (upper 95% bound 39%) |  |
| Lean prompt, no gate, S2-fulfilment | 0/6 (upper 95% bound 39%) | 0/24 | n/a | n/a | 0/6 (upper 95% bound 39%) |  |
| Lean prompt, gate, S1-customer-insights | 0/6 (upper 95% bound 39%) | 0/24 | 0/0 | 0/0 | 0/6 (upper 95% bound 39%) |  |
| Lean prompt, gate, S2-fulfilment | 0/6 (upper 95% bound 39%) | 0/24 | 0/0 | 0/0 | 0/6 (upper 95% bound 39%) |  |
| Large handbook, no gate, S1-customer-insights | 0/6 (upper 95% bound 39%) | 0/24 | n/a | n/a | 0/6 (upper 95% bound 39%) |  |
| Large handbook, no gate, S2-fulfilment | 0/6 (upper 95% bound 39%) | 0/24 | n/a | n/a | 0/6 (upper 95% bound 39%) |  |
| Large handbook, gate, S1-customer-insights | 0/6 (upper 95% bound 39%) | 0/24 | 0/0 | 0/0 | 0/6 (upper 95% bound 39%) |  |
| Large handbook, gate, S2-fulfilment | 0/6 (upper 95% bound 39%) | 0/24 | 0/0 | 0/0 | 0/6 (upper 95% bound 39%) |  |

## Time, spend and repair effort

Session wall time and CLI-reported agent cost (API-equivalent, notional under a subscription login).

| Guidance, arm, agent | Sessions | Median session time | Total agent cost | Repair requests | Turns ending with a carried-over violation |
| --- | --- | --- | --- | --- | --- |
| Lean prompt, no gate, Sonnet 5.5 | 6 | 95 s | US$1.78 | n/a | 0 |
| Lean prompt, no gate, Haiku 5.5 | 6 | 84 s | US$0.13 | n/a | 0 |
| Lean prompt, gate, Sonnet 5.5 | 6 | 100 s | US$1.82 | 0 | 0 |
| Lean prompt, gate, Haiku 5.5 | 6 | 85 s | US$0.13 | 0 | 0 |
| Large handbook, no gate, Sonnet 5.5 | 6 | 105 s | US$3.80 | n/a | 0 |
| Large handbook, no gate, Haiku 5.5 | 6 | 94 s | US$0.40 | n/a | 0 |
| Large handbook, gate, Sonnet 5.5 | 6 | 105 s | US$3.79 | 0 | 0 |
| Large handbook, gate, Haiku 5.5 | 6 | 103 s | US$0.42 | 0 | 0 |

## Every slip

None.

## Completeness and integrity

- Terminations: completed 48.
- Planned sessions without a record: 0.
- Sessions with tampering detected: 0. Sessions that modified the legacy reports controller: 0.
- Reported spend: agent US$12.27, evaluation judge US$0.12.
- Environment: Claude Code 2.1.322 (Claude Code).
