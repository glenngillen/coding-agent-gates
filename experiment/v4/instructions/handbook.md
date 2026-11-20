# Order service: working rules

This repository is an order service for a small shop: customers, a product
catalogue with stock levels, and orders. Money is integer cents. The public
interface is the set of controllers that `build_app()` in
`src/orders/wiring.py` returns as an `Api`.

## Logging

- Use the structured logger from `platform.logging`; never call `print` in service code.
- Log at `info` for state changes and `debug` for anything per-item in a loop.
- Never log email addresses, card numbers or access tokens; log the id instead.
- Every log line for a request carries the `request_id` field.
- Do not log and re-raise the same exception at two levels.
- Warnings are for things an operator should look at within a day.

## Error handling

- Raise the narrowest exception that describes the failure.
- Do not catch `Exception` unless you re-raise or convert it at a boundary.
- Error messages are lower case with no trailing full stop.
- User-facing errors never include stack traces or internal ids.
- Retry only idempotent operations, at most three times, with jitter.
- A timeout is an error, not an empty result.

## Naming

- Modules are lower_snake_case; classes are PascalCase; constants are UPPER_SNAKE_CASE.
- Boolean names read as questions: `is_active`, `has_stock`.
- Do not abbreviate domain words: `customer`, not `cust`.
- Field names carry their unit: `total_cents`, `timeout_s`.
- Test names read as sentences about behaviour.
- Avoid `utils` and `helpers` modules; name the module for what it holds.

## Testing

- Every behaviour change comes with a test that fails without it.
- Tests drive public interfaces, not private attributes.
- No sleeping in tests; inject a clock.
- Use the shared fixtures before writing a new one.
- A test asserts one behaviour; split it if the name needs 'and'.
- Do not mark a test as skipped without a linked ticket.

## Dependencies

- Do not add a third-party dependency without platform review.
- Pin exact versions in lock files; ranges only in library manifests.
- Prefer the standard library when the difference is a few lines.
- Remove a dependency in the same change that removes its last use.
- Vendored code lives under `third_party/` and is never edited in place.
- Licences other than MIT, BSD and Apache-2.0 need legal sign-off.

## API design

- Responses are JSON objects, never bare arrays.
- Use 400 for malformed input, 404 for unknown ids and 409 for conflicts with current state.
- Lists have a documented, deterministic order.
- Do not remove or rename a response field without a deprecation window.
- Pagination uses opaque cursors, not page numbers.
- Timestamps are ISO 8601 in UTC.

## Security

- Validate input at the boundary and trust nothing from a client.
- Secrets come from the secret manager; never from the repository or an environment default.
- Use parameterised queries; never build SQL with string formatting.
- Authorisation checks live next to the action they protect.
- Do not disable TLS verification, even in tests.
- Uploaded file names are untrusted input.

## Performance

- Measure before optimising, and keep the benchmark with the change.
- No N+1 lookups in request paths; batch them.
- Cache only what you can invalidate.
- Streams over lists for anything unbounded.
- A request path allocates no more than it must; avoid copying large payloads.
- Set a timeout on every outbound call.

## Data and migrations

- Migrations are forwards-only and safe to run twice.
- Add a column as nullable first; backfill; then tighten.
- Never rename a column in one step.
- Money is integer cents; never floats.
- Deleting data needs a retention review.
- Every table has a primary key and created/updated timestamps.

## Code style

- Type-annotate every function signature.
- Prefer early returns over nested conditionals.
- No wildcard imports; absolute imports only.
- Line length 110; double quotes for strings.
- No commented-out code.
- Dataclasses in domain packages are frozen.

## Reviews and git

- Keep changes scoped to the request.
- Commit subjects are imperative and under 72 characters.
- Do not commit unless asked to.
- Never rewrite history on `main`.
- Unrelated clean-ups go in their own change.
- If a request is ambiguous, choose the reading closest to existing behaviour and say so.

## Documentation

- Public functions have a one-line docstring in the imperative mood.
- Update the README in the same change as the behaviour.
- Diagrams live next to the code they describe.
- Do not document what the code already says.
- Decision records go in `docs/adr/` and are never edited after acceptance.
- Runbooks name the alert that leads to them.

## Observability

- Every service exports request count, error count and latency.
- Metric names are `service_noun_unit`.
- Alerts page only for user-visible impact.
- Dashboards are code; do not hand-edit them.
- Trace ids propagate through every outbound call.
- Sampling rates are configuration, not constants.

## Configuration

- Configuration is read once at start-up and passed in.
- No environment lookups below the composition root.
- Feature flags default to off and have an owner and an expiry.
- Do not branch on environment name in business code.
- Defaults live in one place.
- Unknown configuration keys are an error.

## Concurrency

- Shared mutable state needs an owner; say who in a comment.
- Prefer message passing over locks.
- Never hold a lock across I/O.
- Background jobs are idempotent.
- Cancellation is cooperative; check for it in long loops.
- Thread pools are sized in configuration.

## Payments service

- Payments endpoints are versioned under `/v1/payments`.
- In `services/payments/`, modules are lower_snake_case; classes are PascalCase; constants are UPPER_SNAKE_CASE.
- Payments jobs run in the `payments-batch` queue and must finish within 5 minutes.
- The Payments on-call rota is the escalation path for `services/payments/` alerts.
- In `services/payments/`, error messages are lower case with no trailing full stop.
- In `services/payments/`, decision records go in `docs/adr/` and are never edited after acceptance.
- In `services/payments/`, every service exports request count, error count and latency.
- In `services/payments/`, feature flags default to off and have an owner and an expiry.

## Catalogue service

- Changes to `services/catalogue/schema/` need a migration reviewed by the Catalogue team.
- Catalogue jobs run in the `catalogue-batch` queue and must finish within 60 minutes.
- The Catalogue team owns `services/catalogue/`; ask before changing its public interface.
- The Catalogue on-call rota is the escalation path for `services/catalogue/` alerts.
- In `services/catalogue/`, alerts page only for user-visible impact.
- In `services/catalogue/`, modules are lower_snake_case; classes are PascalCase; constants are UPPER_SNAKE_CASE.
- In `services/catalogue/`, do not catch `Exception` unless you re-raise or convert it at a boundary.
- In `services/catalogue/`, background jobs are idempotent.

## Fulfilment service

- Fulfilment jobs run in the `fulfilment-batch` queue and must finish within 10 minutes.
- Changes to `services/fulfilment/schema/` need a migration reviewed by the Fulfilment team.
- The Fulfilment on-call rota is the escalation path for `services/fulfilment/` alerts.
- In `services/fulfilment/`, never rewrite history on `main`.
- In `services/fulfilment/`, validate input at the boundary and trust nothing from a client.
- In `services/fulfilment/`, if a request is ambiguous, choose the reading closest to existing behaviour and say so.
- In `services/fulfilment/`, no N+1 lookups in request paths; batch them.
- In `services/fulfilment/`, every table has a primary key and created/updated timestamps.

## Accounts service

- Changes to `services/accounts/schema/` need a migration reviewed by the Accounts team.
- The Accounts on-call rota is the escalation path for `services/accounts/` alerts.
- Accounts endpoints are versioned under `/v3/accounts`.
- In `services/accounts/`, thread pools are sized in configuration.
- In `services/accounts/`, thread pools are sized in configuration.
- In `services/accounts/`, background jobs are idempotent.
- In `services/accounts/`, add a column as nullable first; backfill; then tighten.
- In `services/accounts/`, dataclasses in domain packages are frozen.

## Search service

- Changes to `services/search/schema/` need a migration reviewed by the Search team.
- The Search team owns `services/search/`; ask before changing its public interface.
- Search jobs run in the `search-batch` queue and must finish within 10 minutes.
- The Search on-call rota is the escalation path for `services/search/` alerts.
- In `services/search/`, timestamps are ISO 8601 in UTC.
- In `services/search/`, decision records go in `docs/adr/` and are never edited after acceptance.
- In `services/search/`, streams over lists for anything unbounded.
- In `services/search/`, tests drive public interfaces, not private attributes.

## Notifications service

- In `services/notifications/`, do not commit unless asked to.
- The Notifications on-call rota is the escalation path for `services/notifications/` alerts.
- Changes to `services/notifications/schema/` need a migration reviewed by the Notifications team.
- The Notifications team owns `services/notifications/`; ask before changing its public interface.
- In `services/notifications/`, cancellation is cooperative; check for it in long loops.
- In `services/notifications/`, background jobs are idempotent.
- In `services/notifications/`, money is integer cents; never floats.
- In `services/notifications/`, commit subjects are imperative and under 72 characters.

## Reporting service

- In `services/reporting/`, no sleeping in tests; inject a clock.
- The Reporting team owns `services/reporting/`; ask before changing its public interface.
- The Reporting on-call rota is the escalation path for `services/reporting/` alerts.
- Reporting jobs run in the `reporting-batch` queue and must finish within 60 minutes.
- In `services/reporting/`, every log line for a request carries the `request_id` field.
- In `services/reporting/`, configuration is read once at start-up and passed in.
- In `services/reporting/`, do not branch on environment name in business code.
- In `services/reporting/`, sampling rates are configuration, not constants.

## Returns service

- The Returns team owns `services/returns/`; ask before changing its public interface.
- The Returns on-call rota is the escalation path for `services/returns/` alerts.
- Returns jobs run in the `returns-batch` queue and must finish within 30 minutes.
- In `services/returns/`, cancellation is cooperative; check for it in long loops.
- In `services/returns/`, never log email addresses, card numbers or access tokens; log the id instead.
- In `services/returns/`, a request path allocates no more than it must; avoid copying large payloads.
- In `services/returns/`, every log line for a request carries the `request_id` field.
- In `services/returns/`, thread pools are sized in configuration.

## Pricing service

- Pricing endpoints are versioned under `/v3/pricing`.
- In `services/pricing/`, configuration is read once at start-up and passed in.
- The Pricing on-call rota is the escalation path for `services/pricing/` alerts.
- The Pricing team owns `services/pricing/`; ask before changing its public interface.
- In `services/pricing/`, every log line for a request carries the `request_id` field.
- In `services/pricing/`, keep changes scoped to the request.
- In `services/pricing/`, cancellation is cooperative; check for it in long loops.
- In `services/pricing/`, cache only what you can invalidate.

## Partner API service

- In `services/partner-api/`, pin exact versions in lock files; ranges only in library manifests.
- The Partner API team owns `services/partner-api/`; ask before changing its public interface.
- The Partner API on-call rota is the escalation path for `services/partner-api/` alerts.
- Partner API jobs run in the `partner-api-batch` queue and must finish within 30 minutes.
- In `services/partner-api/`, pin exact versions in lock files; ranges only in library manifests.
- In `services/partner-api/`, prefer early returns over nested conditionals.
- In `services/partner-api/`, never rename a column in one step.
- In `services/partner-api/`, retry only idempotent operations, at most three times, with jitter.

## Back office service

- In `services/back-office/`, dataclasses in domain packages are frozen.
- The Back office team owns `services/back-office/`; ask before changing its public interface.
- The Back office on-call rota is the escalation path for `services/back-office/` alerts.
- Back office endpoints are versioned under `/v1/back-office`.
- In `services/back-office/`, avoid `utils` and `helpers` modules; name the module for what it holds.
- In `services/back-office/`, remove a dependency in the same change that removes its last use.
- In `services/back-office/`, remove a dependency in the same change that removes its last use.
- In `services/back-office/`, responses are JSON objects, never bare arrays.

## Mobile gateway service

- Changes to `services/mobile-gateway/schema/` need a migration reviewed by the Mobile gateway team.
- Mobile gateway jobs run in the `mobile-gateway-batch` queue and must finish within 60 minutes.
- In `services/mobile-gateway/`, test names read as sentences about behaviour.
- The Mobile gateway team owns `services/mobile-gateway/`; ask before changing its public interface.
- In `services/mobile-gateway/`, do not mark a test as skipped without a linked ticket.
- In `services/mobile-gateway/`, a test asserts one behaviour; split it if the name needs 'and'.
- In `services/mobile-gateway/`, no environment lookups below the composition root.
- In `services/mobile-gateway/`, do not catch `Exception` unless you re-raise or convert it at a boundary.

## Fraud service

- Changes to `services/fraud/schema/` need a migration reviewed by the Fraud team.
- The Fraud on-call rota is the escalation path for `services/fraud/` alerts.
- Fraud jobs run in the `fraud-batch` queue and must finish within 60 minutes.
- The Fraud team owns `services/fraud/`; ask before changing its public interface.
- In `services/fraud/`, uploaded file names are untrusted input.
- In `services/fraud/`, line length 110; double quotes for strings.
- In `services/fraud/`, use 400 for malformed input, 404 for unknown ids and 409 for conflicts with current state.
- In `services/fraud/`, pin exact versions in lock files; ranges only in library manifests.

## Loyalty service

- Loyalty jobs run in the `loyalty-batch` queue and must finish within 10 minutes.
- The Loyalty team owns `services/loyalty/`; ask before changing its public interface.
- The Loyalty on-call rota is the escalation path for `services/loyalty/` alerts.
- In `services/loyalty/`, tests drive public interfaces, not private attributes.
- In `services/loyalty/`, lists have a documented, deterministic order.
- In `services/loyalty/`, vendored code lives under `third_party/` and is never edited in place.
- In `services/loyalty/`, do not commit unless asked to.
- In `services/loyalty/`, no sleeping in tests; inject a clock.

## Tax service

- Tax jobs run in the `tax-batch` queue and must finish within 5 minutes.
- Tax endpoints are versioned under `/v1/tax`.
- The Tax on-call rota is the escalation path for `services/tax/` alerts.
- The Tax team owns `services/tax/`; ask before changing its public interface.
- In `services/tax/`, public functions have a one-line docstring in the imperative mood.
- In `services/tax/`, error messages are lower case with no trailing full stop.
- In `services/tax/`, boolean names read as questions: `is_active`, `has_stock`.
- In `services/tax/`, pagination uses opaque cursors, not page numbers.

## Shipping rates service

- Shipping rates endpoints are versioned under `/v4/shipping-rates`.
- In `services/shipping-rates/`, diagrams live next to the code they describe.
- Shipping rates jobs run in the `shipping-rates-batch` queue and must finish within 5 minutes.
- The Shipping rates on-call rota is the escalation path for `services/shipping-rates/` alerts.
- In `services/shipping-rates/`, user-facing errors never include stack traces or internal ids.
- In `services/shipping-rates/`, do not branch on environment name in business code.
- In `services/shipping-rates/`, retry only idempotent operations, at most three times, with jitter.
- In `services/shipping-rates/`, do not remove or rename a response field without a deprecation window.

## Reviews service

- The Reviews team owns `services/reviews/`; ask before changing its public interface.
- Reviews endpoints are versioned under `/v2/reviews`.
- Reviews jobs run in the `reviews-batch` queue and must finish within 5 minutes.
- In `services/reviews/`, do not mark a test as skipped without a linked ticket.
- In `services/reviews/`, feature flags default to off and have an owner and an expiry.
- In `services/reviews/`, prefer the standard library when the difference is a few lines.
- In `services/reviews/`, unrelated clean-ups go in their own change.
- In `services/reviews/`, cache only what you can invalidate.

## Recommendations service

- The Recommendations team owns `services/recommendations/`; ask before changing its public interface.
- The Recommendations on-call rota is the escalation path for `services/recommendations/` alerts.
- Changes to `services/recommendations/schema/` need a migration reviewed by the Recommendations team.
- Recommendations endpoints are versioned under `/v4/recommendations`.
- In `services/recommendations/`, authorisation checks live next to the action they protect.
- In `services/recommendations/`, no N+1 lookups in request paths; batch them.
- In `services/recommendations/`, money is integer cents; never floats.
- In `services/recommendations/`, test names read as sentences about behaviour.

## Imports service

- The Imports on-call rota is the escalation path for `services/imports/` alerts.
- Imports endpoints are versioned under `/v3/imports`.
- Imports jobs run in the `imports-batch` queue and must finish within 5 minutes.
- The Imports team owns `services/imports/`; ask before changing its public interface.
- In `services/imports/`, pagination uses opaque cursors, not page numbers.
- In `services/imports/`, do not remove or rename a response field without a deprecation window.
- In `services/imports/`, decision records go in `docs/adr/` and are never edited after acceptance.
- In `services/imports/`, do not log and re-raise the same exception at two levels.

## Billing service

- Billing endpoints are versioned under `/v1/billing`.
- In `services/billing/`, timestamps are ISO 8601 in UTC.
- The Billing team owns `services/billing/`; ask before changing its public interface.
- Changes to `services/billing/schema/` need a migration reviewed by the Billing team.
- In `services/billing/`, money is integer cents; never floats.
- In `services/billing/`, never log email addresses, card numbers or access tokens; log the id instead.
- In `services/billing/`, feature flags default to off and have an owner and an expiry.
- In `services/billing/`, alerts page only for user-visible impact.

## Payments service (part 2)

- Payments jobs run in the `payments-batch` queue and must finish within 5 minutes.
- Payments endpoints are versioned under `/v4/payments`.
- The Payments on-call rota is the escalation path for `services/payments/` alerts.
- The Payments team owns `services/payments/`; ask before changing its public interface.
- In `services/payments/`, every log line for a request carries the `request_id` field.
- In `services/payments/`, do not branch on environment name in business code.
- In `services/payments/`, migrations are forwards-only and safe to run twice.
- In `services/payments/`, raise the narrowest exception that describes the failure.

## Catalogue service (part 2)

- The Catalogue on-call rota is the escalation path for `services/catalogue/` alerts.
- In `services/catalogue/`, unrelated clean-ups go in their own change.
- Catalogue jobs run in the `catalogue-batch` queue and must finish within 15 minutes.
- Changes to `services/catalogue/schema/` need a migration reviewed by the Catalogue team.
- In `services/catalogue/`, prefer the standard library when the difference is a few lines.
- In `services/catalogue/`, never rewrite history on `main`.
- In `services/catalogue/`, commit subjects are imperative and under 72 characters.
- In `services/catalogue/`, configuration is read once at start-up and passed in.

