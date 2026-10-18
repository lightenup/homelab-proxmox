# Backlog: `market-model` and `eurooffice` are missing from the prod monitoring inventory

**Status**: **RESOLVED 2026-10-18** — both hosts added to the prod inventory. See
[Resolution](#resolution-2026-10-18) at the end.
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

## Resolution (2026-10-18)

Found again while investigating a burst of `EndpointDown` alerts: the `eurooffice` liveness job
and `EuroOfficeDown` rule were missing from the live rule set.

1. **Verified on live Prometheus, not assumed.** Over 30 days there was no `up{job="eurooffice"}`,
   no `market-model-api` probe, no `EuroOfficeDown`/`MarketModelDown` rule, and `.218`/`.219` were
   absent from the `node-exporter` job. The only coverage either service had was the shared
   `blackbox-https` probe (`EndpointDown`), which comes from `caddy_services`, not the inventory.
   Nothing depended on their absence; no alert had been deliberately suppressed.
2. **Root cause, more precisely than above:** per-service deploys build their own single-host
   inventory, so both services deploy and run fine. Only the `monitoring` deploy layers in the
   committed `inventories/prod/hosts.yml` (`scripts/lab/pve-service-deploy`) to see every other
   host's `monitoring_contract`, so a host missing from that file is invisible to monitoring alone.
3. **Fix:** both added to the `services` group (`market-model` `192.168.1.218`, `eurooffice`
   `192.168.1.219`). Before adding them, checked that nothing would fire on the first scrape:
   node_exporter answers on `:9100` on both, `/healthz` and `/healthcheck` return 200, and
   memory (12% / 19%) and root disk (51% / 64%) are well under the 85% thresholds.
4. **Audit of all 12 running LXCs** (`pct list`) against the inventory: no other gap.
   `homeassistant` (LXC 104, `.212`) is also absent and should stay so for now. The LXC is
   empty (no containers, no node_exporter), and `host_vars` says "Service not yet installed".
   Adding it would page `ServiceDown`, because the `node-exporter` job includes any host whose
   `monitoring_contract` is not explicitly disabled. Add it when the service is installed.
