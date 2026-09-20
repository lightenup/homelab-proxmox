# Contract — Alias Mapping Data → `config.yaml`

**Feature**: `064-llm-router` | Satisfies FR-003, FR-004, FR-005

This is the contract that makes SC-003 true: **the role template must be able to render any valid
alias mapping without being edited.** If a retier ever requires touching `config.yaml.j2` or role
logic, this contract has been broken.

## Source of truth

`ansible/group_vars/services/vars.yml` → `llm_router_aliases` (shape in
[data-model.md](../data-model.md#entity-alias-mapping-the-aggregate)).

## Rendering rules

1. **One `model_list` entry per deployment**, with `model_name` set to the **alias**. LiteLLM's
   repeated-`model_name` convention is what turns an ordered list into a routing pool; entry order
   in `model_list` preserves `deployments` order.
2. **Credentials by indirection only** — `api_key: os.environ/<api_key_env>`. A rendered literal key
   in `config.yaml` is a Constitution II violation and a preflight failure.
3. **`model_info.disable_background_health_check: true`** on every deployment with
   `health_checked: false`, so a deployment that must not be probed on a timer never is
   (D-101). Written for the metered tiers, which are gone; it still governs any future
   backend where a probe costs money or wakes something up.
4. **`router_settings.fallbacks`** built from every alias with a non-null `fallback_to`.
5. **`router_settings.context_window_fallbacks`** built from every alias with a non-null
   `context_window_fallback_to`.
6. **No alias name appears literally in the template.** The template iterates; it never branches on
   `hermes-fast`. This is the mechanical check that FR-003 holds.

## Rendered shape

```yaml
model_list:
{% for alias in llm_router_aliases %}
{% for d in alias.deployments %}
  - model_name: {{ alias.name }}
    litellm_params:
      model: {{ d.provider_model }}
{% if d.api_base is defined and d.api_base %}
      api_base: {{ d.api_base }}
{% endif %}
{% if d.api_key_env is defined and d.api_key_env %}
      api_key: os.environ/{{ d.api_key_env }}
{% endif %}
      timeout: {{ d.timeout | default(llm_router_request_timeout) }}
    model_info:
      id: {{ d.id }}
      disable_background_health_check: {{ not d.health_checked }}
{% endfor %}
{% endfor %}

router_settings:
  fallbacks: [ ... from alias.fallback_to ... ]
  context_window_fallbacks: [ ... from alias.context_window_fallback_to ... ]
  allowed_fails: 0
  cooldown_time: 60
  num_retries: 0
  enable_pre_call_checks: true

general_settings:
  background_health_checks: true
  health_check_interval: 60
  background_health_check_model_groups: [ ... aliases having a health_checked deployment ... ]

litellm_settings:
  ssl_verify: /etc/ssl/mac-ca.pem     # the Mac's cert — a path, never `false`
```

Three of those carry a decision that is easy to undo by accident:

- **`timeout` is per-deployment**, defaulting to `llm_router_request_timeout`. A single
  gateway-wide timeout cannot be right when one alias answers in two seconds and another
  spends twenty minutes on a cold prefill.
- **`allowed_fails: 0`**, not a tolerance. The failure counter's TTL is `cooldown_time`, so
  a count above zero is only reached by that many failures *within* the cooldown window —
  with a long per-request timeout, it never is, and every request pays the full timeout.
  Zero means the first failure cools the deployment down and the rest fail in ~0.03 s.
- **`ssl_verify` is a path, not a boolean.** The local-tier leg carries `mac_litellm_key`,
  so it is authenticated as well as encrypted. Setting this to `false` would keep the
  feature working and silently drop the authentication.

## Change semantics

| Change | Blast radius |
|---|---|
| Swap a deployment's `provider_model` | One `group_vars` line + deploy. No client change. **This is the SC-003 drill.** |
| Reorder `deployments` | Changes preference. No client change. |
| Add a deployment to an alias | One list entry. No client change. |
| Add a new alias | `group_vars` only — but clients must be told the new name exists. |
| Rename an alias | **Breaking.** Every client changes. Treat as a new alias plus a deprecation. |

## Preflight assertions

Rendering is not attempted until all of these pass — a malformed mapping should fail the deploy, not
produce a subtly wrong routing table:

- Fallback graph is acyclic and terminates at an alias with no `fallback_to`.
- Every referenced alias exists.
- Every `tier: local` deployment has a `.local` mDNS `api_base` and not an IP literal
  (FR-013). Amended 2026-09-14: the namespace moved from MagicDNS to mDNS when the local
  tier moved from the tailnet to the LAN. The invariant is unchanged — a stable name,
  never a DHCP-assigned address.
- Every deployment's `api_key_env`, local or not, names a vault variable that is non-empty.
  The local tier is no longer unauthenticated: it presents `mac_litellm_key` to the Mac's
  own gateway.
- `sum(client budgets) < gateway cap` (see [data-model.md](../data-model.md#entity-gateway-budget)).
- `llm_router_version` is pinned — not empty, not `latest` (FR-001).