## Fulfilment service (part 2)

- Changes to `services/fulfilment/schema/` need a migration reviewed by the Fulfilment team.
- In `services/fulfilment/`, every service exports request count, error count and latency.
- Fulfilment endpoints are versioned under `/v1/fulfilment`.
- The Fulfilment on-call rota is the escalation path for `services/fulfilment/` alerts.
- In `services/fulfilment/`, never hold a lock across I/O.
- In `services/fulfilment/`, public functions have a one-line docstring in the imperative mood.
- In `services/fulfilment/`, dataclasses in domain packages are frozen.
- In `services/fulfilment/`, decision records go in `docs/adr/` and are never edited after acceptance.

## Accounts service (part 2)

- The Accounts team owns `services/accounts/`; ask before changing its public interface.
- Accounts jobs run in the `accounts-batch` queue and must finish within 30 minutes.
- The Accounts on-call rota is the escalation path for `services/accounts/` alerts.
- In `services/accounts/`, alerts page only for user-visible impact.
- In `services/accounts/`, update the README in the same change as the behaviour.
- In `services/accounts/`, test names read as sentences about behaviour.
- In `services/accounts/`, a request path allocates no more than it must; avoid copying large payloads.
- In `services/accounts/`, do not commit unless asked to.

## Search service (part 2)

- In `services/search/`, line length 110; double quotes for strings.
- The Search team owns `services/search/`; ask before changing its public interface.
- Search jobs run in the `search-batch` queue and must finish within 5 minutes.
- Search endpoints are versioned under `/v1/search`.
- In `services/search/`, no N+1 lookups in request paths; batch them.
- In `services/search/`, pin exact versions in lock files; ranges only in library manifests.
- In `services/search/`, lists have a documented, deterministic order.
- In `services/search/`, never rename a column in one step.

## Notifications service (part 2)

- The Notifications team owns `services/notifications/`; ask before changing its public interface.
- Notifications endpoints are versioned under `/v3/notifications`.
- Notifications jobs run in the `notifications-batch` queue and must finish within 30 minutes.
- In `services/notifications/`, if a request is ambiguous, choose the reading closest to existing behaviour and say so.
- In `services/notifications/`, set a timeout on every outbound call.
- In `services/notifications/`, feature flags default to off and have an owner and an expiry.
- In `services/notifications/`, decision records go in `docs/adr/` and are never edited after acceptance.
- In `services/notifications/`, raise the narrowest exception that describes the failure.

## Reporting service (part 2)

- Changes to `services/reporting/schema/` need a migration reviewed by the Reporting team.
- In `services/reporting/`, keep changes scoped to the request.
- Reporting endpoints are versioned under `/v3/reporting`.
- The Reporting on-call rota is the escalation path for `services/reporting/` alerts.
- In `services/reporting/`, unknown configuration keys are an error.
- In `services/reporting/`, commit subjects are imperative and under 72 characters.
- In `services/reporting/`, use the shared fixtures before writing a new one.
- In `services/reporting/`, prefer the standard library when the difference is a few lines.

## Returns service (part 2)

- In `services/returns/`, type-annotate every function signature.
- Returns jobs run in the `returns-batch` queue and must finish within 5 minutes.
- Returns endpoints are versioned under `/v3/returns`.
- The Returns on-call rota is the escalation path for `services/returns/` alerts.
- In `services/returns/`, set a timeout on every outbound call.
- In `services/returns/`, pin exact versions in lock files; ranges only in library manifests.
- In `services/returns/`, add a column as nullable first; backfill; then tighten.
- In `services/returns/`, prefer the standard library when the difference is a few lines.

## Pricing service (part 2)

- Pricing endpoints are versioned under `/v3/pricing`.
- The Pricing team owns `services/pricing/`; ask before changing its public interface.
- Pricing jobs run in the `pricing-batch` queue and must finish within 30 minutes.
- In `services/pricing/`, money is integer cents; never floats.
- In `services/pricing/`, authorisation checks live next to the action they protect.
- In `services/pricing/`, do not log and re-raise the same exception at two levels.
- In `services/pricing/`, dashboards are code; do not hand-edit them.
- In `services/pricing/`, user-facing errors never include stack traces or internal ids.

## Partner API service (part 2)

- Partner API jobs run in the `partner-api-batch` queue and must finish within 10 minutes.
- The Partner API on-call rota is the escalation path for `services/partner-api/` alerts.
- In `services/partner-api/`, retry only idempotent operations, at most three times, with jitter.
- The Partner API team owns `services/partner-api/`; ask before changing its public interface.
- In `services/partner-api/`, do not log and re-raise the same exception at two levels.
- In `services/partner-api/`, feature flags default to off and have an owner and an expiry.
- In `services/partner-api/`, do not branch on environment name in business code.
- In `services/partner-api/`, modules are lower_snake_case; classes are PascalCase; constants are UPPER_SNAKE_CASE.

## Back office service (part 2)

- Changes to `services/back-office/schema/` need a migration reviewed by the Back office team.
- The Back office on-call rota is the escalation path for `services/back-office/` alerts.
- In `services/back-office/`, use parameterised queries; never build SQL with string formatting.
- Back office jobs run in the `back-office-batch` queue and must finish within 30 minutes.
- In `services/back-office/`, update the README in the same change as the behaviour.
- In `services/back-office/`, use 400 for malformed input, 404 for unknown ids and 409 for conflicts with current state.
- In `services/back-office/`, unknown configuration keys are an error.
- In `services/back-office/`, never log email addresses, card numbers or access tokens; log the id instead.

## Mobile gateway service (part 2)

- The Mobile gateway on-call rota is the escalation path for `services/mobile-gateway/` alerts.
- Mobile gateway jobs run in the `mobile-gateway-batch` queue and must finish within 5 minutes.
- The Mobile gateway team owns `services/mobile-gateway/`; ask before changing its public interface.
- In `services/mobile-gateway/`, a request path allocates no more than it must; avoid copying large payloads.
- In `services/mobile-gateway/`, use the structured logger from `platform.logging`; never call `print` in service code.
- In `services/mobile-gateway/`, error messages are lower case with no trailing full stop.
- In `services/mobile-gateway/`, pin exact versions in lock files; ranges only in library manifests.
- In `services/mobile-gateway/`, licences other than MIT, BSD and Apache-2.0 need legal sign-off.

## Fraud service (part 2)

- Fraud endpoints are versioned under `/v2/fraud`.
- The Fraud on-call rota is the escalation path for `services/fraud/` alerts.
- The Fraud team owns `services/fraud/`; ask before changing its public interface.
- Changes to `services/fraud/schema/` need a migration reviewed by the Fraud team.
- In `services/fraud/`, trace ids propagate through every outbound call.
- In `services/fraud/`, raise the narrowest exception that describes the failure.
- In `services/fraud/`, never rename a column in one step.
- In `services/fraud/`, do not abbreviate domain words: `customer`, not `cust`.

## Loyalty service (part 2)

- Loyalty endpoints are versioned under `/v4/loyalty`.
- In `services/loyalty/`, authorisation checks live next to the action they protect.
- Changes to `services/loyalty/schema/` need a migration reviewed by the Loyalty team.
- The Loyalty on-call rota is the escalation path for `services/loyalty/` alerts.
- In `services/loyalty/`, timestamps are ISO 8601 in UTC.
- In `services/loyalty/`, every table has a primary key and created/updated timestamps.
- In `services/loyalty/`, prefer the standard library when the difference is a few lines.
- In `services/loyalty/`, authorisation checks live next to the action they protect.

## Tax service (part 2)

- The Tax team owns `services/tax/`; ask before changing its public interface.
- Tax jobs run in the `tax-batch` queue and must finish within 30 minutes.
- In `services/tax/`, every log line for a request carries the `request_id` field.
- Changes to `services/tax/schema/` need a migration reviewed by the Tax team.
- In `services/tax/`, migrations are forwards-only and safe to run twice.
- In `services/tax/`, error messages are lower case with no trailing full stop.
- In `services/tax/`, do not add a third-party dependency without platform review.
- In `services/tax/`, no N+1 lookups in request paths; batch them.

## Shipping rates service (part 2)

- Shipping rates endpoints are versioned under `/v3/shipping-rates`.
- Changes to `services/shipping-rates/schema/` need a migration reviewed by the Shipping rates team.
- The Shipping rates team owns `services/shipping-rates/`; ask before changing its public interface.
- In `services/shipping-rates/`, licences other than MIT, BSD and Apache-2.0 need legal sign-off.
- In `services/shipping-rates/`, dataclasses in domain packages are frozen.
- In `services/shipping-rates/`, prefer early returns over nested conditionals.
- In `services/shipping-rates/`, never rewrite history on `main`.
- In `services/shipping-rates/`, use parameterised queries; never build SQL with string formatting.

## Reviews service (part 2)

- In `services/reviews/`, a request path allocates no more than it must; avoid copying large payloads.
- Reviews endpoints are versioned under `/v4/reviews`.
- Changes to `services/reviews/schema/` need a migration reviewed by the Reviews team.
- The Reviews on-call rota is the escalation path for `services/reviews/` alerts.
- In `services/reviews/`, decision records go in `docs/adr/` and are never edited after acceptance.
- In `services/reviews/`, type-annotate every function signature.
- In `services/reviews/`, do not remove or rename a response field without a deprecation window.
- In `services/reviews/`, modules are lower_snake_case; classes are PascalCase; constants are UPPER_SNAKE_CASE.

## Recommendations service (part 2)

- The Recommendations on-call rota is the escalation path for `services/recommendations/` alerts.
- Recommendations jobs run in the `recommendations-batch` queue and must finish within 60 minutes.
- In `services/recommendations/`, prefer message passing over locks.
- The Recommendations team owns `services/recommendations/`; ask before changing its public interface.
- In `services/recommendations/`, pagination uses opaque cursors, not page numbers.
- In `services/recommendations/`, do not remove or rename a response field without a deprecation window.
- In `services/recommendations/`, use 400 for malformed input, 404 for unknown ids and 409 for conflicts with current state.
- In `services/recommendations/`, responses are JSON objects, never bare arrays.

## Imports service (part 2)

- Changes to `services/imports/schema/` need a migration reviewed by the Imports team.
- In `services/imports/`, unrelated clean-ups go in their own change.
- Imports endpoints are versioned under `/v4/imports`.
- The Imports team owns `services/imports/`; ask before changing its public interface.
- In `services/imports/`, licences other than MIT, BSD and Apache-2.0 need legal sign-off.
- In `services/imports/`, warnings are for things an operator should look at within a day.
- In `services/imports/`, field names carry their unit: `total_cents`, `timeout_s`.
- In `services/imports/`, trace ids propagate through every outbound call.

## Billing service (part 2)

- Billing endpoints are versioned under `/v3/billing`.
- Changes to `services/billing/schema/` need a migration reviewed by the Billing team.
- In `services/billing/`, do not log and re-raise the same exception at two levels.
- Billing jobs run in the `billing-batch` queue and must finish within 10 minutes.
- In `services/billing/`, lists have a documented, deterministic order.
- In `services/billing/`, unknown configuration keys are an error.
- In `services/billing/`, uploaded file names are untrusted input.
- In `services/billing/`, do not mark a test as skipped without a linked ticket.

## Payments service (part 3)

- In `services/payments/`, commit subjects are imperative and under 72 characters.
- The Payments team owns `services/payments/`; ask before changing its public interface.
- Payments jobs run in the `payments-batch` queue and must finish within 10 minutes.
- Payments endpoints are versioned under `/v3/payments`.
- In `services/payments/`, validate input at the boundary and trust nothing from a client.
- In `services/payments/`, raise the narrowest exception that describes the failure.
- In `services/payments/`, streams over lists for anything unbounded.
- In `services/payments/`, never log email addresses, card numbers or access tokens; log the id instead.

## Catalogue service (part 3)

- Catalogue jobs run in the `catalogue-batch` queue and must finish within 30 minutes.
- The Catalogue on-call rota is the escalation path for `services/catalogue/` alerts.
- In `services/catalogue/`, metric names are `service_noun_unit`.
- The Catalogue team owns `services/catalogue/`; ask before changing its public interface.
- In `services/catalogue/`, raise the narrowest exception that describes the failure.
- In `services/catalogue/`, a timeout is an error, not an empty result.
- In `services/catalogue/`, use the shared fixtures before writing a new one.
- In `services/catalogue/`, validate input at the boundary and trust nothing from a client.

## Fulfilment service (part 3)

- In `services/fulfilment/`, do not commit unless asked to.
- The Fulfilment team owns `services/fulfilment/`; ask before changing its public interface.
- Changes to `services/fulfilment/schema/` need a migration reviewed by the Fulfilment team.
- The Fulfilment on-call rota is the escalation path for `services/fulfilment/` alerts.
- In `services/fulfilment/`, no environment lookups below the composition root.
- In `services/fulfilment/`, no environment lookups below the composition root.
- In `services/fulfilment/`, pin exact versions in lock files; ranges only in library manifests.
- In `services/fulfilment/`, every service exports request count, error count and latency.

## Accounts service (part 3)

- Accounts jobs run in the `accounts-batch` queue and must finish within 10 minutes.
- Changes to `services/accounts/schema/` need a migration reviewed by the Accounts team.
- In `services/accounts/`, runbooks name the alert that leads to them.
- The Accounts on-call rota is the escalation path for `services/accounts/` alerts.
- In `services/accounts/`, no commented-out code.
- In `services/accounts/`, authorisation checks live next to the action they protect.
- In `services/accounts/`, add a column as nullable first; backfill; then tighten.
- In `services/accounts/`, unrelated clean-ups go in their own change.

## Search service (part 3)

- The Search team owns `services/search/`; ask before changing its public interface.
- The Search on-call rota is the escalation path for `services/search/` alerts.
- Search jobs run in the `search-batch` queue and must finish within 5 minutes.
- In `services/search/`, test names read as sentences about behaviour.
- In `services/search/`, a request path allocates no more than it must; avoid copying large payloads.
- In `services/search/`, unrelated clean-ups go in their own change.
- In `services/search/`, do not branch on environment name in business code.
- In `services/search/`, do not disable TLS verification, even in tests.

## Notifications service (part 3)

- Changes to `services/notifications/schema/` need a migration reviewed by the Notifications team.
- Notifications jobs run in the `notifications-batch` queue and must finish within 15 minutes.
- In `services/notifications/`, use the shared fixtures before writing a new one.
- The Notifications team owns `services/notifications/`; ask before changing its public interface.
- In `services/notifications/`, uploaded file names are untrusted input.
- In `services/notifications/`, every behaviour change comes with a test that fails without it.
- In `services/notifications/`, commit subjects are imperative and under 72 characters.
- In `services/notifications/`, do not remove or rename a response field without a deprecation window.

## Reporting service (part 3)

- Reporting endpoints are versioned under `/v2/reporting`.
- The Reporting team owns `services/reporting/`; ask before changing its public interface.
- In `services/reporting/`, use the shared fixtures before writing a new one.
- Changes to `services/reporting/schema/` need a migration reviewed by the Reporting team.
- In `services/reporting/`, line length 110; double quotes for strings.
- In `services/reporting/`, diagrams live next to the code they describe.
- In `services/reporting/`, do not remove or rename a response field without a deprecation window.
- In `services/reporting/`, metric names are `service_noun_unit`.

## Returns service (part 3)

- Returns endpoints are versioned under `/v1/returns`.
- The Returns team owns `services/returns/`; ask before changing its public interface.
- Returns jobs run in the `returns-batch` queue and must finish within 5 minutes.
- Changes to `services/returns/schema/` need a migration reviewed by the Returns team.
- In `services/returns/`, secrets come from the secret manager; never from the repository or an environment default.
- In `services/returns/`, if a request is ambiguous, choose the reading closest to existing behaviour and say so.
- In `services/returns/`, test names read as sentences about behaviour.
- In `services/returns/`, configuration is read once at start-up and passed in.

## Pricing service (part 3)

- The Pricing team owns `services/pricing/`; ask before changing its public interface.
- The Pricing on-call rota is the escalation path for `services/pricing/` alerts.
- Pricing endpoints are versioned under `/v2/pricing`.
- In `services/pricing/`, a request path allocates no more than it must; avoid copying large payloads.
- In `services/pricing/`, avoid `utils` and `helpers` modules; name the module for what it holds.
- In `services/pricing/`, tests drive public interfaces, not private attributes.
- In `services/pricing/`, error messages are lower case with no trailing full stop.
- In `services/pricing/`, money is integer cents; never floats.

## Partner API service (part 3)

- The Partner API team owns `services/partner-api/`; ask before changing its public interface.
- Changes to `services/partner-api/schema/` need a migration reviewed by the Partner API team.
- Partner API endpoints are versioned under `/v1/partner-api`.
- Partner API jobs run in the `partner-api-batch` queue and must finish within 30 minutes.
- In `services/partner-api/`, do not mark a test as skipped without a linked ticket.
- In `services/partner-api/`, do not catch `Exception` unless you re-raise or convert it at a boundary.
- In `services/partner-api/`, configuration is read once at start-up and passed in.
- In `services/partner-api/`, deleting data needs a retention review.

## Back office service (part 3)

- Changes to `services/back-office/schema/` need a migration reviewed by the Back office team.
- The Back office on-call rota is the escalation path for `services/back-office/` alerts.
- Back office jobs run in the `back-office-batch` queue and must finish within 30 minutes.
- Back office endpoints are versioned under `/v4/back-office`.
- In `services/back-office/`, unknown configuration keys are an error.
- In `services/back-office/`, vendored code lives under `third_party/` and is never edited in place.
- In `services/back-office/`, licences other than MIT, BSD and Apache-2.0 need legal sign-off.
- In `services/back-office/`, measure before optimising, and keep the benchmark with the change.

