# Version 3 results: written-down rules, unwritten rules and the gate

Study `guidance-v3-2026-11-20`, protocol [`protocol-v3.md`](protocol-v3.md). Written by `tools/summarize_v3.py` from 72 retained records (`runs/guidance-v3-2026-11-20/`); 72 sessions were planned.

Descriptive counts only. Rates are `k/n` with exact one-sided 95% bounds in brackets (an upper bound for a zero count; lower and upper otherwise). Session-level counts are primary; turns within a session are not independent.

## Headline: guidance level × gate

Pooled over both scenarios and both agent configurations.

| Guidance, arm | Sessions with a slip | Turn slips | Caught by the gate | Repaired in the turn | Final snapshot violates the rule | All four steps accepted |
| --- | --- | --- | --- | --- | --- | --- |
| Rule stated, no gate | 0/12 (upper 95% bound 22%) | 0/48 | n/a | n/a | 0/12 (upper 95% bound 22%) | 12/12 |
| Rule stated, gate | 0/12 (upper 95% bound 22%) | 0/48 | 0/0 | 0/0 | 0/12 (upper 95% bound 22%) | 12/12 |
| One-line hint, no gate | 0/12 (upper 95% bound 22%) | 0/48 | n/a | n/a | 0/12 (upper 95% bound 22%) | 12/12 |
| One-line hint, gate | 0/12 (upper 95% bound 22%) | 0/48 | 0/0 | 0/0 | 0/12 (upper 95% bound 22%) | 12/12 |
| Rule unstated, no gate | 9/12 (95% bounds 47% to 93%) | 14/48 | n/a | n/a | 9/12 (95% bounds 47% to 93%) | 12/12 |
| Rule unstated, gate | 10/12 (95% bounds 56% to 97%) | 10/48 | 10/10 | 10/10 | 0/12 (upper 95% bound 22%) | 12/12 |

## By agent configuration

| Guidance, arm, agent | Sessions with a slip | Turn slips | Caught by the gate | Repaired in the turn | Final snapshot violates the rule | All four steps accepted |
| --- | --- | --- | --- | --- | --- | --- |
| Rule stated, no gate, Sonnet 5.5 | 0/6 (upper 95% bound 39%) | 0/24 | n/a | n/a | 0/6 (upper 95% bound 39%) | 6/6 |
| Rule stated, no gate, Haiku 5.5 | 0/6 (upper 95% bound 39%) | 0/24 | n/a | n/a | 0/6 (upper 95% bound 39%) | 6/6 |
| Rule stated, gate, Sonnet 5.5 | 0/6 (upper 95% bound 39%) | 0/24 | 0/0 | 0/0 | 0/6 (upper 95% bound 39%) | 6/6 |
| Rule stated, gate, Haiku 5.5 | 0/6 (upper 95% bound 39%) | 0/24 | 0/0 | 0/0 | 0/6 (upper 95% bound 39%) | 6/6 |
| One-line hint, no gate, Sonnet 5.5 | 0/6 (upper 95% bound 39%) | 0/24 | n/a | n/a | 0/6 (upper 95% bound 39%) | 6/6 |
| One-line hint, no gate, Haiku 5.5 | 0/6 (upper 95% bound 39%) | 0/24 | n/a | n/a | 0/6 (upper 95% bound 39%) | 6/6 |
| One-line hint, gate, Sonnet 5.5 | 0/6 (upper 95% bound 39%) | 0/24 | 0/0 | 0/0 | 0/6 (upper 95% bound 39%) | 6/6 |
| One-line hint, gate, Haiku 5.5 | 0/6 (upper 95% bound 39%) | 0/24 | 0/0 | 0/0 | 0/6 (upper 95% bound 39%) | 6/6 |
| Rule unstated, no gate, Sonnet 5.5 | 6/6 (95% bounds 61% to 100%) | 9/24 | n/a | n/a | 6/6 (95% bounds 61% to 100%) | 6/6 |
| Rule unstated, no gate, Haiku 5.5 | 3/6 (95% bounds 15% to 85%) | 5/24 | n/a | n/a | 3/6 (95% bounds 15% to 85%) | 6/6 |
| Rule unstated, gate, Sonnet 5.5 | 6/6 (95% bounds 61% to 100%) | 6/24 | 6/6 | 6/6 | 0/6 (upper 95% bound 39%) | 6/6 |
| Rule unstated, gate, Haiku 5.5 | 4/6 (95% bounds 27% to 94%) | 4/24 | 4/4 | 4/4 | 0/6 (upper 95% bound 39%) | 6/6 |

## By scenario

