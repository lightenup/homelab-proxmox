# Phase 1 — Data Model: LLM Router

**Feature**: `064-llm-router` | **Date**: 2026-08-29

No application database is designed here — LiteLLM owns its own schema. What this document models is
the **configuration data the role consumes** (the entities from [spec.md § Key Entities](./spec.md))
and the validation rules the preflight enforces.

---

## Entity: Intent Alias

The stable, client-facing name for a class of work. The only model identifier a client knows.

| Field | Type | Rules |
|---|---|---|
| `name` | string | One of `hermes-fast`, `hermes-balanced`, `hermes-deep`. Lowercase, hyphenated. Immutable — renaming one is a breaking change for every client, which is what FR-003 exists to prevent. |
| `deployments` | ordered list | ≥1 `Deployment`. Order is preference: index 0 is preferred, later entries are standby. |
| `fallback_to` | string \| null | The alias to escalate to when every own deployment is in cooldown. |
| `context_window_fallback_to` | string \| null | The alias to escalate to when input exceeds this alias's context window (FR-006). |

**Relationships**: an Alias has many Deployments (ordered); an Alias may point at one other Alias for
each of the two fallback kinds. The fallback graph MUST be acyclic and MUST terminate at an alias
whose deployments are all always-available (i.e. `hermes-deep`).

**Validation** (preflight):
- Every `fallback_to` / `context_window_fallback_to` names a defined alias.
- The fallback graph has no cycle.
- `hermes-deep` has `fallback_to: null` — it is the terminus.
- At least one alias exists.

---

## Entity: Deployment

One concrete backend a request can be served by.

| Field | Type | Rules |
|---|---|---|
| `id` | string | Unique across all aliases. Used as the LiteLLM `model_name` suffix and as the Prometheus label that makes SC-002 checkable. |
| `tier` | enum | `local` \| `aggregator` \| `frontier`. Drives health-check scoping (D-101) and cost expectations. |
| `provider_model` | string | LiteLLM provider-qualified ID, e.g. `ollama_chat/<model>`, `openrouter/<model>`, `anthropic/claude-sonnet-5`. |
| `api_base` | string \| null | Required for `local` (the Mac's MagicDNS name); null for hosted tiers. |
| `api_key_env` | string \| null | Name of the environment variable holding the credential — **never the credential itself** (FR-007, Constitution II). Null for `local` (unauthenticated over the tailnet). |
| `context_window` | integer | Used to decide context-window escalation. |
| `health_checked` | bool | True only for `tier: local`. False for metered tiers so probes never bill (FR-005). |

**State** (owned by LiteLLM at runtime, not by config): `healthy` → `cooling_down` (after
`allowed_fails` failures) → `healthy` (after `cooldown_time` elapses and a probe passes). A
deployment in `cooling_down` is skipped without being attempted — Acceptance Scenario 1.3.

**Validation** (preflight):
- Exactly one deployment per alias has `tier: local` at most.
- `tier: local` ⇒ `api_base` is set, is a MagicDNS name (`*.ts.net`), and is **not** an IP literal
  (FR-013 — an IP here silently reintroduces the LAN dependency the feature exists to remove).
- `tier != local` ⇒ `api_key_env` is set and the named variable is non-empty in the environment.
- `provider_model` is non-empty and contains a `/`.

---

## Entity: Client Key

The credential a homelab consumer presents; the unit budgets and attribution hang off (FR-015).

| Field | Type | Rules |
|---|---|---|
| `alias` | string | Human-readable consumer name (`hermes`, `agent-foo`). Becomes the LiteLLM key alias and the Prometheus label. |
| `key_env` | string | Vault-sourced env var holding the key value. Never in git. |
| `max_budget` | decimal | Per-client spend cap in USD (FR-010). |
| `budget_duration` | string | Reset window, e.g. `30d`. |
| `rpm_limit` | integer \| null | Optional per-client rate limit. |

**Validation**: `alias` unique; `max_budget` > 0; the sum of all `max_budget` values MUST be **less
than** the gateway-wide cap, with headroom — see the Gateway Budget rule below.

---

## Entity: Gateway Budget

The backstop cap across all clients (FR-010, SC-012).

| Field | Type | Rules |
|---|---|---|
| `max_budget` | decimal | Gateway-wide USD cap. |
| `budget_duration` | string | Reset window; MUST match the client budget window so the two are comparable. |

**Validation**: `max_budget` > `sum(client.max_budget)`. This is the check that keeps the cap from
becoming a self-inflicted outage — if the cap is below the sum of what clients are individually
permitted, normal usage trips it and every client is refused at once. The preflight fails on this
rather than warning, because the failure mode is a silent homelab-wide outage.

---

## Entity: Alias Mapping (the aggregate)

The single artefact an operator edits to retier (FR-003, SC-003). Lives in
`ansible/group_vars/services/vars.yml`; templated into `config.yaml` by the role.

```yaml
llm_router_aliases:
  - name: hermes-fast
    fallback_to: hermes-balanced
    context_window_fallback_to: hermes-deep
    deployments:
      - {id: fast-local,  tier: local,      provider_model: "ollama_chat/<model>", api_base: "http://<mac>.<tailnet>.ts.net:11434", context_window: 32768, health_checked: true}
      - {id: fast-hosted, tier: aggregator, provider_model: "openrouter/<model>",  api_key_env: OPENROUTER_API_KEY, context_window: 32768, health_checked: false}
  - name: hermes-balanced
    fallback_to: hermes-deep
    ...
  - name: hermes-deep
    fallback_to: null
    deployments:
      - {id: deep-frontier, tier: frontier, provider_model: "anthropic/claude-sonnet-5", api_key_env: ANTHROPIC_API_KEY, context_window: 1000000, health_checked: false}
```

**The SC-003 property this shape buys**: retiering `hermes-balanced` from a hosted model to a 70B
local one when the Mac reaches 128 GB is an edit to one `deployments` list — no role logic, no client
change. The role template iterates this structure and never branches on alias names.

---

## Entity: Monitoring Contract

Declared in `ansible/host_vars/llm-router.yml`; consumed by `monitoring_stack` via `hostvars`.
Shape and semantics in [contracts/monitoring.md](./contracts/monitoring.md).

---

## What is deliberately NOT modelled

- **Prompt and response bodies** — FR-012 forbids logging them by default. No entity, no retention
  policy, no storage sizing for them.
- **User accounts** — there are none. A Client Key is the only identity.
- **LiteLLM's internal schema** (`LiteLLM_SpendLogs`, key tables) — owned and migrated by the image.
  The role never writes to it directly; D-105's fallback only ever *reads* `LiteLLM_SpendLogs`.