## Mobile gateway service (part 3)

- Mobile gateway endpoints are versioned under `/v3/mobile-gateway`.
- Changes to `services/mobile-gateway/schema/` need a migration reviewed by the Mobile gateway team.
- Mobile gateway jobs run in the `mobile-gateway-batch` queue and must finish within 10 minutes.
- The Mobile gateway on-call rota is the escalation path for `services/mobile-gateway/` alerts.
- In `services/mobile-gateway/`, no sleeping in tests; inject a clock.
- In `services/mobile-gateway/`, add a column as nullable first; backfill; then tighten.
- In `services/mobile-gateway/`, responses are JSON objects, never bare arrays.
- In `services/mobile-gateway/`, keep changes scoped to the request.

## Fraud service (part 3)

- The Fraud on-call rota is the escalation path for `services/fraud/` alerts.
- The Fraud team owns `services/fraud/`; ask before changing its public interface.
- Changes to `services/fraud/schema/` need a migration reviewed by the Fraud team.
- In `services/fraud/`, every log line for a request carries the `request_id` field.
- In `services/fraud/`, no environment lookups below the composition root.
- In `services/fraud/`, every behaviour change comes with a test that fails without it.
- In `services/fraud/`, warnings are for things an operator should look at within a day.
- In `services/fraud/`, thread pools are sized in configuration.

## Loyalty service (part 3)

- The Loyalty team owns `services/loyalty/`; ask before changing its public interface.
- Changes to `services/loyalty/schema/` need a migration reviewed by the Loyalty team.
- Loyalty endpoints are versioned under `/v1/loyalty`.
- The Loyalty on-call rota is the escalation path for `services/loyalty/` alerts.
- In `services/loyalty/`, commit subjects are imperative and under 72 characters.
- In `services/loyalty/`, modules are lower_snake_case; classes are PascalCase; constants are UPPER_SNAKE_CASE.
- In `services/loyalty/`, do not disable TLS verification, even in tests.
- In `services/loyalty/`, do not remove or rename a response field without a deprecation window.

## Tax service (part 3)

- Tax endpoints are versioned under `/v3/tax`.
- The Tax on-call rota is the escalation path for `services/tax/` alerts.
- The Tax team owns `services/tax/`; ask before changing its public interface.
- Changes to `services/tax/schema/` need a migration reviewed by the Tax team.
- In `services/tax/`, modules are lower_snake_case; classes are PascalCase; constants are UPPER_SNAKE_CASE.
- In `services/tax/`, raise the narrowest exception that describes the failure.
- In `services/tax/`, metric names are `service_noun_unit`.
- In `services/tax/`, prefer early returns over nested conditionals.

## Shipping rates service (part 3)

- In `services/shipping-rates/`, cache only what you can invalidate.
- Shipping rates endpoints are versioned under `/v2/shipping-rates`.
- The Shipping rates team owns `services/shipping-rates/`; ask before changing its public interface.
- Shipping rates jobs run in the `shipping-rates-batch` queue and must finish within 15 minutes.
- In `services/shipping-rates/`, remove a dependency in the same change that removes its last use.
- In `services/shipping-rates/`, use the shared fixtures before writing a new one.
- In `services/shipping-rates/`, do not commit unless asked to.
- In `services/shipping-rates/`, streams over lists for anything unbounded.

## Reviews service (part 3)

- Reviews jobs run in the `reviews-batch` queue and must finish within 10 minutes.
- The Reviews team owns `services/reviews/`; ask before changing its public interface.
- The Reviews on-call rota is the escalation path for `services/reviews/` alerts.
- Reviews endpoints are versioned under `/v2/reviews`.
- In `services/reviews/`, test names read as sentences about behaviour.
- In `services/reviews/`, alerts page only for user-visible impact.
- In `services/reviews/`, tests drive public interfaces, not private attributes.
- In `services/reviews/`, uploaded file names are untrusted input.

## Recommendations service (part 3)

- Recommendations jobs run in the `recommendations-batch` queue and must finish within 10 minutes.
- Recommendations endpoints are versioned under `/v2/recommendations`.
- In `services/recommendations/`, use parameterised queries; never build SQL with string formatting.
- The Recommendations team owns `services/recommendations/`; ask before changing its public interface.
- In `services/recommendations/`, public functions have a one-line docstring in the imperative mood.
- In `services/recommendations/`, responses are JSON objects, never bare arrays.
- In `services/recommendations/`, do not remove or rename a response field without a deprecation window.
- In `services/recommendations/`, shared mutable state needs an owner; say who in a comment.

## Imports service (part 3)

- Imports jobs run in the `imports-batch` queue and must finish within 15 minutes.
- In `services/imports/`, pin exact versions in lock files; ranges only in library manifests.
- Changes to `services/imports/schema/` need a migration reviewed by the Imports team.
- The Imports on-call rota is the escalation path for `services/imports/` alerts.
- In `services/imports/`, money is integer cents; never floats.
- In `services/imports/`, unrelated clean-ups go in their own change.
- In `services/imports/`, never log email addresses, card numbers or access tokens; log the id instead.
- In `services/imports/`, sampling rates are configuration, not constants.

## Billing service (part 3)

- The Billing on-call rota is the escalation path for `services/billing/` alerts.
- In `services/billing/`, prefer message passing over locks.
- Billing jobs run in the `billing-batch` queue and must finish within 30 minutes.
- Billing endpoints are versioned under `/v3/billing`.
- In `services/billing/`, feature flags default to off and have an owner and an expiry.
- In `services/billing/`, use 400 for malformed input, 404 for unknown ids and 409 for conflicts with current state.
- In `services/billing/`, lists have a documented, deterministic order.
- In `services/billing/`, no commented-out code.

## Payments service (part 4)

- Payments jobs run in the `payments-batch` queue and must finish within 30 minutes.
- Changes to `services/payments/schema/` need a migration reviewed by the Payments team.
- In `services/payments/`, lists have a documented, deterministic order.
- Payments endpoints are versioned under `/v3/payments`.
- In `services/payments/`, metric names are `service_noun_unit`.
- In `services/payments/`, prefer the standard library when the difference is a few lines.
- In `services/payments/`, never log email addresses, card numbers or access tokens; log the id instead.
- In `services/payments/`, no N+1 lookups in request paths; batch them.

## Catalogue service (part 4)

- In `services/catalogue/`, field names carry their unit: `total_cents`, `timeout_s`.
- The Catalogue on-call rota is the escalation path for `services/catalogue/` alerts.
- Catalogue jobs run in the `catalogue-batch` queue and must finish within 5 minutes.
- Catalogue endpoints are versioned under `/v4/catalogue`.
- In `services/catalogue/`, feature flags default to off and have an owner and an expiry.
- In `services/catalogue/`, do not remove or rename a response field without a deprecation window.
- In `services/catalogue/`, use parameterised queries; never build SQL with string formatting.
- In `services/catalogue/`, vendored code lives under `third_party/` and is never edited in place.

## Fulfilment service (part 4)

- In `services/fulfilment/`, do not branch on environment name in business code.
- The Fulfilment on-call rota is the escalation path for `services/fulfilment/` alerts.
- Changes to `services/fulfilment/schema/` need a migration reviewed by the Fulfilment team.
- The Fulfilment team owns `services/fulfilment/`; ask before changing its public interface.
- In `services/fulfilment/`, streams over lists for anything unbounded.
- In `services/fulfilment/`, migrations are forwards-only and safe to run twice.
- In `services/fulfilment/`, never hold a lock across I/O.
- In `services/fulfilment/`, use the structured logger from `platform.logging`; never call `print` in service code.

## Accounts service (part 4)

- In `services/accounts/`, do not commit unless asked to.
- Accounts endpoints are versioned under `/v1/accounts`.
- Changes to `services/accounts/schema/` need a migration reviewed by the Accounts team.
- The Accounts on-call rota is the escalation path for `services/accounts/` alerts.
- In `services/accounts/`, uploaded file names are untrusted input.
- In `services/accounts/`, cache only what you can invalidate.
- In `services/accounts/`, prefer the standard library when the difference is a few lines.
- In `services/accounts/`, lists have a documented, deterministic order.

## Search service (part 4)

- In `services/search/`, cache only what you can invalidate.
- The Search on-call rota is the escalation path for `services/search/` alerts.
- Changes to `services/search/schema/` need a migration reviewed by the Search team.
- Search jobs run in the `search-batch` queue and must finish within 10 minutes.
- In `services/search/`, never rewrite history on `main`.
- In `services/search/`, retry only idempotent operations, at most three times, with jitter.
- In `services/search/`, runbooks name the alert that leads to them.
- In `services/search/`, every table has a primary key and created/updated timestamps.

## Notifications service (part 4)

- Notifications jobs run in the `notifications-batch` queue and must finish within 30 minutes.
- The Notifications on-call rota is the escalation path for `services/notifications/` alerts.
- The Notifications team owns `services/notifications/`; ask before changing its public interface.
- In `services/notifications/`, uploaded file names are untrusted input.
- In `services/notifications/`, never rewrite history on `main`.
- In `services/notifications/`, set a timeout on every outbound call.
- In `services/notifications/`, never hold a lock across I/O.
- In `services/notifications/`, do not branch on environment name in business code.

## Reporting service (part 4)

- The Reporting team owns `services/reporting/`; ask before changing its public interface.
- Changes to `services/reporting/schema/` need a migration reviewed by the Reporting team.
- The Reporting on-call rota is the escalation path for `services/reporting/` alerts.
- Reporting endpoints are versioned under `/v2/reporting`.
- In `services/reporting/`, modules are lower_snake_case; classes are PascalCase; constants are UPPER_SNAKE_CASE.
- In `services/reporting/`, keep changes scoped to the request.
- In `services/reporting/`, prefer early returns over nested conditionals.
- In `services/reporting/`, lists have a documented, deterministic order.

## Returns service (part 4)

- Returns endpoints are versioned under `/v3/returns`.
- The Returns on-call rota is the escalation path for `services/returns/` alerts.
- Returns jobs run in the `returns-batch` queue and must finish within 10 minutes.
- In `services/returns/`, do not disable TLS verification, even in tests.
- In `services/returns/`, dashboards are code; do not hand-edit them.
- In `services/returns/`, money is integer cents; never floats.
- In `services/returns/`, metric names are `service_noun_unit`.
- In `services/returns/`, use parameterised queries; never build SQL with string formatting.

## Pricing service (part 4)

- The Pricing team owns `services/pricing/`; ask before changing its public interface.
- In `services/pricing/`, do not document what the code already says.
- Pricing jobs run in the `pricing-batch` queue and must finish within 10 minutes.
- Pricing endpoints are versioned under `/v4/pricing`.
- In `services/pricing/`, modules are lower_snake_case; classes are PascalCase; constants are UPPER_SNAKE_CASE.
- In `services/pricing/`, every table has a primary key and created/updated timestamps.
- In `services/pricing/`, set a timeout on every outbound call.
- In `services/pricing/`, runbooks name the alert that leads to them.

## Partner API service (part 4)

- In `services/partner-api/`, never log email addresses, card numbers or access tokens; log the id instead.
- Partner API jobs run in the `partner-api-batch` queue and must finish within 30 minutes.
- The Partner API team owns `services/partner-api/`; ask before changing its public interface.
- The Partner API on-call rota is the escalation path for `services/partner-api/` alerts.
- In `services/partner-api/`, error messages are lower case with no trailing full stop.
- In `services/partner-api/`, trace ids propagate through every outbound call.
- In `services/partner-api/`, deleting data needs a retention review.
- In `services/partner-api/`, defaults live in one place.

## Back office service (part 4)

- In `services/back-office/`, log at `info` for state changes and `debug` for anything per-item in a loop.
- The Back office team owns `services/back-office/`; ask before changing its public interface.
- Back office jobs run in the `back-office-batch` queue and must finish within 15 minutes.
- Changes to `services/back-office/schema/` need a migration reviewed by the Back office team.
- In `services/back-office/`, do not mark a test as skipped without a linked ticket.
- In `services/back-office/`, cancellation is cooperative; check for it in long loops.
- In `services/back-office/`, secrets come from the secret manager; never from the repository or an environment default.
- In `services/back-office/`, prefer message passing over locks.

## Mobile gateway service (part 4)

- The Mobile gateway on-call rota is the escalation path for `services/mobile-gateway/` alerts.
- The Mobile gateway team owns `services/mobile-gateway/`; ask before changing its public interface.
- Changes to `services/mobile-gateway/schema/` need a migration reviewed by the Mobile gateway team.
- Mobile gateway jobs run in the `mobile-gateway-batch` queue and must finish within 15 minutes.
- In `services/mobile-gateway/`, metric names are `service_noun_unit`.
- In `services/mobile-gateway/`, never hold a lock across I/O.
- In `services/mobile-gateway/`, do not abbreviate domain words: `customer`, not `cust`.
- In `services/mobile-gateway/`, feature flags default to off and have an owner and an expiry.

## Fraud service (part 4)

- Fraud jobs run in the `fraud-batch` queue and must finish within 15 minutes.
- The Fraud on-call rota is the escalation path for `services/fraud/` alerts.
- Fraud endpoints are versioned under `/v2/fraud`.
- Changes to `services/fraud/schema/` need a migration reviewed by the Fraud team.
- In `services/fraud/`, migrations are forwards-only and safe to run twice.
- In `services/fraud/`, sampling rates are configuration, not constants.
- In `services/fraud/`, validate input at the boundary and trust nothing from a client.
- In `services/fraud/`, do not remove or rename a response field without a deprecation window.

## Loyalty service (part 4)

- In `services/loyalty/`, every behaviour change comes with a test that fails without it.
- Changes to `services/loyalty/schema/` need a migration reviewed by the Loyalty team.
- The Loyalty team owns `services/loyalty/`; ask before changing its public interface.
- The Loyalty on-call rota is the escalation path for `services/loyalty/` alerts.
- In `services/loyalty/`, pin exact versions in lock files; ranges only in library manifests.
- In `services/loyalty/`, sampling rates are configuration, not constants.
- In `services/loyalty/`, dataclasses in domain packages are frozen.
- In `services/loyalty/`, dashboards are code; do not hand-edit them.

## Tax service (part 4)

- Tax jobs run in the `tax-batch` queue and must finish within 10 minutes.
- Changes to `services/tax/schema/` need a migration reviewed by the Tax team.
- The Tax team owns `services/tax/`; ask before changing its public interface.
- Tax endpoints are versioned under `/v2/tax`.
- In `services/tax/`, remove a dependency in the same change that removes its last use.
- In `services/tax/`, do not mark a test as skipped without a linked ticket.
- In `services/tax/`, metric names are `service_noun_unit`.
- In `services/tax/`, public functions have a one-line docstring in the imperative mood.

## Shipping rates service (part 4)

- The Shipping rates team owns `services/shipping-rates/`; ask before changing its public interface.
- Shipping rates jobs run in the `shipping-rates-batch` queue and must finish within 60 minutes.
- Shipping rates endpoints are versioned under `/v3/shipping-rates`.
- The Shipping rates on-call rota is the escalation path for `services/shipping-rates/` alerts.
- In `services/shipping-rates/`, do not log and re-raise the same exception at two levels.
- In `services/shipping-rates/`, do not commit unless asked to.
- In `services/shipping-rates/`, timestamps are ISO 8601 in UTC.
- In `services/shipping-rates/`, line length 110; double quotes for strings.

## Reviews service (part 4)

- The Reviews team owns `services/reviews/`; ask before changing its public interface.
- Reviews endpoints are versioned under `/v1/reviews`.
- In `services/reviews/`, set a timeout on every outbound call.
- The Reviews on-call rota is the escalation path for `services/reviews/` alerts.
- In `services/reviews/`, a timeout is an error, not an empty result.
- In `services/reviews/`, every service exports request count, error count and latency.
- In `services/reviews/`, prefer message passing over locks.
- In `services/reviews/`, line length 110; double quotes for strings.

## Recommendations service (part 4)

- In `services/recommendations/`, lists have a documented, deterministic order.
- The Recommendations on-call rota is the escalation path for `services/recommendations/` alerts.
- Changes to `services/recommendations/schema/` need a migration reviewed by the Recommendations team.
- The Recommendations team owns `services/recommendations/`; ask before changing its public interface.
- In `services/recommendations/`, use the structured logger from `platform.logging`; never call `print` in service code.
- In `services/recommendations/`, dashboards are code; do not hand-edit them.
- In `services/recommendations/`, keep changes scoped to the request.
- In `services/recommendations/`, lists have a documented, deterministic order.

## Imports service (part 4)

- Imports endpoints are versioned under `/v2/imports`.
- Imports jobs run in the `imports-batch` queue and must finish within 30 minutes.
- Changes to `services/imports/schema/` need a migration reviewed by the Imports team.
- The Imports team owns `services/imports/`; ask before changing its public interface.
- In `services/imports/`, set a timeout on every outbound call.
- In `services/imports/`, modules are lower_snake_case; classes are PascalCase; constants are UPPER_SNAKE_CASE.
- In `services/imports/`, feature flags default to off and have an owner and an expiry.
- In `services/imports/`, no N+1 lookups in request paths; batch them.

## Billing service (part 4)

- Billing jobs run in the `billing-batch` queue and must finish within 5 minutes.
- The Billing team owns `services/billing/`; ask before changing its public interface.
- Billing endpoints are versioned under `/v4/billing`.
- Changes to `services/billing/schema/` need a migration reviewed by the Billing team.
- In `services/billing/`, use 400 for malformed input, 404 for unknown ids and 409 for conflicts with current state.
- In `services/billing/`, pagination uses opaque cursors, not page numbers.
- In `services/billing/`, use the shared fixtures before writing a new one.
- In `services/billing/`, boolean names read as questions: `is_active`, `has_stock`.