| Guidance, arm, scenario | Sessions with a slip | Turn slips | Caught by the gate | Repaired in the turn | Final snapshot violates the rule | All four steps accepted |
| --- | --- | --- | --- | --- | --- | --- |
| Rule stated, no gate, S1-customer-insights | 0/6 (upper 95% bound 39%) | 0/24 | n/a | n/a | 0/6 (upper 95% bound 39%) |  |
| Rule stated, no gate, S2-fulfilment | 0/6 (upper 95% bound 39%) | 0/24 | n/a | n/a | 0/6 (upper 95% bound 39%) |  |
| Rule stated, gate, S1-customer-insights | 0/6 (upper 95% bound 39%) | 0/24 | 0/0 | 0/0 | 0/6 (upper 95% bound 39%) |  |
| Rule stated, gate, S2-fulfilment | 0/6 (upper 95% bound 39%) | 0/24 | 0/0 | 0/0 | 0/6 (upper 95% bound 39%) |  |
| One-line hint, no gate, S1-customer-insights | 0/6 (upper 95% bound 39%) | 0/24 | n/a | n/a | 0/6 (upper 95% bound 39%) |  |
| One-line hint, no gate, S2-fulfilment | 0/6 (upper 95% bound 39%) | 0/24 | n/a | n/a | 0/6 (upper 95% bound 39%) |  |
| One-line hint, gate, S1-customer-insights | 0/6 (upper 95% bound 39%) | 0/24 | 0/0 | 0/0 | 0/6 (upper 95% bound 39%) |  |
| One-line hint, gate, S2-fulfilment | 0/6 (upper 95% bound 39%) | 0/24 | 0/0 | 0/0 | 0/6 (upper 95% bound 39%) |  |
| Rule unstated, no gate, S1-customer-insights | 5/6 (95% bounds 42% to 99%) | 5/24 | n/a | n/a | 5/6 (95% bounds 42% to 99%) |  |
| Rule unstated, no gate, S2-fulfilment | 4/6 (95% bounds 27% to 94%) | 9/24 | n/a | n/a | 4/6 (95% bounds 27% to 94%) |  |
| Rule unstated, gate, S1-customer-insights | 5/6 (95% bounds 42% to 99%) | 5/24 | 5/5 | 5/5 | 0/6 (upper 95% bound 39%) |  |
| Rule unstated, gate, S2-fulfilment | 5/6 (95% bounds 42% to 99%) | 5/24 | 5/5 | 5/5 | 0/6 (upper 95% bound 39%) |  |

## Time, spend and repair effort

Session wall time and CLI-reported agent cost (API-equivalent, notional under a subscription login).

| Guidance, arm, agent | Sessions | Median session time | Total agent cost | Repair requests | Turns ending with a carried-over violation |
| --- | --- | --- | --- | --- | --- |
| Rule stated, no gate, Sonnet 5.5 | 6 | 85 s | US$1.64 | n/a | 0 |
| Rule stated, no gate, Haiku 5.5 | 6 | 86 s | US$0.13 | n/a | 0 |
| Rule stated, gate, Sonnet 5.5 | 6 | 92 s | US$1.73 | 0 | 0 |
| Rule stated, gate, Haiku 5.5 | 6 | 81 s | US$0.13 | 0 | 0 |
| One-line hint, no gate, Sonnet 5.5 | 6 | 90 s | US$1.73 | n/a | 0 |
| One-line hint, no gate, Haiku 5.5 | 6 | 76 s | US$0.12 | n/a | 0 |
| One-line hint, gate, Sonnet 5.5 | 6 | 91 s | US$1.81 | 0 | 0 |
| One-line hint, gate, Haiku 5.5 | 6 | 76 s | US$0.12 | 0 | 0 |
| Rule unstated, no gate, Sonnet 5.5 | 6 | 86 s | US$1.57 | n/a | 12 |
| Rule unstated, no gate, Haiku 5.5 | 6 | 75 s | US$0.12 | n/a | 5 |
| Rule unstated, gate, Sonnet 5.5 | 6 | 113 s | US$2.05 | 6 | 0 |
| Rule unstated, gate, Haiku 5.5 | 6 | 82 s | US$0.13 | 4 | 0 |

## Every slip

