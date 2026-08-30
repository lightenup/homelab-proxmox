# Contract — Monitoring

**Feature**: `064-llm-router` | Satisfies FR-009, SC-005, SC-012

Declared in `ansible/host_vars/llm-router.yml`; consumed by `monitoring_stack` through `hostvars`,
the same mechanism `market-model` uses.

> **Precondition (D-107):** the host must be present in `ansible/inventories/prod/hosts.yml`. The
> monitoring templates iterate `groups['all']` / `groups['services']`; a host absent from the
> inventory contributes no scrape target, no probe and no alert, and the contract below silently
> does nothing.

## Shape

```yaml
healthcheck_url:
  scheme: http
  port: 4000
  path: /health/readiness
healthcheck_profile: lan
healthcheck_expect_status: 200

monitoring_contract:
  enabled: true
  scrape_targets:
    - job_name: "llm-router"
      port: 4000
      path: /metrics
  liveness_targets:
    - job_name: "llm-router-readiness"
      url: "http://192.168.1.220:4000/health/readiness"
      module: http_2xx
  alert_rules:
    - alert: LlmRouterDown                # severity: critical
    - alert: LlmRouterLocalTierDown       # severity: info
    - alert: LlmRouterAllBackendsFailing  # severity: critical
    - alert: LlmRouterCanaryFailing       # severity: critical
    - alert: LlmRouterBudgetCapExhausted  # severity: critical
```

## Signals and severities

| Signal | Source | Severity | Why |
|---|---|---|---|
| Gateway down or database unreachable | blackbox on `/health/readiness` | **critical** | Every client is refused. FR-009 requires the gateway being down to alert. |
| Local tier (Mac) unavailable | `litellm_deployment_state` for the Ollama deployment | **info** | FR-009 requires this to be informational, not critical — the Mac is a discount, not a dependency. Alerting critically on an intermittent-by-design backend would train the operator to ignore the channel. |
| **All backends failing, under traffic** | failure ratio across all deployments > 90% over 10m | **critical** | FR-018. The gateway is alive and the database is fine, but nothing can be served. |
| **All backends failing, no traffic** | synthetic canary request fails | **critical** | FR-018, SC-013. The failure-rate signal is silent with no clients calling — which is exactly how this trap goes unnoticed until someone tries to use the gateway. |
| Gateway-wide budget cap exhausted | `litellm_remaining_team_budget_metric` at/near zero | **critical** | SC-012. This refuses every client at once, so it is an availability event, not just a spend one. |
| Per-client budget breach | spend metric per key alias | (dashboard only) | SC-010 — visible and attributable, but one client hitting its own cap is working as designed, not an incident. |

The severity split is the substance of this contract. A downed Mac and a downed gateway look similar
in a naive dashboard and could not be more different operationally.

**Why two all-backends signals rather than one.** `/health/readiness` returns 200 while every
deployment is dead — it only checks the database. The failure-rate signal closes that, but only while
clients are calling; a homelab gateway can sit idle for hours, so a traffic-derived alert can stay
green through a total outage. The canary is the half that makes SC-013 testable: it is a real
low-cadence request against the cheapest alias, so it is **client traffic, not a health probe**, and
therefore does not count against SC-011's probe budget. While the Mac is up it is served locally at
zero marginal cost.

## Grafana panels (SC-005)

- Per-alias request volume — by `requested_model`.
- Per-deployment success/failure — `litellm_deployment_success_responses` /
  `_failure_responses` by `model_info.id`, which is what makes SC-002 ("`hermes-fast` demonstrably
  served locally") checkable rather than assumed.
- Metered spend per alias — `litellm_spend_metric`, **or** the `LiteLLM_SpendLogs` fallback
  (research D-105).
- Local-tier availability timeline — makes the intermittent Mac's duty cycle visible, which is what
  tells the operator whether retiering to a bigger local model is worth it.

## Scrape-config note (D-105 — resolved by live testing)

Live-tested against the pinned `v1.83.3-stable` image: `/metrics` is **open by default** (not
bearer-gated, contrary to the docs' prose), and enabling `require_auth_for_metrics_endpoint: true`
reproducibly hangs the master key against this endpoint specifically (confirmed: the same key works
instantly on every other admin endpoint). No working authenticated path was found for this pinned
version, so the endpoint ships at its default (open), documented explicitly in `config.yaml.j2`
rather than relying on silent default behaviour — `/metrics` publishes spend and deployment
topology, not credentials, and FR-008 already accepts LAN reachability for the gateway itself
(D-108). An optional, default-off `authorization` block was still added to the shared
`prometheus.yml.j2` (byte-identical output for every other service's contract) so a future service
that does need scrape auth has it available. Revisit `require_auth_for_metrics_endpoint` on the next
LiteLLM version bump. `/metrics` also redirects to `/metrics/` (307) — the scrape target's `path` is
set to `/metrics/` directly to skip the extra hop.