## Payments service (part 5)

- Payments jobs run in the `payments-batch` queue and must finish within 60 minutes.
- The Payments team owns `services/payments/`; ask before changing its public interface.
- In `services/payments/`, lists have a documented, deterministic order.
- Payments endpoints are versioned under `/v3/payments`.
- In `services/payments/`, responses are JSON objects, never bare arrays.
- In `services/payments/`, secrets come from the secret manager; never from the repository or an environment default.
- In `services/payments/`, do not catch `Exception` unless you re-raise or convert it at a boundary.
- In `services/payments/`, do not branch on environment name in business code.

## Catalogue service (part 5)

- Changes to `services/catalogue/schema/` need a migration reviewed by the Catalogue team.
- Catalogue endpoints are versioned under `/v4/catalogue`.
- In `services/catalogue/`, deleting data needs a retention review.
- Catalogue jobs run in the `catalogue-batch` queue and must finish within 10 minutes.
- In `services/catalogue/`, do not mark a test as skipped without a linked ticket.
- In `services/catalogue/`, pin exact versions in lock files; ranges only in library manifests.
- In `services/catalogue/`, sampling rates are configuration, not constants.
- In `services/catalogue/`, a test asserts one behaviour; split it if the name needs 'and'.

## Fulfilment service (part 5)

- Changes to `services/fulfilment/schema/` need a migration reviewed by the Fulfilment team.
- In `services/fulfilment/`, deleting data needs a retention review.
- Fulfilment endpoints are versioned under `/v3/fulfilment`.
- The Fulfilment team owns `services/fulfilment/`; ask before changing its public interface.
- In `services/fulfilment/`, log at `info` for state changes and `debug` for anything per-item in a loop.
- In `services/fulfilment/`, avoid `utils` and `helpers` modules; name the module for what it holds.
- In `services/fulfilment/`, do not mark a test as skipped without a linked ticket.
- In `services/fulfilment/`, no sleeping in tests; inject a clock.

## Accounts service (part 5)

- Changes to `services/accounts/schema/` need a migration reviewed by the Accounts team.
- The Accounts team owns `services/accounts/`; ask before changing its public interface.
- Accounts endpoints are versioned under `/v1/accounts`.
- Accounts jobs run in the `accounts-batch` queue and must finish within 30 minutes.
- In `services/accounts/`, if a request is ambiguous, choose the reading closest to existing behaviour and say so.
- In `services/accounts/`, diagrams live next to the code they describe.
- In `services/accounts/`, use 400 for malformed input, 404 for unknown ids and 409 for conflicts with current state.
- In `services/accounts/`, no environment lookups below the composition root.

## Search service (part 5)

- The Search team owns `services/search/`; ask before changing its public interface.
- Search endpoints are versioned under `/v2/search`.
- Changes to `services/search/schema/` need a migration reviewed by the Search team.
- Search jobs run in the `search-batch` queue and must finish within 5 minutes.
- In `services/search/`, cache only what you can invalidate.
- In `services/search/`, warnings are for things an operator should look at within a day.
- In `services/search/`, dataclasses in domain packages are frozen.
- In `services/search/`, unrelated clean-ups go in their own change.

## Notifications service (part 5)

- The Notifications team owns `services/notifications/`; ask before changing its public interface.
- The Notifications on-call rota is the escalation path for `services/notifications/` alerts.
- Notifications jobs run in the `notifications-batch` queue and must finish within 30 minutes.
- Changes to `services/notifications/schema/` need a migration reviewed by the Notifications team.
- In `services/notifications/`, sampling rates are configuration, not constants.
- In `services/notifications/`, raise the narrowest exception that describes the failure.
- In `services/notifications/`, money is integer cents; never floats.
- In `services/notifications/`, prefer early returns over nested conditionals.

## Reporting service (part 5)

- Changes to `services/reporting/schema/` need a migration reviewed by the Reporting team.
- The Reporting team owns `services/reporting/`; ask before changing its public interface.
- Reporting endpoints are versioned under `/v2/reporting`.
- Reporting jobs run in the `reporting-batch` queue and must finish within 10 minutes.
- In `services/reporting/`, unrelated clean-ups go in their own change.
- In `services/reporting/`, avoid `utils` and `helpers` modules; name the module for what it holds.
- In `services/reporting/`, no commented-out code.
- In `services/reporting/`, do not log and re-raise the same exception at two levels.

## Returns service (part 5)

- Returns endpoints are versioned under `/v3/returns`.
- Changes to `services/returns/schema/` need a migration reviewed by the Returns team.
- The Returns team owns `services/returns/`; ask before changing its public interface.
- The Returns on-call rota is the escalation path for `services/returns/` alerts.
- In `services/returns/`, defaults live in one place.
- In `services/returns/`, do not catch `Exception` unless you re-raise or convert it at a boundary.
- In `services/returns/`, dataclasses in domain packages are frozen.
- In `services/returns/`, field names carry their unit: `total_cents`, `timeout_s`.

## Pricing service (part 5)

- Pricing jobs run in the `pricing-batch` queue and must finish within 60 minutes.
- Changes to `services/pricing/schema/` need a migration reviewed by the Pricing team.
- Pricing endpoints are versioned under `/v2/pricing`.
- In `services/pricing/`, pin exact versions in lock files; ranges only in library manifests.
- In `services/pricing/`, decision records go in `docs/adr/` and are never edited after acceptance.
- In `services/pricing/`, commit subjects are imperative and under 72 characters.
- In `services/pricing/`, every log line for a request carries the `request_id` field.
- In `services/pricing/`, vendored code lives under `third_party/` and is never edited in place.

## Partner API service (part 5)

- Changes to `services/partner-api/schema/` need a migration reviewed by the Partner API team.
- Partner API jobs run in the `partner-api-batch` queue and must finish within 30 minutes.
- The Partner API on-call rota is the escalation path for `services/partner-api/` alerts.
- The Partner API team owns `services/partner-api/`; ask before changing its public interface.
- In `services/partner-api/`, no sleeping in tests; inject a clock.
- In `services/partner-api/`, cache only what you can invalidate.
- In `services/partner-api/`, public functions have a one-line docstring in the imperative mood.
- In `services/partner-api/`, streams over lists for anything unbounded.

## Back office service (part 5)

- In `services/back-office/`, prefer message passing over locks.
- The Back office on-call rota is the escalation path for `services/back-office/` alerts.
- Back office jobs run in the `back-office-batch` queue and must finish within 60 minutes.
- Changes to `services/back-office/schema/` need a migration reviewed by the Back office team.
- In `services/back-office/`, feature flags default to off and have an owner and an expiry.
- In `services/back-office/`, boolean names read as questions: `is_active`, `has_stock`.
- In `services/back-office/`, decision records go in `docs/adr/` and are never edited after acceptance.
- In `services/back-office/`, never rename a column in one step.

## Mobile gateway service (part 5)

- Mobile gateway endpoints are versioned under `/v4/mobile-gateway`.
- Changes to `services/mobile-gateway/schema/` need a migration reviewed by the Mobile gateway team.
- The Mobile gateway team owns `services/mobile-gateway/`; ask before changing its public interface.
- In `services/mobile-gateway/`, use the structured logger from `platform.logging`; never call `print` in service code.
- In `services/mobile-gateway/`, no wildcard imports; absolute imports only.
- In `services/mobile-gateway/`, diagrams live next to the code they describe.
- In `services/mobile-gateway/`, prefer early returns over nested conditionals.
- In `services/mobile-gateway/`, licences other than MIT, BSD and Apache-2.0 need legal sign-off.

## Fraud service (part 5)

- Fraud endpoints are versioned under `/v4/fraud`.
- Changes to `services/fraud/schema/` need a migration reviewed by the Fraud team.
- In `services/fraud/`, every service exports request count, error count and latency.
- Fraud jobs run in the `fraud-batch` queue and must finish within 60 minutes.
- In `services/fraud/`, no environment lookups below the composition root.
- In `services/fraud/`, public functions have a one-line docstring in the imperative mood.
- In `services/fraud/`, dataclasses in domain packages are frozen.
- In `services/fraud/`, trace ids propagate through every outbound call.

## Loyalty service (part 5)

- The Loyalty team owns `services/loyalty/`; ask before changing its public interface.
- The Loyalty on-call rota is the escalation path for `services/loyalty/` alerts.
- In `services/loyalty/`, every table has a primary key and created/updated timestamps.
- Changes to `services/loyalty/schema/` need a migration reviewed by the Loyalty team.
- In `services/loyalty/`, a timeout is an error, not an empty result.
- In `services/loyalty/`, do not disable TLS verification, even in tests.
- In `services/loyalty/`, authorisation checks live next to the action they protect.
- In `services/loyalty/`, unknown configuration keys are an error.

## Tax service (part 5)

- Changes to `services/tax/schema/` need a migration reviewed by the Tax team.
- Tax jobs run in the `tax-batch` queue and must finish within 10 minutes.
- In `services/tax/`, do not catch `Exception` unless you re-raise or convert it at a boundary.
- Tax endpoints are versioned under `/v1/tax`.
- In `services/tax/`, log at `info` for state changes and `debug` for anything per-item in a loop.
- In `services/tax/`, cancellation is cooperative; check for it in long loops.
- In `services/tax/`, never rename a column in one step.
- In `services/tax/`, log at `info` for state changes and `debug` for anything per-item in a loop.

## Shipping rates service (part 5)

- In `services/shipping-rates/`, diagrams live next to the code they describe.
- Shipping rates jobs run in the `shipping-rates-batch` queue and must finish within 60 minutes.
- Shipping rates endpoints are versioned under `/v2/shipping-rates`.
- Changes to `services/shipping-rates/schema/` need a migration reviewed by the Shipping rates team.
- In `services/shipping-rates/`, modules are lower_snake_case; classes are PascalCase; constants are UPPER_SNAKE_CASE.
- In `services/shipping-rates/`, public functions have a one-line docstring in the imperative mood.
- In `services/shipping-rates/`, configuration is read once at start-up and passed in.
- In `services/shipping-rates/`, unknown configuration keys are an error.

## Reviews service (part 5)

- Reviews endpoints are versioned under `/v2/reviews`.
- In `services/reviews/`, pagination uses opaque cursors, not page numbers.
- Changes to `services/reviews/schema/` need a migration reviewed by the Reviews team.
- Reviews jobs run in the `reviews-batch` queue and must finish within 5 minutes.
- In `services/reviews/`, raise the narrowest exception that describes the failure.
- In `services/reviews/`, alerts page only for user-visible impact.
- In `services/reviews/`, raise the narrowest exception that describes the failure.
- In `services/reviews/`, vendored code lives under `third_party/` and is never edited in place.

## Recommendations service (part 5)

- Changes to `services/recommendations/schema/` need a migration reviewed by the Recommendations team.
- In `services/recommendations/`, sampling rates are configuration, not constants.
- Recommendations endpoints are versioned under `/v2/recommendations`.
- The Recommendations team owns `services/recommendations/`; ask before changing its public interface.
- In `services/recommendations/`, authorisation checks live next to the action they protect.
- In `services/recommendations/`, never log email addresses, card numbers or access tokens; log the id instead.
- In `services/recommendations/`, a test asserts one behaviour; split it if the name needs 'and'.
- In `services/recommendations/`, migrations are forwards-only and safe to run twice.

## Imports service (part 5)

- Imports endpoints are versioned under `/v4/imports`.
- Imports jobs run in the `imports-batch` queue and must finish within 5 minutes.
- The Imports on-call rota is the escalation path for `services/imports/` alerts.
- The Imports team owns `services/imports/`; ask before changing its public interface.
- In `services/imports/`, dataclasses in domain packages are frozen.
- In `services/imports/`, responses are JSON objects, never bare arrays.
- In `services/imports/`, timestamps are ISO 8601 in UTC.
- In `services/imports/`, tests drive public interfaces, not private attributes.

## Billing service (part 5)

- The Billing team owns `services/billing/`; ask before changing its public interface.
- In `services/billing/`, responses are JSON objects, never bare arrays.
- Billing endpoints are versioned under `/v2/billing`.
- Billing jobs run in the `billing-batch` queue and must finish within 15 minutes.
- In `services/billing/`, keep changes scoped to the request.
- In `services/billing/`, line length 110; double quotes for strings.
- In `services/billing/`, trace ids propagate through every outbound call.
- In `services/billing/`, set a timeout on every outbound call.

## Payments service (part 6)

- Changes to `services/payments/schema/` need a migration reviewed by the Payments team.
- The Payments on-call rota is the escalation path for `services/payments/` alerts.
- In `services/payments/`, shared mutable state needs an owner; say who in a comment.
- The Payments team owns `services/payments/`; ask before changing its public interface.
- In `services/payments/`, cancellation is cooperative; check for it in long loops.
- In `services/payments/`, uploaded file names are untrusted input.
- In `services/payments/`, error messages are lower case with no trailing full stop.
- In `services/payments/`, use parameterised queries; never build SQL with string formatting.

## Catalogue service (part 6)

- The Catalogue on-call rota is the escalation path for `services/catalogue/` alerts.
- Catalogue endpoints are versioned under `/v3/catalogue`.
- The Catalogue team owns `services/catalogue/`; ask before changing its public interface.
- Catalogue jobs run in the `catalogue-batch` queue and must finish within 15 minutes.
- In `services/catalogue/`, never hold a lock across I/O.
- In `services/catalogue/`, every log line for a request carries the `request_id` field.
- In `services/catalogue/`, money is integer cents; never floats.
- In `services/catalogue/`, do not mark a test as skipped without a linked ticket.

## Fulfilment service (part 6)

- Fulfilment endpoints are versioned under `/v1/fulfilment`.
- Changes to `services/fulfilment/schema/` need a migration reviewed by the Fulfilment team.
- In `services/fulfilment/`, pin exact versions in lock files; ranges only in library manifests.
- The Fulfilment on-call rota is the escalation path for `services/fulfilment/` alerts.
- In `services/fulfilment/`, authorisation checks live next to the action they protect.
- In `services/fulfilment/`, licences other than MIT, BSD and Apache-2.0 need legal sign-off.
- In `services/fulfilment/`, lists have a documented, deterministic order.
- In `services/fulfilment/`, cache only what you can invalidate.

## Accounts service (part 6)

- The Accounts on-call rota is the escalation path for `services/accounts/` alerts.
- Accounts endpoints are versioned under `/v1/accounts`.
- The Accounts team owns `services/accounts/`; ask before changing its public interface.
- Changes to `services/accounts/schema/` need a migration reviewed by the Accounts team.
- In `services/accounts/`, configuration is read once at start-up and passed in.
- In `services/accounts/`, update the README in the same change as the behaviour.
- In `services/accounts/`, type-annotate every function signature.
- In `services/accounts/`, cancellation is cooperative; check for it in long loops.

## Search service (part 6)

- The Search team owns `services/search/`; ask before changing its public interface.
- In `services/search/`, do not add a third-party dependency without platform review.
- Search jobs run in the `search-batch` queue and must finish within 60 minutes.
- Search endpoints are versioned under `/v2/search`.
- In `services/search/`, do not remove or rename a response field without a deprecation window.
- In `services/search/`, use the shared fixtures before writing a new one.
- In `services/search/`, deleting data needs a retention review.
- In `services/search/`, do not branch on environment name in business code.

## Notifications service (part 6)

- In `services/notifications/`, responses are JSON objects, never bare arrays.
- Notifications jobs run in the `notifications-batch` queue and must finish within 10 minutes.
- Changes to `services/notifications/schema/` need a migration reviewed by the Notifications team.
- The Notifications team owns `services/notifications/`; ask before changing its public interface.
- In `services/notifications/`, every service exports request count, error count and latency.
- In `services/notifications/`, feature flags default to off and have an owner and an expiry.
- In `services/notifications/`, type-annotate every function signature.
- In `services/notifications/`, trace ids propagate through every outbound call.

## Reporting service (part 6)

- In `services/reporting/`, a request path allocates no more than it must; avoid copying large payloads.
- The Reporting team owns `services/reporting/`; ask before changing its public interface.
- Reporting endpoints are versioned under `/v2/reporting`.
- Changes to `services/reporting/schema/` need a migration reviewed by the Reporting team.
- In `services/reporting/`, do not abbreviate domain words: `customer`, not `cust`.
- In `services/reporting/`, no wildcard imports; absolute imports only.
- In `services/reporting/`, a request path allocates no more than it must; avoid copying large payloads.
- In `services/reporting/`, runbooks name the alert that leads to them.

## Returns service (part 6)

- The Returns team owns `services/returns/`; ask before changing its public interface.
- Returns jobs run in the `returns-batch` queue and must finish within 30 minutes.
- Changes to `services/returns/schema/` need a migration reviewed by the Returns team.
- The Returns on-call rota is the escalation path for `services/returns/` alerts.
- In `services/returns/`, a timeout is an error, not an empty result.
- In `services/returns/`, unknown configuration keys are an error.
- In `services/returns/`, retry only idempotent operations, at most three times, with jitter.
- In `services/returns/`, every log line for a request carries the `request_id` field.

## Pricing service (part 6)

- Pricing endpoints are versioned under `/v2/pricing`.
- The Pricing on-call rota is the escalation path for `services/pricing/` alerts.
- In `services/pricing/`, do not mark a test as skipped without a linked ticket.
- Changes to `services/pricing/schema/` need a migration reviewed by the Pricing team.
- In `services/pricing/`, decision records go in `docs/adr/` and are never edited after acceptance.
- In `services/pricing/`, responses are JSON objects, never bare arrays.
- In `services/pricing/`, boolean names read as questions: `is_active`, `has_stock`.
- In `services/pricing/`, remove a dependency in the same change that removes its last use.

