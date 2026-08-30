# Backlog: `market-model` and `eurooffice` are missing from the prod monitoring inventory

**Status**: Backlog — found during `064-llm-router` implementation, not yet fixed.
**Source**: `specs/064-llm-router/research.md` § D-107.

## The gap

`ansible/inventories/prod/hosts.yml`'s `services` group lists hosts only up to
`financial-scenario` (`192.168.1.217`). **`market-model` (`.218`) and `eurooffice` (`.219`) are not
present**, even though both are deployed, live services with `monitoring_contract` blocks defined in
their respective `host_vars` files.

The monitoring templates (`prometheus.yml.j2`, `service_alerts.yml.j2`,
`provision_dashboards.yml`) all iterate `groups['services']` / `groups['all']` via `hostvars` to
build scrape targets, liveness probes and alert rules. A host absent from the inventory
contributes **nothing** to any of them — no scrape target, no liveness probe, no alert rule, no
dashboard — regardless of how complete its own `monitoring_contract` is.

## Likely impact

`market-model` and `eurooffice` are probably running **unmonitored in prod right now**: no
Prometheus scrape, no blackbox liveness probe, no alert if either goes down. This has not been
independently confirmed against a live `prometheus.yml` — that's the first step below.

## Why this wasn't fixed in `064-llm-router`

`064` added its own `llm-router` inventory entry (a one-line fix, in scope for that feature) and
in the course of that work also fixed a related-but-distinct latent bug in
`provision_dashboards.yml` (hyphenated host names vs. underscored role directories — see
`research.md` D-110). Repairing the *pre-existing* omission of `market-model` and `eurooffice`
themselves was explicitly out of scope: it's unrelated to what `064` was building, and deserves its
own verification (confirming nothing currently *depends* on their absence, e.g. no alert was
deliberately suppressed) rather than a drive-by two-line diff.

## Suggested fix

1. Confirm via a live `prometheus.yml` / Grafana check whether `market-model` and `eurooffice` are
   actually unmonitored today (don't assume — verify).
2. Add both hosts to `ansible/inventories/prod/hosts.yml`'s `services` group, matching the
   existing entries' shape (`ansible_host`, `ansible_user: root`).
3. Re-run the monitoring role and confirm scrape targets, liveness probes, and alert rules appear
   for both services.
4. Audit whether any other deployed service has the same gap — this backlog item only names the
   two found by inspection during `064`; a full audit wasn't performed.

## Dependencies

None. Independent, low-risk, doc-and-inventory-only change once verified.
