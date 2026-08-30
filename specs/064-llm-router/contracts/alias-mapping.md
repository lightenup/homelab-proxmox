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
   `health_checked: false`, so metered tiers are never probed (D-101).
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
    model_info:
      id: {{ d.id }}
      disable_background_health_check: {{ not d.health_checked }}
{% endfor %}
{% endfor %}

router_settings:
  fallbacks: [ ... from alias.fallback_to ... ]
  context_window_fallbacks: [ ... from alias.context_window_fallback_to ... ]
  allowed_fails: 2
  cooldown_time: 60
  enable_pre_call_checks: true

general_settings:
  background_health_checks: true
  health_check_interval: 60
  background_health_check_model_groups: [ ... aliases having a health_checked deployment ... ]
```

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
- Every `tier: local` deployment has a `*.ts.net` `api_base` and not an IP literal (FR-013).
- Every non-local deployment names a non-empty `api_key_env`.
- `sum(client budgets) < gateway cap` (see [data-model.md](../data-model.md#entity-gateway-budget)).
- `llm_router_version` is pinned — not empty, not `latest` (FR-001).