## Partner API service (part 6)

- Partner API jobs run in the `partner-api-batch` queue and must finish within 10 minutes.
- In `services/partner-api/`, cancellation is cooperative; check for it in long loops.
- Partner API endpoints are versioned under `/v4/partner-api`.
- The Partner API on-call rota is the escalation path for `services/partner-api/` alerts.
- In `services/partner-api/`, commit subjects are imperative and under 72 characters.
- In `services/partner-api/`, set a timeout on every outbound call.
- In `services/partner-api/`, configuration is read once at start-up and passed in.
- In `services/partner-api/`, validate input at the boundary and trust nothing from a client.

## Back office service (part 6)

- Changes to `services/back-office/schema/` need a migration reviewed by the Back office team.
- Back office jobs run in the `back-office-batch` queue and must finish within 15 minutes.
- Back office endpoints are versioned under `/v4/back-office`.
- The Back office team owns `services/back-office/`; ask before changing its public interface.
- In `services/back-office/`, pin exact versions in lock files; ranges only in library manifests.
- In `services/back-office/`, do not document what the code already says.
- In `services/back-office/`, no commented-out code.
- In `services/back-office/`, feature flags default to off and have an owner and an expiry.

## Mobile gateway service (part 6)

- Changes to `services/mobile-gateway/schema/` need a migration reviewed by the Mobile gateway team.
- The Mobile gateway on-call rota is the escalation path for `services/mobile-gateway/` alerts.
- The Mobile gateway team owns `services/mobile-gateway/`; ask before changing its public interface.
- Mobile gateway jobs run in the `mobile-gateway-batch` queue and must finish within 15 minutes.
- In `services/mobile-gateway/`, no N+1 lookups in request paths; batch them.
- In `services/mobile-gateway/`, vendored code lives under `third_party/` and is never edited in place.
- In `services/mobile-gateway/`, every behaviour change comes with a test that fails without it.
- In `services/mobile-gateway/`, alerts page only for user-visible impact.

## Fraud service (part 6)

- Changes to `services/fraud/schema/` need a migration reviewed by the Fraud team.
- In `services/fraud/`, do not mark a test as skipped without a linked ticket.
- Fraud jobs run in the `fraud-batch` queue and must finish within 15 minutes.
- The Fraud on-call rota is the escalation path for `services/fraud/` alerts.
- In `services/fraud/`, update the README in the same change as the behaviour.
- In `services/fraud/`, licences other than MIT, BSD and Apache-2.0 need legal sign-off.
- In `services/fraud/`, do not document what the code already says.
- In `services/fraud/`, dashboards are code; do not hand-edit them.

## Loyalty service (part 6)

- The Loyalty on-call rota is the escalation path for `services/loyalty/` alerts.
- The Loyalty team owns `services/loyalty/`; ask before changing its public interface.
- Loyalty jobs run in the `loyalty-batch` queue and must finish within 10 minutes.
- Changes to `services/loyalty/schema/` need a migration reviewed by the Loyalty team.
- In `services/loyalty/`, avoid `utils` and `helpers` modules; name the module for what it holds.
- In `services/loyalty/`, do not catch `Exception` unless you re-raise or convert it at a boundary.
- In `services/loyalty/`, raise the narrowest exception that describes the failure.
- In `services/loyalty/`, log at `info` for state changes and `debug` for anything per-item in a loop.

## Tax service (part 6)

- Tax endpoints are versioned under `/v2/tax`.
- The Tax team owns `services/tax/`; ask before changing its public interface.
- In `services/tax/`, a request path allocates no more than it must; avoid copying large payloads.
- Tax jobs run in the `tax-batch` queue and must finish within 10 minutes.
- In `services/tax/`, set a timeout on every outbound call.
- In `services/tax/`, warnings are for things an operator should look at within a day.
- In `services/tax/`, streams over lists for anything unbounded.
- In `services/tax/`, do not abbreviate domain words: `customer`, not `cust`.

## Shipping rates service (part 6)

- Shipping rates endpoints are versioned under `/v1/shipping-rates`.
- The Shipping rates on-call rota is the escalation path for `services/shipping-rates/` alerts.
- In `services/shipping-rates/`, do not commit unless asked to.
- Changes to `services/shipping-rates/schema/` need a migration reviewed by the Shipping rates team.
- In `services/shipping-rates/`, decision records go in `docs/adr/` and are never edited after acceptance.
- In `services/shipping-rates/`, every behaviour change comes with a test that fails without it.
- In `services/shipping-rates/`, cancellation is cooperative; check for it in long loops.
- In `services/shipping-rates/`, log at `info` for state changes and `debug` for anything per-item in a loop.

## Reviews service (part 6)

- In `services/reviews/`, do not log and re-raise the same exception at two levels.
- Reviews jobs run in the `reviews-batch` queue and must finish within 30 minutes.
- Changes to `services/reviews/schema/` need a migration reviewed by the Reviews team.
- The Reviews team owns `services/reviews/`; ask before changing its public interface.
- In `services/reviews/`, measure before optimising, and keep the benchmark with the change.
- In `services/reviews/`, test names read as sentences about behaviour.
- In `services/reviews/`, use the shared fixtures before writing a new one.
- In `services/reviews/`, measure before optimising, and keep the benchmark with the change.

## Recommendations service (part 6)

- Recommendations endpoints are versioned under `/v4/recommendations`.
- The Recommendations on-call rota is the escalation path for `services/recommendations/` alerts.
- The Recommendations team owns `services/recommendations/`; ask before changing its public interface.
- In `services/recommendations/`, prefer message passing over locks.
- In `services/recommendations/`, add a column as nullable first; backfill; then tighten.
- In `services/recommendations/`, unrelated clean-ups go in their own change.
- In `services/recommendations/`, every service exports request count, error count and latency.
- In `services/recommendations/`, runbooks name the alert that leads to them.

## Imports service (part 6)

- Imports jobs run in the `imports-batch` queue and must finish within 10 minutes.
- Changes to `services/imports/schema/` need a migration reviewed by the Imports team.
- The Imports team owns `services/imports/`; ask before changing its public interface.
- In `services/imports/`, do not branch on environment name in business code.
- In `services/imports/`, decision records go in `docs/adr/` and are never edited after acceptance.
- In `services/imports/`, do not catch `Exception` unless you re-raise or convert it at a boundary.
- In `services/imports/`, commit subjects are imperative and under 72 characters.
- In `services/imports/`, responses are JSON objects, never bare arrays.

## Billing service (part 6)

- In `services/billing/`, no commented-out code.
- The Billing on-call rota is the escalation path for `services/billing/` alerts.
- The Billing team owns `services/billing/`; ask before changing its public interface.
- Billing endpoints are versioned under `/v3/billing`.
- In `services/billing/`, metric names are `service_noun_unit`.
- In `services/billing/`, do not add a third-party dependency without platform review.
- In `services/billing/`, a test asserts one behaviour; split it if the name needs 'and'.
- In `services/billing/`, streams over lists for anything unbounded.

## Payments service (part 7)

- The Payments on-call rota is the escalation path for `services/payments/` alerts.
- Payments jobs run in the `payments-batch` queue and must finish within 10 minutes.
- The Payments team owns `services/payments/`; ask before changing its public interface.
- In `services/payments/`, never log email addresses, card numbers or access tokens; log the id instead.
- In `services/payments/`, money is integer cents; never floats.
- In `services/payments/`, sampling rates are configuration, not constants.
- In `services/payments/`, defaults live in one place.
- In `services/payments/`, responses are JSON objects, never bare arrays.

## Catalogue service (part 7)

- Changes to `services/catalogue/schema/` need a migration reviewed by the Catalogue team.
- The Catalogue team owns `services/catalogue/`; ask before changing its public interface.
- The Catalogue on-call rota is the escalation path for `services/catalogue/` alerts.
- Catalogue jobs run in the `catalogue-batch` queue and must finish within 15 minutes.
- In `services/catalogue/`, uploaded file names are untrusted input.
- In `services/catalogue/`, money is integer cents; never floats.
- In `services/catalogue/`, do not catch `Exception` unless you re-raise or convert it at a boundary.
- In `services/catalogue/`, a timeout is an error, not an empty result.

## Fulfilment service (part 7)

- Changes to `services/fulfilment/schema/` need a migration reviewed by the Fulfilment team.
- Fulfilment jobs run in the `fulfilment-batch` queue and must finish within 5 minutes.
- Fulfilment endpoints are versioned under `/v3/fulfilment`.
- In `services/fulfilment/`, a timeout is an error, not an empty result.
- In `services/fulfilment/`, prefer the standard library when the difference is a few lines.
- In `services/fulfilment/`, a timeout is an error, not an empty result.
- In `services/fulfilment/`, type-annotate every function signature.
- In `services/fulfilment/`, background jobs are idempotent.

## Accounts service (part 7)

- Changes to `services/accounts/schema/` need a migration reviewed by the Accounts team.
- Accounts endpoints are versioned under `/v3/accounts`.
- In `services/accounts/`, no commented-out code.
- The Accounts on-call rota is the escalation path for `services/accounts/` alerts.
- In `services/accounts/`, lists have a documented, deterministic order.
- In `services/accounts/`, keep changes scoped to the request.
- In `services/accounts/`, tests drive public interfaces, not private attributes.
- In `services/accounts/`, a timeout is an error, not an empty result.

## Search service (part 7)

- In `services/search/`, unrelated clean-ups go in their own change.
- The Search team owns `services/search/`; ask before changing its public interface.
- Changes to `services/search/schema/` need a migration reviewed by the Search team.
- Search endpoints are versioned under `/v1/search`.
- In `services/search/`, use 400 for malformed input, 404 for unknown ids and 409 for conflicts with current state.
- In `services/search/`, remove a dependency in the same change that removes its last use.
- In `services/search/`, no commented-out code.
- In `services/search/`, every log line for a request carries the `request_id` field.

## Notifications service (part 7)

- The Notifications team owns `services/notifications/`; ask before changing its public interface.
- Notifications jobs run in the `notifications-batch` queue and must finish within 5 minutes.
- Notifications endpoints are versioned under `/v1/notifications`.
- The Notifications on-call rota is the escalation path for `services/notifications/` alerts.
- In `services/notifications/`, streams over lists for anything unbounded.
- In `services/notifications/`, type-annotate every function signature.
- In `services/notifications/`, never rewrite history on `main`.
- In `services/notifications/`, no sleeping in tests; inject a clock.

## Reporting service (part 7)

- In `services/reporting/`, measure before optimising, and keep the benchmark with the change.
- Reporting endpoints are versioned under `/v2/reporting`.
- Changes to `services/reporting/schema/` need a migration reviewed by the Reporting team.
- The Reporting team owns `services/reporting/`; ask before changing its public interface.
- In `services/reporting/`, a request path allocates no more than it must; avoid copying large payloads.
- In `services/reporting/`, do not mark a test as skipped without a linked ticket.
- In `services/reporting/`, use parameterised queries; never build SQL with string formatting.
- In `services/reporting/`, tests drive public interfaces, not private attributes.

## Returns service (part 7)

- Returns endpoints are versioned under `/v4/returns`.
- In `services/returns/`, a timeout is an error, not an empty result.
- The Returns on-call rota is the escalation path for `services/returns/` alerts.
- The Returns team owns `services/returns/`; ask before changing its public interface.
- In `services/returns/`, feature flags default to off and have an owner and an expiry.
- In `services/returns/`, avoid `utils` and `helpers` modules; name the module for what it holds.
- In `services/returns/`, prefer early returns over nested conditionals.
- In `services/returns/`, raise the narrowest exception that describes the failure.

## Pricing service (part 7)

- The Pricing team owns `services/pricing/`; ask before changing its public interface.
- The Pricing on-call rota is the escalation path for `services/pricing/` alerts.
- Pricing jobs run in the `pricing-batch` queue and must finish within 60 minutes.
- Changes to `services/pricing/schema/` need a migration reviewed by the Pricing team.
- In `services/pricing/`, cache only what you can invalidate.
- In `services/pricing/`, user-facing errors never include stack traces or internal ids.
- In `services/pricing/`, log at `info` for state changes and `debug` for anything per-item in a loop.
- In `services/pricing/`, error messages are lower case with no trailing full stop.

## Architecture

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

## Partner API service (part 7)

- Changes to `services/partner-api/schema/` need a migration reviewed by the Partner API team.
- The Partner API team owns `services/partner-api/`; ask before changing its public interface.
- Partner API jobs run in the `partner-api-batch` queue and must finish within 60 minutes.
- Partner API endpoints are versioned under `/v4/partner-api`.
- In `services/partner-api/`, money is integer cents; never floats.
- In `services/partner-api/`, do not document what the code already says.
- In `services/partner-api/`, tests drive public interfaces, not private attributes.
- In `services/partner-api/`, deleting data needs a retention review.

## Back office service (part 7)

- In `services/back-office/`, configuration is read once at start-up and passed in.
- Changes to `services/back-office/schema/` need a migration reviewed by the Back office team.
- Back office endpoints are versioned under `/v1/back-office`.
- Back office jobs run in the `back-office-batch` queue and must finish within 30 minutes.
- In `services/back-office/`, decision records go in `docs/adr/` and are never edited after acceptance.
- In `services/back-office/`, metric names are `service_noun_unit`.
- In `services/back-office/`, defaults live in one place.
- In `services/back-office/`, no N+1 lookups in request paths; batch them.

## Mobile gateway service (part 7)

- The Mobile gateway on-call rota is the escalation path for `services/mobile-gateway/` alerts.
- Mobile gateway jobs run in the `mobile-gateway-batch` queue and must finish within 5 minutes.
- Mobile gateway endpoints are versioned under `/v2/mobile-gateway`.
- Changes to `services/mobile-gateway/schema/` need a migration reviewed by the Mobile gateway team.
- In `services/mobile-gateway/`, cache only what you can invalidate.
- In `services/mobile-gateway/`, vendored code lives under `third_party/` and is never edited in place.
- In `services/mobile-gateway/`, update the README in the same change as the behaviour.
- In `services/mobile-gateway/`, prefer the standard library when the difference is a few lines.

## Fraud service (part 7)

- In `services/fraud/`, no commented-out code.
- The Fraud on-call rota is the escalation path for `services/fraud/` alerts.
- Changes to `services/fraud/schema/` need a migration reviewed by the Fraud team.
- Fraud endpoints are versioned under `/v3/fraud`.
- In `services/fraud/`, boolean names read as questions: `is_active`, `has_stock`.
- In `services/fraud/`, shared mutable state needs an owner; say who in a comment.
- In `services/fraud/`, shared mutable state needs an owner; say who in a comment.
- In `services/fraud/`, never rename a column in one step.

## Loyalty service (part 7)

- The Loyalty on-call rota is the escalation path for `services/loyalty/` alerts.
- The Loyalty team owns `services/loyalty/`; ask before changing its public interface.
- Loyalty jobs run in the `loyalty-batch` queue and must finish within 60 minutes.
- Loyalty endpoints are versioned under `/v2/loyalty`.
- In `services/loyalty/`, set a timeout on every outbound call.
- In `services/loyalty/`, lists have a documented, deterministic order.
- In `services/loyalty/`, pin exact versions in lock files; ranges only in library manifests.
- In `services/loyalty/`, do not remove or rename a response field without a deprecation window.

## Tax service (part 7)

- In `services/tax/`, lists have a documented, deterministic order.
- Tax endpoints are versioned under `/v1/tax`.
- Changes to `services/tax/schema/` need a migration reviewed by the Tax team.
- The Tax on-call rota is the escalation path for `services/tax/` alerts.
- In `services/tax/`, secrets come from the secret manager; never from the repository or an environment default.
- In `services/tax/`, no wildcard imports; absolute imports only.
- In `services/tax/`, warnings are for things an operator should look at within a day.
- In `services/tax/`, prefer early returns over nested conditionals.

## Shipping rates service (part 7)

- In `services/shipping-rates/`, do not add a third-party dependency without platform review.
- Shipping rates jobs run in the `shipping-rates-batch` queue and must finish within 15 minutes.
- The Shipping rates on-call rota is the escalation path for `services/shipping-rates/` alerts.
- Shipping rates endpoints are versioned under `/v4/shipping-rates`.
- In `services/shipping-rates/`, every table has a primary key and created/updated timestamps.
- In `services/shipping-rates/`, boolean names read as questions: `is_active`, `has_stock`.
- In `services/shipping-rates/`, thread pools are sized in configuration.
- In `services/shipping-rates/`, keep changes scoped to the request.

## Reviews service (part 7)

- Reviews jobs run in the `reviews-batch` queue and must finish within 10 minutes.
- The Reviews on-call rota is the escalation path for `services/reviews/` alerts.
- Changes to `services/reviews/schema/` need a migration reviewed by the Reviews team.
- The Reviews team owns `services/reviews/`; ask before changing its public interface.
- In `services/reviews/`, field names carry their unit: `total_cents`, `timeout_s`.
- In `services/reviews/`, user-facing errors never include stack traces or internal ids.
- In `services/reviews/`, never rewrite history on `main`.
- In `services/reviews/`, every service exports request count, error count and latency.

## Recommendations service (part 7)

- The Recommendations on-call rota is the escalation path for `services/recommendations/` alerts.
- In `services/recommendations/`, avoid `utils` and `helpers` modules; name the module for what it holds.
- Recommendations endpoints are versioned under `/v2/recommendations`.
- Changes to `services/recommendations/schema/` need a migration reviewed by the Recommendations team.
- In `services/recommendations/`, use the structured logger from `platform.logging`; never call `print` in service code.
- In `services/recommendations/`, timestamps are ISO 8601 in UTC.
- In `services/recommendations/`, do not disable TLS verification, even in tests.
- In `services/recommendations/`, shared mutable state needs an owner; say who in a comment.