| Session | Step | New forbidden imports | Caught | Repaired | Repair requests | Final snapshot |
| --- | --- | --- | --- | --- | --- | --- |
| `unstated-S1-customer-insights__A__haiku__r1` | 3 | `controllers.customer_insights` → `infrastructure.customers` | n/a | n/a | n/a | violation |
| `unstated-S1-customer-insights__A__haiku__r2` | 3 | `controllers.customer_insights` → `infrastructure.customers` | n/a | n/a | n/a | violation |
| `unstated-S1-customer-insights__A__sonnet__r1` | 3 | `controllers.customer_insights` → `infrastructure.customers` | n/a | n/a | n/a | violation |
| `unstated-S1-customer-insights__A__sonnet__r2` | 3 | `controllers.customer_insights` → `infrastructure.customers` | n/a | n/a | n/a | violation |
| `unstated-S1-customer-insights__A__sonnet__r3` | 3 | `controllers.customer_insights` → `infrastructure.customers` | n/a | n/a | n/a | violation |
| `unstated-S1-customer-insights__B__haiku__r2` | 3 | `controllers.customer_insights` → `infrastructure.customers` | yes | yes | 1 | pass |
| `unstated-S1-customer-insights__B__haiku__r3` | 3 | `controllers.customer_insights` → `infrastructure.customers` | yes | yes | 1 | pass |
| `unstated-S1-customer-insights__B__sonnet__r1` | 3 | `controllers.customer_insights` → `infrastructure.customers` | yes | yes | 1 | pass |
| `unstated-S1-customer-insights__B__sonnet__r2` | 3 | `controllers.customer_insights` → `infrastructure.customers` | yes | yes | 1 | pass |
| `unstated-S1-customer-insights__B__sonnet__r3` | 3 | `controllers.customer_insights` → `infrastructure.customers` | yes | yes | 1 | pass |
| `unstated-S2-fulfilment__A__haiku__r1` | 1 | `controllers.fulfilment` → `infrastructure.catalog`, `controllers.fulfilment` → `infrastructure.customers` | n/a | n/a | n/a | violation |
| `unstated-S2-fulfilment__A__haiku__r1` | 2 | `controllers.fulfilment` → `infrastructure.stock` | n/a | n/a | n/a | violation |
| `unstated-S2-fulfilment__A__haiku__r1` | 4 | `controllers.fulfilment` → `infrastructure.repository` | n/a | n/a | n/a | violation |
| `unstated-S2-fulfilment__A__sonnet__r1` | 1 | `controllers.fulfilment` → `infrastructure.catalog`, `controllers.fulfilment` → `infrastructure.customers`, `controllers.fulfilment` → `infrastructure.repository` | n/a | n/a | n/a | violation |
| `unstated-S2-fulfilment__A__sonnet__r1` | 2 | `controllers.fulfilment` → `infrastructure.stock` | n/a | n/a | n/a | violation |
| `unstated-S2-fulfilment__A__sonnet__r2` | 1 | `controllers.fulfilment` → `infrastructure.catalog`, `controllers.fulfilment` → `infrastructure.customers`, `controllers.fulfilment` → `infrastructure.repository` | n/a | n/a | n/a | violation |
| `unstated-S2-fulfilment__A__sonnet__r2` | 2 | `controllers.fulfilment` → `infrastructure.stock` | n/a | n/a | n/a | violation |
| `unstated-S2-fulfilment__A__sonnet__r3` | 1 | `controllers.fulfilment` → `infrastructure.catalog`, `controllers.fulfilment` → `infrastructure.customers`, `controllers.fulfilment` → `infrastructure.repository` | n/a | n/a | n/a | violation |
| `unstated-S2-fulfilment__A__sonnet__r3` | 2 | `controllers.fulfilment` → `infrastructure.stock` | n/a | n/a | n/a | violation |
| `unstated-S2-fulfilment__B__haiku__r2` | 1 | `controllers.fulfilment` → `infrastructure.catalog`, `controllers.fulfilment` → `infrastructure.customers`, `controllers.fulfilment` → `infrastructure.repository` | yes | yes | 1 | pass |
| `unstated-S2-fulfilment__B__haiku__r3` | 1 | `controllers.fulfilment` → `infrastructure.catalog`, `controllers.fulfilment` → `infrastructure.customers` | yes | yes | 1 | pass |
| `unstated-S2-fulfilment__B__sonnet__r1` | 1 | `controllers.fulfilment` → `infrastructure.catalog`, `controllers.fulfilment` → `infrastructure.customers`, `controllers.fulfilment` → `infrastructure.repository` | yes | yes | 1 | pass |
| `unstated-S2-fulfilment__B__sonnet__r2` | 1 | `controllers.fulfilment` → `infrastructure.catalog`, `controllers.fulfilment` → `infrastructure.customers`, `controllers.fulfilment` → `infrastructure.repository` | yes | yes | 1 | pass |
| `unstated-S2-fulfilment__B__sonnet__r3` | 1 | `controllers.fulfilment` → `infrastructure.catalog`, `controllers.fulfilment` → `infrastructure.customers`, `controllers.fulfilment` → `infrastructure.repository` | yes | yes | 1 | pass |

## Completeness and integrity

- Terminations: completed 72.
- Planned sessions without a record: 0.
- Sessions with tampering detected: 0. Sessions that modified the legacy reports controller: 0.
- Reported spend: agent US$11.27, evaluation judge US$0.16.
- Environment: Claude Code 2.1.322 (Claude Code).
