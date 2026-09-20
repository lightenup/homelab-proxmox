# Contract — Monitoring for Hermes

**Feature**: `065-hermes-ai-workspace` | Satisfies FR-017, FR-018

Declared in `ansible/host_vars/hermes.yml` as a `monitoring_contract`, following every other
service in the estate.

## Signals

| Signal | Source | Severity | Why |
|---|---|---|---|
| Hermes unreachable | blackbox probe on the public hostname | **critical** | The owner's only route in is gone. This is also the signal the front-page card reads (FR-017). |
| Backup stale | backup artifact age exceeds its schedule | **warning** | A backup that stopped is invisible until a restore is attempted, which is the worst moment to discover it. |
| Local tier unavailable | inherited from `064` | *(none here)* | Already alerted by `064`. Duplicating it would page twice for one event. |

## Deliberately not alerted

- **Individual model request failures.** When the inference host sleeps, every request fails; that
  is designed behaviour (FR-009), not an incident. `064`'s canary already covers total
  unavailability.
- **A scheduled run failing.** Visible to the owner in the application (SC-010). Paging for it
  would train the operator to ignore the channel, and the cause is almost always the inference host
  being asleep — which is normal.

## The front-page indicator

FR-017 requires the card's state to come from the estate's existing mechanism: the landing page
queries `/api/status`, which proxies a `probe_success` query, and each card carries a `data-probe`
matching the probe's `instance` label.

Two ways exist to put a card on that page, and this feature needs the **first**:

- `caddy_services` with `user_facing: true` — creates a public route **and** a card. Hermes is meant
  to be clicked through to, so this is correct.
- `caddy_landing_links` — a card with no route. This is what `llm-router` uses, because it must
  *not* be routable. Wrong for Hermes.

## Deployment note — inherited scar tissue

**The monitoring contract renders only on the prod path.** `pve-service-deploy` layers
`inventories/${ENVIRONMENT}/hosts.yml` for the monitoring service, and the lab inventory holds one
host and no services. A lab-path monitoring deploy therefore renders an empty configuration **over
the live one**.

This is not hypothetical: it happened on 2026-09-20 and removed all 16 scrape jobs and 5 alert
groups from production Prometheus, with the deploy reporting success. Two guards now refuse it, and
[backlog `072`](../../../docs/backlog/072-lab-monitoring-deploy-wipes-prod.md) has the detail.
Deploy monitoring changes for this feature through the **prod** path.

## Reverse proxy

`caddy_services` supports `proxy_timeout`. It **must** be set long enough to clear FR-021's
twenty-minute ceiling. The default will truncate a long local generation, and the symptom — a
response that dies partway through — looks like a model problem rather than a proxy one.