## Imports service (part 7)

- Imports jobs run in the `imports-batch` queue and must finish within 15 minutes.
- Changes to `services/imports/schema/` need a migration reviewed by the Imports team.
- The Imports on-call rota is the escalation path for `services/imports/` alerts.
- Imports endpoints are versioned under `/v2/imports`.
- In `services/imports/`, prefer the standard library when the difference is a few lines.
- In `services/imports/`, shared mutable state needs an owner; say who in a comment.
- In `services/imports/`, every behaviour change comes with a test that fails without it.
- In `services/imports/`, pin exact versions in lock files; ranges only in library manifests.

## Billing service (part 7)

- The Billing on-call rota is the escalation path for `services/billing/` alerts.
- The Billing team owns `services/billing/`; ask before changing its public interface.
- Billing endpoints are versioned under `/v2/billing`.
- Changes to `services/billing/schema/` need a migration reviewed by the Billing team.
- In `services/billing/`, dashboards are code; do not hand-edit them.
- In `services/billing/`, no wildcard imports; absolute imports only.
- In `services/billing/`, do not catch `Exception` unless you re-raise or convert it at a boundary.
- In `services/billing/`, do not branch on environment name in business code.

## Payments service (part 8)

- In `services/payments/`, log at `info` for state changes and `debug` for anything per-item in a loop.
- The Payments team owns `services/payments/`; ask before changing its public interface.
- Payments jobs run in the `payments-batch` queue and must finish within 10 minutes.
- Changes to `services/payments/schema/` need a migration reviewed by the Payments team.
- In `services/payments/`, modules are lower_snake_case; classes are PascalCase; constants are UPPER_SNAKE_CASE.
- In `services/payments/`, raise the narrowest exception that describes the failure.
- In `services/payments/`, shared mutable state needs an owner; say who in a comment.
- In `services/payments/`, background jobs are idempotent.

## Catalogue service (part 8)

- The Catalogue team owns `services/catalogue/`; ask before changing its public interface.
- In `services/catalogue/`, alerts page only for user-visible impact.
- The Catalogue on-call rota is the escalation path for `services/catalogue/` alerts.
- Catalogue jobs run in the `catalogue-batch` queue and must finish within 10 minutes.
- In `services/catalogue/`, prefer message passing over locks.
- In `services/catalogue/`, do not log and re-raise the same exception at two levels.
- In `services/catalogue/`, tests drive public interfaces, not private attributes.
- In `services/catalogue/`, unknown configuration keys are an error.

## Fulfilment service (part 8)

- Fulfilment jobs run in the `fulfilment-batch` queue and must finish within 5 minutes.
- In `services/fulfilment/`, do not log and re-raise the same exception at two levels.
- Changes to `services/fulfilment/schema/` need a migration reviewed by the Fulfilment team.
- The Fulfilment on-call rota is the escalation path for `services/fulfilment/` alerts.
- In `services/fulfilment/`, do not commit unless asked to.
- In `services/fulfilment/`, never rewrite history on `main`.
- In `services/fulfilment/`, do not commit unless asked to.
- In `services/fulfilment/`, trace ids propagate through every outbound call.

## Accounts service (part 8)

- In `services/accounts/`, alerts page only for user-visible impact.
- Accounts jobs run in the `accounts-batch` queue and must finish within 5 minutes.
- Accounts endpoints are versioned under `/v2/accounts`.
- The Accounts team owns `services/accounts/`; ask before changing its public interface.
- In `services/accounts/`, a test asserts one behaviour; split it if the name needs 'and'.
- In `services/accounts/`, line length 110; double quotes for strings.
- In `services/accounts/`, measure before optimising, and keep the benchmark with the change.
- In `services/accounts/`, do not abbreviate domain words: `customer`, not `cust`.

## Search service (part 8)

- The Search on-call rota is the escalation path for `services/search/` alerts.
- Changes to `services/search/schema/` need a migration reviewed by the Search team.
- Search jobs run in the `search-batch` queue and must finish within 5 minutes.
- The Search team owns `services/search/`; ask before changing its public interface.
- In `services/search/`, defaults live in one place.
- In `services/search/`, metric names are `service_noun_unit`.
- In `services/search/`, set a timeout on every outbound call.
- In `services/search/`, use the shared fixtures before writing a new one.

## Notifications service (part 8)

- The Notifications team owns `services/notifications/`; ask before changing its public interface.
- Notifications jobs run in the `notifications-batch` queue and must finish within 10 minutes.
- Notifications endpoints are versioned under `/v3/notifications`.
- The Notifications on-call rota is the escalation path for `services/notifications/` alerts.
- In `services/notifications/`, dataclasses in domain packages are frozen.
- In `services/notifications/`, every service exports request count, error count and latency.
- In `services/notifications/`, lists have a documented, deterministic order.
- In `services/notifications/`, validate input at the boundary and trust nothing from a client.

## Reporting service (part 8)

- In `services/reporting/`, diagrams live next to the code they describe.
- The Reporting on-call rota is the escalation path for `services/reporting/` alerts.
- Changes to `services/reporting/schema/` need a migration reviewed by the Reporting team.
- Reporting endpoints are versioned under `/v2/reporting`.
- In `services/reporting/`, do not remove or rename a response field without a deprecation window.
- In `services/reporting/`, never rename a column in one step.
- In `services/reporting/`, every service exports request count, error count and latency.
- In `services/reporting/`, shared mutable state needs an owner; say who in a comment.

## Returns service (part 8)

- In `services/returns/`, user-facing errors never include stack traces or internal ids.
- Changes to `services/returns/schema/` need a migration reviewed by the Returns team.
- The Returns team owns `services/returns/`; ask before changing its public interface.
- Returns jobs run in the `returns-batch` queue and must finish within 30 minutes.
- In `services/returns/`, dashboards are code; do not hand-edit them.
- In `services/returns/`, do not disable TLS verification, even in tests.
- In `services/returns/`, do not log and re-raise the same exception at two levels.
- In `services/returns/`, every behaviour change comes with a test that fails without it.

## Pricing service (part 8)

- Pricing endpoints are versioned under `/v3/pricing`.
- In `services/pricing/`, use the structured logger from `platform.logging`; never call `print` in service code.
- Changes to `services/pricing/schema/` need a migration reviewed by the Pricing team.
- The Pricing team owns `services/pricing/`; ask before changing its public interface.
- In `services/pricing/`, feature flags default to off and have an owner and an expiry.
- In `services/pricing/`, deleting data needs a retention review.
- In `services/pricing/`, alerts page only for user-visible impact.
- In `services/pricing/`, never hold a lock across I/O.

## Partner API service (part 8)

- Partner API endpoints are versioned under `/v2/partner-api`.
- The Partner API on-call rota is the escalation path for `services/partner-api/` alerts.
- The Partner API team owns `services/partner-api/`; ask before changing its public interface.
- Changes to `services/partner-api/schema/` need a migration reviewed by the Partner API team.
- In `services/partner-api/`, pin exact versions in lock files; ranges only in library manifests.
- In `services/partner-api/`, responses are JSON objects, never bare arrays.
- In `services/partner-api/`, background jobs are idempotent.
- In `services/partner-api/`, shared mutable state needs an owner; say who in a comment.

## Back office service (part 8)

- Back office jobs run in the `back-office-batch` queue and must finish within 60 minutes.
- The Back office on-call rota is the escalation path for `services/back-office/` alerts.
- The Back office team owns `services/back-office/`; ask before changing its public interface.
- Changes to `services/back-office/schema/` need a migration reviewed by the Back office team.
- In `services/back-office/`, every table has a primary key and created/updated timestamps.
- In `services/back-office/`, use parameterised queries; never build SQL with string formatting.
- In `services/back-office/`, measure before optimising, and keep the benchmark with the change.
- In `services/back-office/`, streams over lists for anything unbounded.

## Mobile gateway service (part 8)

- Changes to `services/mobile-gateway/schema/` need a migration reviewed by the Mobile gateway team.
- The Mobile gateway team owns `services/mobile-gateway/`; ask before changing its public interface.
- Mobile gateway endpoints are versioned under `/v2/mobile-gateway`.
- In `services/mobile-gateway/`, remove a dependency in the same change that removes its last use.
- In `services/mobile-gateway/`, do not mark a test as skipped without a linked ticket.
- In `services/mobile-gateway/`, measure before optimising, and keep the benchmark with the change.
- In `services/mobile-gateway/`, use the shared fixtures before writing a new one.
- In `services/mobile-gateway/`, configuration is read once at start-up and passed in.

## Fraud service (part 8)

- Fraud jobs run in the `fraud-batch` queue and must finish within 5 minutes.
- Fraud endpoints are versioned under `/v1/fraud`.
- In `services/fraud/`, no commented-out code.
- The Fraud team owns `services/fraud/`; ask before changing its public interface.
- In `services/fraud/`, if a request is ambiguous, choose the reading closest to existing behaviour and say so.
- In `services/fraud/`, lists have a documented, deterministic order.
- In `services/fraud/`, if a request is ambiguous, choose the reading closest to existing behaviour and say so.
- In `services/fraud/`, pagination uses opaque cursors, not page numbers.

## Loyalty service (part 8)

- Loyalty endpoints are versioned under `/v4/loyalty`.
- Loyalty jobs run in the `loyalty-batch` queue and must finish within 5 minutes.
- The Loyalty team owns `services/loyalty/`; ask before changing its public interface.
- The Loyalty on-call rota is the escalation path for `services/loyalty/` alerts.
- In `services/loyalty/`, if a request is ambiguous, choose the reading closest to existing behaviour and say so.
- In `services/loyalty/`, no commented-out code.
- In `services/loyalty/`, commit subjects are imperative and under 72 characters.
- In `services/loyalty/`, pagination uses opaque cursors, not page numbers.

## Tax service (part 8)

- Changes to `services/tax/schema/` need a migration reviewed by the Tax team.
- The Tax on-call rota is the escalation path for `services/tax/` alerts.
- The Tax team owns `services/tax/`; ask before changing its public interface.
- In `services/tax/`, never hold a lock across I/O.
- In `services/tax/`, a request path allocates no more than it must; avoid copying large payloads.
- In `services/tax/`, no sleeping in tests; inject a clock.
- In `services/tax/`, diagrams live next to the code they describe.
- In `services/tax/`, pin exact versions in lock files; ranges only in library manifests.

## Shipping rates service (part 8)

- Shipping rates endpoints are versioned under `/v1/shipping-rates`.
- Changes to `services/shipping-rates/schema/` need a migration reviewed by the Shipping rates team.
- In `services/shipping-rates/`, cancellation is cooperative; check for it in long loops.
- The Shipping rates on-call rota is the escalation path for `services/shipping-rates/` alerts.
- In `services/shipping-rates/`, no environment lookups below the composition root.
- In `services/shipping-rates/`, money is integer cents; never floats.
- In `services/shipping-rates/`, a request path allocates no more than it must; avoid copying large payloads.
- In `services/shipping-rates/`, add a column as nullable first; backfill; then tighten.

## Reviews service (part 8)

- The Reviews team owns `services/reviews/`; ask before changing its public interface.
- In `services/reviews/`, warnings are for things an operator should look at within a day.
- Reviews jobs run in the `reviews-batch` queue and must finish within 60 minutes.
- Reviews endpoints are versioned under `/v4/reviews`.
- In `services/reviews/`, timestamps are ISO 8601 in UTC.
- In `services/reviews/`, never rename a column in one step.
- In `services/reviews/`, do not remove or rename a response field without a deprecation window.
- In `services/reviews/`, warnings are for things an operator should look at within a day.

## Recommendations service (part 8)

- Changes to `services/recommendations/schema/` need a migration reviewed by the Recommendations team.
- Recommendations endpoints are versioned under `/v4/recommendations`.
- The Recommendations on-call rota is the escalation path for `services/recommendations/` alerts.
- The Recommendations team owns `services/recommendations/`; ask before changing its public interface.
- In `services/recommendations/`, never rename a column in one step.
- In `services/recommendations/`, never rename a column in one step.
- In `services/recommendations/`, cache only what you can invalidate.
- In `services/recommendations/`, diagrams live next to the code they describe.

## Imports service (part 8)

- In `services/imports/`, error messages are lower case with no trailing full stop.
- The Imports on-call rota is the escalation path for `services/imports/` alerts.
- Imports endpoints are versioned under `/v2/imports`.
- Imports jobs run in the `imports-batch` queue and must finish within 10 minutes.
- In `services/imports/`, metric names are `service_noun_unit`.
- In `services/imports/`, tests drive public interfaces, not private attributes.
- In `services/imports/`, unrelated clean-ups go in their own change.
- In `services/imports/`, do not log and re-raise the same exception at two levels.

## Billing service (part 8)

- In `services/billing/`, error messages are lower case with no trailing full stop.
- Billing jobs run in the `billing-batch` queue and must finish within 15 minutes.
- Billing endpoints are versioned under `/v3/billing`.
- Changes to `services/billing/schema/` need a migration reviewed by the Billing team.
- In `services/billing/`, thread pools are sized in configuration.
- In `services/billing/`, uploaded file names are untrusted input.
- In `services/billing/`, no commented-out code.
- In `services/billing/`, timestamps are ISO 8601 in UTC.

## Payments service (part 9)

- Changes to `services/payments/schema/` need a migration reviewed by the Payments team.
- The Payments on-call rota is the escalation path for `services/payments/` alerts.
- The Payments team owns `services/payments/`; ask before changing its public interface.
- Payments jobs run in the `payments-batch` queue and must finish within 10 minutes.
- In `services/payments/`, runbooks name the alert that leads to them.
- In `services/payments/`, metric names are `service_noun_unit`.
- In `services/payments/`, a test asserts one behaviour; split it if the name needs 'and'.
- In `services/payments/`, pagination uses opaque cursors, not page numbers.

## Catalogue service (part 9)

- The Catalogue team owns `services/catalogue/`; ask before changing its public interface.
- Catalogue endpoints are versioned under `/v4/catalogue`.
- The Catalogue on-call rota is the escalation path for `services/catalogue/` alerts.
- Changes to `services/catalogue/schema/` need a migration reviewed by the Catalogue team.
- In `services/catalogue/`, user-facing errors never include stack traces or internal ids.
- In `services/catalogue/`, avoid `utils` and `helpers` modules; name the module for what it holds.
- In `services/catalogue/`, background jobs are idempotent.
- In `services/catalogue/`, no N+1 lookups in request paths; batch them.

## Fulfilment service (part 9)

- Fulfilment jobs run in the `fulfilment-batch` queue and must finish within 30 minutes.
- In `services/fulfilment/`, pin exact versions in lock files; ranges only in library manifests.
- Fulfilment endpoints are versioned under `/v3/fulfilment`.
- The Fulfilment team owns `services/fulfilment/`; ask before changing its public interface.
- In `services/fulfilment/`, streams over lists for anything unbounded.
- In `services/fulfilment/`, log at `info` for state changes and `debug` for anything per-item in a loop.
- In `services/fulfilment/`, streams over lists for anything unbounded.
- In `services/fulfilment/`, feature flags default to off and have an owner and an expiry.

## Accounts service (part 9)

- Accounts endpoints are versioned under `/v3/accounts`.
- The Accounts team owns `services/accounts/`; ask before changing its public interface.
- Changes to `services/accounts/schema/` need a migration reviewed by the Accounts team.
- The Accounts on-call rota is the escalation path for `services/accounts/` alerts.
- In `services/accounts/`, retry only idempotent operations, at most three times, with jitter.
- In `services/accounts/`, keep changes scoped to the request.
- In `services/accounts/`, update the README in the same change as the behaviour.
- In `services/accounts/`, add a column as nullable first; backfill; then tighten.

## Search service (part 9)

- Search endpoints are versioned under `/v4/search`.
- The Search team owns `services/search/`; ask before changing its public interface.
- In `services/search/`, avoid `utils` and `helpers` modules; name the module for what it holds.
- The Search on-call rota is the escalation path for `services/search/` alerts.
- In `services/search/`, log at `info` for state changes and `debug` for anything per-item in a loop.
- In `services/search/`, warnings are for things an operator should look at within a day.
- In `services/search/`, diagrams live next to the code they describe.
- In `services/search/`, no N+1 lookups in request paths; batch them.

## Notifications service (part 9)

- The Notifications on-call rota is the escalation path for `services/notifications/` alerts.
- In `services/notifications/`, boolean names read as questions: `is_active`, `has_stock`.
- The Notifications team owns `services/notifications/`; ask before changing its public interface.
- Notifications jobs run in the `notifications-batch` queue and must finish within 5 minutes.
- In `services/notifications/`, every service exports request count, error count and latency.
- In `services/notifications/`, use the shared fixtures before writing a new one.
- In `services/notifications/`, unknown configuration keys are an error.
- In `services/notifications/`, sampling rates are configuration, not constants.

## Reporting service (part 9)

- Reporting jobs run in the `reporting-batch` queue and must finish within 10 minutes.
- Changes to `services/reporting/schema/` need a migration reviewed by the Reporting team.
- The Reporting on-call rota is the escalation path for `services/reporting/` alerts.
- The Reporting team owns `services/reporting/`; ask before changing its public interface.
- In `services/reporting/`, do not log and re-raise the same exception at two levels.
- In `services/reporting/`, money is integer cents; never floats.
- In `services/reporting/`, never hold a lock across I/O.
- In `services/reporting/`, do not branch on environment name in business code.

## Returns service (part 9)

- The Returns team owns `services/returns/`; ask before changing its public interface.
- In `services/returns/`, do not mark a test as skipped without a linked ticket.
- Returns jobs run in the `returns-batch` queue and must finish within 5 minutes.
- The Returns on-call rota is the escalation path for `services/returns/` alerts.
- In `services/returns/`, user-facing errors never include stack traces or internal ids.
- In `services/returns/`, defaults live in one place.
- In `services/returns/`, runbooks name the alert that leads to them.
- In `services/returns/`, shared mutable state needs an owner; say who in a comment.

## Pricing service (part 9)

- Pricing jobs run in the `pricing-batch` queue and must finish within 10 minutes.
- The Pricing team owns `services/pricing/`; ask before changing its public interface.
- In `services/pricing/`, do not abbreviate domain words: `customer`, not `cust`.
- Changes to `services/pricing/schema/` need a migration reviewed by the Pricing team.
- In `services/pricing/`, a timeout is an error, not an empty result.
- In `services/pricing/`, a timeout is an error, not an empty result.
- In `services/pricing/`, use parameterised queries; never build SQL with string formatting.
- In `services/pricing/`, every behaviour change comes with a test that fails without it.

## Partner API service (part 9)

- Changes to `services/partner-api/schema/` need a migration reviewed by the Partner API team.
- Partner API endpoints are versioned under `/v2/partner-api`.
- In `services/partner-api/`, add a column as nullable first; backfill; then tighten.
- The Partner API team owns `services/partner-api/`; ask before changing its public interface.
- In `services/partner-api/`, never log email addresses, card numbers or access tokens; log the id instead.
- In `services/partner-api/`, prefer message passing over locks.
- In `services/partner-api/`, do not catch `Exception` unless you re-raise or convert it at a boundary.
- In `services/partner-api/`, secrets come from the secret manager; never from the repository or an environment default.

## Back office service (part 9)

- The Back office on-call rota is the escalation path for `services/back-office/` alerts.
- In `services/back-office/`, migrations are forwards-only and safe to run twice.
- Back office endpoints are versioned under `/v2/back-office`.
- Changes to `services/back-office/schema/` need a migration reviewed by the Back office team.
- In `services/back-office/`, use 400 for malformed input, 404 for unknown ids and 409 for conflicts with current state.
- In `services/back-office/`, diagrams live next to the code they describe.
- In `services/back-office/`, licences other than MIT, BSD and Apache-2.0 need legal sign-off.
- In `services/back-office/`, use the structured logger from `platform.logging`; never call `print` in service code.

## Mobile gateway service (part 9)

- The Mobile gateway team owns `services/mobile-gateway/`; ask before changing its public interface.
- Changes to `services/mobile-gateway/schema/` need a migration reviewed by the Mobile gateway team.
- In `services/mobile-gateway/`, error messages are lower case with no trailing full stop.
- The Mobile gateway on-call rota is the escalation path for `services/mobile-gateway/` alerts.
- In `services/mobile-gateway/`, raise the narrowest exception that describes the failure.
- In `services/mobile-gateway/`, public functions have a one-line docstring in the imperative mood.
- In `services/mobile-gateway/`, remove a dependency in the same change that removes its last use.
- In `services/mobile-gateway/`, do not remove or rename a response field without a deprecation window.

## Fraud service (part 9)

- In `services/fraud/`, background jobs are idempotent.
- Changes to `services/fraud/schema/` need a migration reviewed by the Fraud team.
- Fraud jobs run in the `fraud-batch` queue and must finish within 5 minutes.
- Fraud endpoints are versioned under `/v2/fraud`.
- In `services/fraud/`, no environment lookups below the composition root.
- In `services/fraud/`, trace ids propagate through every outbound call.
- In `services/fraud/`, use parameterised queries; never build SQL with string formatting.
- In `services/fraud/`, error messages are lower case with no trailing full stop.

## Loyalty service (part 9)

- Loyalty endpoints are versioned under `/v4/loyalty`.
- The Loyalty team owns `services/loyalty/`; ask before changing its public interface.
- In `services/loyalty/`, a test asserts one behaviour; split it if the name needs 'and'.
- The Loyalty on-call rota is the escalation path for `services/loyalty/` alerts.
- In `services/loyalty/`, thread pools are sized in configuration.
- In `services/loyalty/`, modules are lower_snake_case; classes are PascalCase; constants are UPPER_SNAKE_CASE.
- In `services/loyalty/`, uploaded file names are untrusted input.
- In `services/loyalty/`, add a column as nullable first; backfill; then tighten.

## Tax service (part 9)

- In `services/tax/`, no environment lookups below the composition root.
- Tax endpoints are versioned under `/v1/tax`.
- Changes to `services/tax/schema/` need a migration reviewed by the Tax team.
- The Tax on-call rota is the escalation path for `services/tax/` alerts.
- In `services/tax/`, commit subjects are imperative and under 72 characters.
- In `services/tax/`, add a column as nullable first; backfill; then tighten.
- In `services/tax/`, every service exports request count, error count and latency.
- In `services/tax/`, error messages are lower case with no trailing full stop.

## Shipping rates service (part 9)

- Shipping rates endpoints are versioned under `/v2/shipping-rates`.
- In `services/shipping-rates/`, set a timeout on every outbound call.
- The Shipping rates on-call rota is the escalation path for `services/shipping-rates/` alerts.
- Changes to `services/shipping-rates/schema/` need a migration reviewed by the Shipping rates team.
- In `services/shipping-rates/`, use the shared fixtures before writing a new one.
- In `services/shipping-rates/`, every log line for a request carries the `request_id` field.
- In `services/shipping-rates/`, vendored code lives under `third_party/` and is never edited in place.
- In `services/shipping-rates/`, responses are JSON objects, never bare arrays.

## Reviews service (part 9)

- The Reviews team owns `services/reviews/`; ask before changing its public interface.
- The Reviews on-call rota is the escalation path for `services/reviews/` alerts.
- Changes to `services/reviews/schema/` need a migration reviewed by the Reviews team.
- Reviews endpoints are versioned under `/v4/reviews`.
- In `services/reviews/`, do not commit unless asked to.
- In `services/reviews/`, field names carry their unit: `total_cents`, `timeout_s`.
- In `services/reviews/`, a test asserts one behaviour; split it if the name needs 'and'.
- In `services/reviews/`, no wildcard imports; absolute imports only.

## Recommendations service (part 9)

- In `services/recommendations/`, no wildcard imports; absolute imports only.
- The Recommendations team owns `services/recommendations/`; ask before changing its public interface.
- Recommendations endpoints are versioned under `/v2/recommendations`.
- The Recommendations on-call rota is the escalation path for `services/recommendations/` alerts.
- In `services/recommendations/`, do not catch `Exception` unless you re-raise or convert it at a boundary.
- In `services/recommendations/`, do not catch `Exception` unless you re-raise or convert it at a boundary.
- In `services/recommendations/`, use the shared fixtures before writing a new one.
- In `services/recommendations/`, modules are lower_snake_case; classes are PascalCase; constants are UPPER_SNAKE_CASE.

## Imports service (part 9)

- Imports endpoints are versioned under `/v1/imports`.
- Imports jobs run in the `imports-batch` queue and must finish within 5 minutes.
- Changes to `services/imports/schema/` need a migration reviewed by the Imports team.
- The Imports on-call rota is the escalation path for `services/imports/` alerts.
- In `services/imports/`, commit subjects are imperative and under 72 characters.
- In `services/imports/`, if a request is ambiguous, choose the reading closest to existing behaviour and say so.
- In `services/imports/`, every log line for a request carries the `request_id` field.
- In `services/imports/`, diagrams live next to the code they describe.

## Billing service (part 9)

- The Billing on-call rota is the escalation path for `services/billing/` alerts.
- Changes to `services/billing/schema/` need a migration reviewed by the Billing team.
- In `services/billing/`, shared mutable state needs an owner; say who in a comment.
- Billing endpoints are versioned under `/v4/billing`.
- In `services/billing/`, line length 110; double quotes for strings.
- In `services/billing/`, validate input at the boundary and trust nothing from a client.
- In `services/billing/`, do not add a third-party dependency without platform review.
- In `services/billing/`, alerts page only for user-visible impact.

## Payments service (part 10)

- Payments jobs run in the `payments-batch` queue and must finish within 10 minutes.
- The Payments team owns `services/payments/`; ask before changing its public interface.
- In `services/payments/`, if a request is ambiguous, choose the reading closest to existing behaviour and say so.
- Changes to `services/payments/schema/` need a migration reviewed by the Payments team.
- In `services/payments/`, keep changes scoped to the request.
- In `services/payments/`, no commented-out code.
- In `services/payments/`, uploaded file names are untrusted input.
- In `services/payments/`, a test asserts one behaviour; split it if the name needs 'and'.

## Catalogue service (part 10)

- The Catalogue on-call rota is the escalation path for `services/catalogue/` alerts.
- The Catalogue team owns `services/catalogue/`; ask before changing its public interface.
- Catalogue endpoints are versioned under `/v4/catalogue`.
- Changes to `services/catalogue/schema/` need a migration reviewed by the Catalogue team.
- In `services/catalogue/`, do not remove or rename a response field without a deprecation window.
- In `services/catalogue/`, field names carry their unit: `total_cents`, `timeout_s`.
- In `services/catalogue/`, tests drive public interfaces, not private attributes.
- In `services/catalogue/`, avoid `utils` and `helpers` modules; name the module for what it holds.

## Fulfilment service (part 10)

- In `services/fulfilment/`, retry only idempotent operations, at most three times, with jitter.
- The Fulfilment on-call rota is the escalation path for `services/fulfilment/` alerts.
- Fulfilment jobs run in the `fulfilment-batch` queue and must finish within 5 minutes.
- The Fulfilment team owns `services/fulfilment/`; ask before changing its public interface.
- In `services/fulfilment/`, never log email addresses, card numbers or access tokens; log the id instead.
- In `services/fulfilment/`, validate input at the boundary and trust nothing from a client.
- In `services/fulfilment/`, every table has a primary key and created/updated timestamps.
- In `services/fulfilment/`, migrations are forwards-only and safe to run twice.

## Accounts service (part 10)

- Changes to `services/accounts/schema/` need a migration reviewed by the Accounts team.
- The Accounts team owns `services/accounts/`; ask before changing its public interface.
- Accounts jobs run in the `accounts-batch` queue and must finish within 60 minutes.
- The Accounts on-call rota is the escalation path for `services/accounts/` alerts.
- In `services/accounts/`, defaults live in one place.
- In `services/accounts/`, a request path allocates no more than it must; avoid copying large payloads.
- In `services/accounts/`, thread pools are sized in configuration.
- In `services/accounts/`, background jobs are idempotent.

## Search service (part 10)

- The Search on-call rota is the escalation path for `services/search/` alerts.
- Search endpoints are versioned under `/v3/search`.
- The Search team owns `services/search/`; ask before changing its public interface.
- In `services/search/`, do not document what the code already says.
- In `services/search/`, avoid `utils` and `helpers` modules; name the module for what it holds.
- In `services/search/`, a request path allocates no more than it must; avoid copying large payloads.
- In `services/search/`, a request path allocates no more than it must; avoid copying large payloads.
- In `services/search/`, do not branch on environment name in business code.

## Notifications service (part 10)

- The Notifications team owns `services/notifications/`; ask before changing its public interface.
- The Notifications on-call rota is the escalation path for `services/notifications/` alerts.
- In `services/notifications/`, metric names are `service_noun_unit`.
- Notifications jobs run in the `notifications-batch` queue and must finish within 10 minutes.
- In `services/notifications/`, commit subjects are imperative and under 72 characters.
- In `services/notifications/`, never rename a column in one step.
- In `services/notifications/`, feature flags default to off and have an owner and an expiry.
- In `services/notifications/`, defaults live in one place.

## Reporting service (part 10)

- The Reporting on-call rota is the escalation path for `services/reporting/` alerts.
- Changes to `services/reporting/schema/` need a migration reviewed by the Reporting team.
- In `services/reporting/`, warnings are for things an operator should look at within a day.
- Reporting jobs run in the `reporting-batch` queue and must finish within 60 minutes.
- In `services/reporting/`, pagination uses opaque cursors, not page numbers.
- In `services/reporting/`, use the structured logger from `platform.logging`; never call `print` in service code.
- In `services/reporting/`, thread pools are sized in configuration.
- In `services/reporting/`, a test asserts one behaviour; split it if the name needs 'and'.

## Returns service (part 10)

- Returns endpoints are versioned under `/v1/returns`.
- In `services/returns/`, pin exact versions in lock files; ranges only in library manifests.
- The Returns team owns `services/returns/`; ask before changing its public interface.
- Returns jobs run in the `returns-batch` queue and must finish within 15 minutes.
- In `services/returns/`, every table has a primary key and created/updated timestamps.
- In `services/returns/`, measure before optimising, and keep the benchmark with the change.
- In `services/returns/`, do not remove or rename a response field without a deprecation window.
- In `services/returns/`, a timeout is an error, not an empty result.

## Pricing service (part 10)

- The Pricing team owns `services/pricing/`; ask before changing its public interface.
- Pricing endpoints are versioned under `/v2/pricing`.
- In `services/pricing/`, sampling rates are configuration, not constants.
- Changes to `services/pricing/schema/` need a migration reviewed by the Pricing team.
- In `services/pricing/`, secrets come from the secret manager; never from the repository or an environment default.
- In `services/pricing/`, authorisation checks live next to the action they protect.
- In `services/pricing/`, modules are lower_snake_case; classes are PascalCase; constants are UPPER_SNAKE_CASE.
- In `services/pricing/`, tests drive public interfaces, not private attributes.

## Partner API service (part 10)

- Partner API jobs run in the `partner-api-batch` queue and must finish within 10 minutes.
- In `services/partner-api/`, log at `info` for state changes and `debug` for anything per-item in a loop.
- The Partner API team owns `services/partner-api/`; ask before changing its public interface.
- Partner API endpoints are versioned under `/v3/partner-api`.
- In `services/partner-api/`, type-annotate every function signature.
- In `services/partner-api/`, every log line for a request carries the `request_id` field.
- In `services/partner-api/`, vendored code lives under `third_party/` and is never edited in place.
- In `services/partner-api/`, do not branch on environment name in business code.

## Back office service (part 10)

- In `services/back-office/`, shared mutable state needs an owner; say who in a comment.
- The Back office on-call rota is the escalation path for `services/back-office/` alerts.
- Changes to `services/back-office/schema/` need a migration reviewed by the Back office team.
- Back office jobs run in the `back-office-batch` queue and must finish within 60 minutes.
- In `services/back-office/`, authorisation checks live next to the action they protect.
- In `services/back-office/`, do not disable TLS verification, even in tests.
- In `services/back-office/`, raise the narrowest exception that describes the failure.
- In `services/back-office/`, responses are JSON objects, never bare arrays.

## Mobile gateway service (part 10)

- The Mobile gateway on-call rota is the escalation path for `services/mobile-gateway/` alerts.
- In `services/mobile-gateway/`, unrelated clean-ups go in their own change.
- Mobile gateway jobs run in the `mobile-gateway-batch` queue and must finish within 5 minutes.
- The Mobile gateway team owns `services/mobile-gateway/`; ask before changing its public interface.
- In `services/mobile-gateway/`, add a column as nullable first; backfill; then tighten.
- In `services/mobile-gateway/`, error messages are lower case with no trailing full stop.
- In `services/mobile-gateway/`, vendored code lives under `third_party/` and is never edited in place.
- In `services/mobile-gateway/`, commit subjects are imperative and under 72 characters.

## Fraud service (part 10)

- Changes to `services/fraud/schema/` need a migration reviewed by the Fraud team.
- Fraud jobs run in the `fraud-batch` queue and must finish within 10 minutes.
- Fraud endpoints are versioned under `/v2/fraud`.
- The Fraud on-call rota is the escalation path for `services/fraud/` alerts.
- In `services/fraud/`, shared mutable state needs an owner; say who in a comment.
- In `services/fraud/`, prefer early returns over nested conditionals.
- In `services/fraud/`, never rename a column in one step.
- In `services/fraud/`, do not log and re-raise the same exception at two levels.

## Loyalty service (part 10)

- Changes to `services/loyalty/schema/` need a migration reviewed by the Loyalty team.
- The Loyalty team owns `services/loyalty/`; ask before changing its public interface.
- The Loyalty on-call rota is the escalation path for `services/loyalty/` alerts.
- In `services/loyalty/`, field names carry their unit: `total_cents`, `timeout_s`.
- In `services/loyalty/`, decision records go in `docs/adr/` and are never edited after acceptance.
- In `services/loyalty/`, do not remove or rename a response field without a deprecation window.
- In `services/loyalty/`, vendored code lives under `third_party/` and is never edited in place.
- In `services/loyalty/`, validate input at the boundary and trust nothing from a client.

## Tax service (part 10)

- The Tax on-call rota is the escalation path for `services/tax/` alerts.
- In `services/tax/`, if a request is ambiguous, choose the reading closest to existing behaviour and say so.
- Changes to `services/tax/schema/` need a migration reviewed by the Tax team.
- Tax endpoints are versioned under `/v2/tax`.
- In `services/tax/`, uploaded file names are untrusted input.
- In `services/tax/`, no N+1 lookups in request paths; batch them.
- In `services/tax/`, do not catch `Exception` unless you re-raise or convert it at a boundary.
- In `services/tax/`, metric names are `service_noun_unit`.

## Shipping rates service (part 10)

- Shipping rates endpoints are versioned under `/v2/shipping-rates`.
- Changes to `services/shipping-rates/schema/` need a migration reviewed by the Shipping rates team.
- The Shipping rates team owns `services/shipping-rates/`; ask before changing its public interface.
- Shipping rates jobs run in the `shipping-rates-batch` queue and must finish within 5 minutes.
- In `services/shipping-rates/`, licences other than MIT, BSD and Apache-2.0 need legal sign-off.
- In `services/shipping-rates/`, do not branch on environment name in business code.
- In `services/shipping-rates/`, use the shared fixtures before writing a new one.
- In `services/shipping-rates/`, lists have a documented, deterministic order.

## Reviews service (part 10)

- Reviews jobs run in the `reviews-batch` queue and must finish within 5 minutes.
- Reviews endpoints are versioned under `/v2/reviews`.
- In `services/reviews/`, avoid `utils` and `helpers` modules; name the module for what it holds.
- The Reviews team owns `services/reviews/`; ask before changing its public interface.
- In `services/reviews/`, dataclasses in domain packages are frozen.
- In `services/reviews/`, a request path allocates no more than it must; avoid copying large payloads.
- In `services/reviews/`, modules are lower_snake_case; classes are PascalCase; constants are UPPER_SNAKE_CASE.
- In `services/reviews/`, every log line for a request carries the `request_id` field.

## Recommendations service (part 10)

- Recommendations endpoints are versioned under `/v2/recommendations`.
- The Recommendations team owns `services/recommendations/`; ask before changing its public interface.
- Changes to `services/recommendations/schema/` need a migration reviewed by the Recommendations team.
- In `services/recommendations/`, do not branch on environment name in business code.
- In `services/recommendations/`, cache only what you can invalidate.
- In `services/recommendations/`, metric names are `service_noun_unit`.
- In `services/recommendations/`, dashboards are code; do not hand-edit them.
- In `services/recommendations/`, line length 110; double quotes for strings.

## Imports service (part 10)

- The Imports on-call rota is the escalation path for `services/imports/` alerts.
- In `services/imports/`, unknown configuration keys are an error.
- Changes to `services/imports/schema/` need a migration reviewed by the Imports team.
- The Imports team owns `services/imports/`; ask before changing its public interface.
- In `services/imports/`, do not mark a test as skipped without a linked ticket.
- In `services/imports/`, streams over lists for anything unbounded.
- In `services/imports/`, sampling rates are configuration, not constants.
- In `services/imports/`, a request path allocates no more than it must; avoid copying large payloads.

## Billing service (part 10)

- Billing jobs run in the `billing-batch` queue and must finish within 15 minutes.
- The Billing team owns `services/billing/`; ask before changing its public interface.
- The Billing on-call rota is the escalation path for `services/billing/` alerts.
- Changes to `services/billing/schema/` need a migration reviewed by the Billing team.
- In `services/billing/`, use the shared fixtures before writing a new one.
- In `services/billing/`, unknown configuration keys are an error.
- In `services/billing/`, a request path allocates no more than it must; avoid copying large payloads.
- In `services/billing/`, prefer the standard library when the difference is a few lines.

## Payments service (part 11)

- The Payments on-call rota is the escalation path for `services/payments/` alerts.
- In `services/payments/`, tests drive public interfaces, not private attributes.
- Payments jobs run in the `payments-batch` queue and must finish within 60 minutes.
- The Payments team owns `services/payments/`; ask before changing its public interface.
- In `services/payments/`, timestamps are ISO 8601 in UTC.
- In `services/payments/`, remove a dependency in the same change that removes its last use.
- In `services/payments/`, a timeout is an error, not an empty result.
- In `services/payments/`, use the shared fixtures before writing a new one.

## Catalogue service (part 11)

- Catalogue endpoints are versioned under `/v2/catalogue`.
- In `services/catalogue/`, alerts page only for user-visible impact.
- Changes to `services/catalogue/schema/` need a migration reviewed by the Catalogue team.
- The Catalogue team owns `services/catalogue/`; ask before changing its public interface.
- In `services/catalogue/`, use the structured logger from `platform.logging`; never call `print` in service code.
- In `services/catalogue/`, error messages are lower case with no trailing full stop.
- In `services/catalogue/`, do not disable TLS verification, even in tests.
- In `services/catalogue/`, do not branch on environment name in business code.

## Fulfilment service (part 11)

- Fulfilment endpoints are versioned under `/v2/fulfilment`.
- Fulfilment jobs run in the `fulfilment-batch` queue and must finish within 15 minutes.
- In `services/fulfilment/`, authorisation checks live next to the action they protect.
- The Fulfilment team owns `services/fulfilment/`; ask before changing its public interface.
- In `services/fulfilment/`, do not add a third-party dependency without platform review.
- In `services/fulfilment/`, unrelated clean-ups go in their own change.
- In `services/fulfilment/`, every table has a primary key and created/updated timestamps.
- In `services/fulfilment/`, dashboards are code; do not hand-edit them.

## Accounts service (part 11)

- Accounts endpoints are versioned under `/v2/accounts`.
- Accounts jobs run in the `accounts-batch` queue and must finish within 5 minutes.
- In `services/accounts/`, streams over lists for anything unbounded.
- Changes to `services/accounts/schema/` need a migration reviewed by the Accounts team.
- In `services/accounts/`, type-annotate every function signature.
- In `services/accounts/`, cancellation is cooperative; check for it in long loops.
- In `services/accounts/`, dataclasses in domain packages are frozen.
- In `services/accounts/`, commit subjects are imperative and under 72 characters.

## Search service (part 11)

- The Search on-call rota is the escalation path for `services/search/` alerts.
- Search jobs run in the `search-batch` queue and must finish within 10 minutes.
- Changes to `services/search/schema/` need a migration reviewed by the Search team.
- Search endpoints are versioned under `/v2/search`.
- In `services/search/`, no sleeping in tests; inject a clock.
- In `services/search/`, validate input at the boundary and trust nothing from a client.
- In `services/search/`, every log line for a request carries the `request_id` field.
- In `services/search/`, no wildcard imports; absolute imports only.

## Notifications service (part 11)

- Notifications endpoints are versioned under `/v3/notifications`.
- Changes to `services/notifications/schema/` need a migration reviewed by the Notifications team.
- The Notifications team owns `services/notifications/`; ask before changing its public interface.
- In `services/notifications/`, set a timeout on every outbound call.
- In `services/notifications/`, a request path allocates no more than it must; avoid copying large payloads.
- In `services/notifications/`, measure before optimising, and keep the benchmark with the change.
- In `services/notifications/`, no sleeping in tests; inject a clock.
- In `services/notifications/`, user-facing errors never include stack traces or internal ids.

## Reporting service (part 11)

- The Reporting team owns `services/reporting/`; ask before changing its public interface.
- In `services/reporting/`, prefer early returns over nested conditionals.
- Changes to `services/reporting/schema/` need a migration reviewed by the Reporting team.
- Reporting jobs run in the `reporting-batch` queue and must finish within 10 minutes.
- In `services/reporting/`, prefer early returns over nested conditionals.
- In `services/reporting/`, never rewrite history on `main`.
- In `services/reporting/`, a timeout is an error, not an empty result.
- In `services/reporting/`, test names read as sentences about behaviour.

## Returns service (part 11)

- The Returns team owns `services/returns/`; ask before changing its public interface.
- The Returns on-call rota is the escalation path for `services/returns/` alerts.
- In `services/returns/`, dataclasses in domain packages are frozen.
- Changes to `services/returns/schema/` need a migration reviewed by the Returns team.
- In `services/returns/`, streams over lists for anything unbounded.
- In `services/returns/`, field names carry their unit: `total_cents`, `timeout_s`.
- In `services/returns/`, never rename a column in one step.
- In `services/returns/`, line length 110; double quotes for strings.

## Pricing service (part 11)

- The Pricing team owns `services/pricing/`; ask before changing its public interface.
- In `services/pricing/`, line length 110; double quotes for strings.
- Changes to `services/pricing/schema/` need a migration reviewed by the Pricing team.
- The Pricing on-call rota is the escalation path for `services/pricing/` alerts.
- In `services/pricing/`, do not branch on environment name in business code.
- In `services/pricing/`, if a request is ambiguous, choose the reading closest to existing behaviour and say so.
- In `services/pricing/`, runbooks name the alert that leads to them.
- In `services/pricing/`, a test asserts one behaviour; split it if the name needs 'and'.

## Partner API service (part 11)

- The Partner API on-call rota is the escalation path for `services/partner-api/` alerts.
- The Partner API team owns `services/partner-api/`; ask before changing its public interface.
- Changes to `services/partner-api/schema/` need a migration reviewed by the Partner API team.
- In `services/partner-api/`, migrations are forwards-only and safe to run twice.
- In `services/partner-api/`, remove a dependency in the same change that removes its last use.
- In `services/partner-api/`, cancellation is cooperative; check for it in long loops.
- In `services/partner-api/`, defaults live in one place.
- In `services/partner-api/`, no N+1 lookups in request paths; batch them.

## Back office service (part 11)

- Changes to `services/back-office/schema/` need a migration reviewed by the Back office team.
- Back office jobs run in the `back-office-batch` queue and must finish within 60 minutes.
- Back office endpoints are versioned under `/v3/back-office`.
- The Back office team owns `services/back-office/`; ask before changing its public interface.
- In `services/back-office/`, a timeout is an error, not an empty result.
- In `services/back-office/`, migrations are forwards-only and safe to run twice.
- In `services/back-office/`, sampling rates are configuration, not constants.
- In `services/back-office/`, lists have a documented, deterministic order.

## Mobile gateway service (part 11)

- The Mobile gateway on-call rota is the escalation path for `services/mobile-gateway/` alerts.
- Mobile gateway endpoints are versioned under `/v3/mobile-gateway`.
- The Mobile gateway team owns `services/mobile-gateway/`; ask before changing its public interface.
- Mobile gateway jobs run in the `mobile-gateway-batch` queue and must finish within 60 minutes.
- In `services/mobile-gateway/`, cancellation is cooperative; check for it in long loops.
- In `services/mobile-gateway/`, defaults live in one place.
- In `services/mobile-gateway/`, background jobs are idempotent.
- In `services/mobile-gateway/`, warnings are for things an operator should look at within a day.

## Fraud service (part 11)

- The Fraud team owns `services/fraud/`; ask before changing its public interface.
- Changes to `services/fraud/schema/` need a migration reviewed by the Fraud team.
- In `services/fraud/`, commit subjects are imperative and under 72 characters.
- Fraud jobs run in the `fraud-batch` queue and must finish within 10 minutes.
- In `services/fraud/`, dataclasses in domain packages are frozen.
- In `services/fraud/`, secrets come from the secret manager; never from the repository or an environment default.
- In `services/fraud/`, do not mark a test as skipped without a linked ticket.
- In `services/fraud/`, defaults live in one place.

## Loyalty service (part 11)

- Loyalty endpoints are versioned under `/v4/loyalty`.
- The Loyalty on-call rota is the escalation path for `services/loyalty/` alerts.
- In `services/loyalty/`, vendored code lives under `third_party/` and is never edited in place.
- The Loyalty team owns `services/loyalty/`; ask before changing its public interface.
- In `services/loyalty/`, diagrams live next to the code they describe.
- In `services/loyalty/`, modules are lower_snake_case; classes are PascalCase; constants are UPPER_SNAKE_CASE.
- In `services/loyalty/`, do not disable TLS verification, even in tests.
- In `services/loyalty/`, licences other than MIT, BSD and Apache-2.0 need legal sign-off.

## Tax service (part 11)

- Changes to `services/tax/schema/` need a migration reviewed by the Tax team.
- In `services/tax/`, do not disable TLS verification, even in tests.
- Tax endpoints are versioned under `/v4/tax`.
- The Tax team owns `services/tax/`; ask before changing its public interface.
- In `services/tax/`, set a timeout on every outbound call.
- In `services/tax/`, never rewrite history on `main`.
- In `services/tax/`, no N+1 lookups in request paths; batch them.
- In `services/tax/`, migrations are forwards-only and safe to run twice.

## Shipping rates service (part 11)

- Shipping rates jobs run in the `shipping-rates-batch` queue and must finish within 15 minutes.
- Changes to `services/shipping-rates/schema/` need a migration reviewed by the Shipping rates team.
- Shipping rates endpoints are versioned under `/v1/shipping-rates`.
- In `services/shipping-rates/`, no commented-out code.
- In `services/shipping-rates/`, background jobs are idempotent.
- In `services/shipping-rates/`, do not branch on environment name in business code.
- In `services/shipping-rates/`, prefer message passing over locks.
- In `services/shipping-rates/`, do not add a third-party dependency without platform review.

## Reviews service (part 11)

- Reviews endpoints are versioned under `/v2/reviews`.
- In `services/reviews/`, user-facing errors never include stack traces or internal ids.
- The Reviews team owns `services/reviews/`; ask before changing its public interface.
- Changes to `services/reviews/schema/` need a migration reviewed by the Reviews team.
- In `services/reviews/`, modules are lower_snake_case; classes are PascalCase; constants are UPPER_SNAKE_CASE.
- In `services/reviews/`, prefer message passing over locks.
- In `services/reviews/`, raise the narrowest exception that describes the failure.
- In `services/reviews/`, timestamps are ISO 8601 in UTC.

## Recommendations service (part 11)

- The Recommendations on-call rota is the escalation path for `services/recommendations/` alerts.
- The Recommendations team owns `services/recommendations/`; ask before changing its public interface.
- Recommendations jobs run in the `recommendations-batch` queue and must finish within 10 minutes.
- In `services/recommendations/`, field names carry their unit: `total_cents`, `timeout_s`.
- In `services/recommendations/`, if a request is ambiguous, choose the reading closest to existing behaviour and say so.
- In `services/recommendations/`, money is integer cents; never floats.
- In `services/recommendations/`, trace ids propagate through every outbound call.
- In `services/recommendations/`, pagination uses opaque cursors, not page numbers.

## Imports service (part 11)

- Imports endpoints are versioned under `/v4/imports`.
- The Imports team owns `services/imports/`; ask before changing its public interface.
- Changes to `services/imports/schema/` need a migration reviewed by the Imports team.
- Imports jobs run in the `imports-batch` queue and must finish within 10 minutes.
- In `services/imports/`, no sleeping in tests; inject a clock.
- In `services/imports/`, do not abbreviate domain words: `customer`, not `cust`.
- In `services/imports/`, authorisation checks live next to the action they protect.
- In `services/imports/`, never rewrite history on `main`.

## Billing service (part 11)

- Changes to `services/billing/schema/` need a migration reviewed by the Billing team.
- The Billing team owns `services/billing/`; ask before changing its public interface.
- The Billing on-call rota is the escalation path for `services/billing/` alerts.
- Billing jobs run in the `billing-batch` queue and must finish within 30 minutes.
- In `services/billing/`, measure before optimising, and keep the benchmark with the change.
- In `services/billing/`, vendored code lives under `third_party/` and is never edited in place.
- In `services/billing/`, unrelated clean-ups go in their own change.
- In `services/billing/`, sampling rates are configuration, not constants.

## Payments service (part 12)

- The Payments team owns `services/payments/`; ask before changing its public interface.
- Payments endpoints are versioned under `/v3/payments`.
- The Payments on-call rota is the escalation path for `services/payments/` alerts.
- In `services/payments/`, background jobs are idempotent.
- In `services/payments/`, authorisation checks live next to the action they protect.
- In `services/payments/`, boolean names read as questions: `is_active`, `has_stock`.
- In `services/payments/`, dashboards are code; do not hand-edit them.
- In `services/payments/`, field names carry their unit: `total_cents`, `timeout_s`.

## Catalogue service (part 12)

- Catalogue endpoints are versioned under `/v1/catalogue`.
- Changes to `services/catalogue/schema/` need a migration reviewed by the Catalogue team.
- The Catalogue team owns `services/catalogue/`; ask before changing its public interface.
- In `services/catalogue/`, do not remove or rename a response field without a deprecation window.
- In `services/catalogue/`, responses are JSON objects, never bare arrays.
- In `services/catalogue/`, thread pools are sized in configuration.
- In `services/catalogue/`, modules are lower_snake_case; classes are PascalCase; constants are UPPER_SNAKE_CASE.
- In `services/catalogue/`, a timeout is an error, not an empty result.

## Fulfilment service (part 12)

- Fulfilment endpoints are versioned under `/v3/fulfilment`.
- In `services/fulfilment/`, do not log and re-raise the same exception at two levels.
- The Fulfilment on-call rota is the escalation path for `services/fulfilment/` alerts.
- Fulfilment jobs run in the `fulfilment-batch` queue and must finish within 5 minutes.
- In `services/fulfilment/`, do not catch `Exception` unless you re-raise or convert it at a boundary.
- In `services/fulfilment/`, feature flags default to off and have an owner and an expiry.
- In `services/fulfilment/`, unrelated clean-ups go in their own change.
- In `services/fulfilment/`, do not add a third-party dependency without platform review.

## Accounts service (part 12)

- Changes to `services/accounts/schema/` need a migration reviewed by the Accounts team.
- Accounts jobs run in the `accounts-batch` queue and must finish within 30 minutes.
- Accounts endpoints are versioned under `/v2/accounts`.
- The Accounts team owns `services/accounts/`; ask before changing its public interface.
- In `services/accounts/`, warnings are for things an operator should look at within a day.
- In `services/accounts/`, uploaded file names are untrusted input.
- In `services/accounts/`, vendored code lives under `third_party/` and is never edited in place.
- In `services/accounts/`, use the shared fixtures before writing a new one.

## Search service (part 12)

- The Search on-call rota is the escalation path for `services/search/` alerts.
- Search endpoints are versioned under `/v1/search`.
- In `services/search/`, prefer early returns over nested conditionals.
- Search jobs run in the `search-batch` queue and must finish within 5 minutes.
- In `services/search/`, do not abbreviate domain words: `customer`, not `cust`.
- In `services/search/`, prefer message passing over locks.
- In `services/search/`, tests drive public interfaces, not private attributes.
- In `services/search/`, retry only idempotent operations, at most three times, with jitter.

## Working

- Run the tests with `.venv/bin/python -m pytest -q tests`.
- Keep the existing behaviour and tests passing, and add tests for new
  behaviour.
- Do not edit this file.
