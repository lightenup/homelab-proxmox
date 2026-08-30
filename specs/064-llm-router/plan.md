# Implementation Plan: LLM Router (gateway LXC)

**Branch**: `064-llm-router` | **Date**: 2026-08-29 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/064-llm-router/spec.md`

## Summary

Deploy LiteLLM as a single-endpoint, OpenAI-compatible LLM gateway on a new `llm-router` LXC
(`192.168.1.220`), provisioned by the existing `modules/lxc_service` Terraform module and configured
by a new `llm_router` Ansible role running `docker_compose_v2` — the same shape as `market-model`
and `eurooffice`.

Clients address three intent aliases (`hermes-fast`, `hermes-balanced`, `hermes-deep`). Each alias
maps to an ordered list of deployments defined as data in `ansible/group_vars/services/vars.yml` and
templated into `config.yaml`. LiteLLM's background health checks — scoped to the local model group
only, so probes never bill — pull the intermittent Mac out of the pool before a request lands on it,
and `router_settings.fallbacks` carries the request to the aggregator or Anthropic tier.

Two design problems the spec did not fully anticipate are resolved here:

1. **The LXC has no tailnet path today.** Tailscale runs only on the PVE host as a subnet router,
   which advertises the LAN *into* the tailnet — it does not let a LAN-only LXC reach a roaming Mac.
   Resolved by running `tailscaled` in userspace-networking mode as a compose sidecar and pointing
   LiteLLM at its outbound HTTP proxy: no TUN device, no `pct set`, no privileged container, and no
   collision with the Tier-2 bind-mount allowlist. See research D-102.
2. **The Mac blackbox probe FR-009(c) asks for would need the *monitoring* LXC on the tailnet too.**
   Resolved by taking the local-tier signal from LiteLLM's own `litellm_deployment_state` metric,
   scraped over the LAN, instead of a second tailnet path. See research D-103.

## Technical Context

**Language/Version**: HCL (Terraform, `telmate/proxmox`), YAML (Ansible 2.x), Jinja2, Bash. No new language.
**Primary Dependencies**: `modules/lxc_service` (Terraform); `geerlingguy.docker` + `community.docker.docker_compose_v2` (Ansible); `ghcr.io/berriai/litellm` (pinned, non-`latest`); `postgres:17-alpine`; `tailscale/tailscale` (userspace sidecar). **No Redis** — single-worker, see research D-104.
**Storage**: PostgreSQL on the LXC's local disk (`/opt/llm-router-data/postgres`) for virtual keys, budgets and `LiteLLM_SpendLogs`. No NFS mount (`features_mount` omitted) — FR-012. No user data persisted; prompt/response bodies not logged.
**Testing**: `pve-service-deploy plan` (non-destructive), `scripts/healthcheck/llm-router.sh` post-apply, `act -l` for workflow changes, plus the manual downed-backend drill (SC-008)
**Target Platform**: Debian stable unprivileged LXC on PVE, nesting enabled, static IP `192.168.1.220/24`
**Project Type**: Homelab IaC — Terraform (existence/sizing) + Ansible (in-guest config). Not a `src/`+`tests/` application.
**Performance Goals**: Gateway overhead is negligible next to inference; the binding number is FR-005's ≤60 s health-check interval, so a dead Mac leaves the pool within one interval.
**Constraints**: No public reachability (FR-008 — LAN + tailnet, no Caddy route); LXC sized 2 vCPU / 4 GB / 16 GB; background probes must not bill (FR-005); no Anthropic subscription credential (FR-007)
**Scale/Scope**: Single-node, single-worker, a handful of homelab clients. One new Terraform module block, one new Ansible role, one new playbook, one healthcheck script, three workflow dropdown entries, one allowlist entry.

## Constitution Check

*GATE: evaluated before Phase 0 and re-evaluated after Phase 1 design.*

| Principle | Status | Notes |
|---|---|---|
| **I. Spec-Driven Workflow** | PASS | Work is driven from `specs/064-llm-router/`; spec and plan updated together. |
| **II. Secrets Policy (NON-NEGOTIABLE)** | PASS | `OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY`, `LITELLM_MASTER_KEY`, Postgres password and the Tailscale auth key all come from `ansible/group_vars/services/vault.yml`. `config.yaml` uses `os.environ/<NAME>` indirection so no rendered secret lands on disk. FR-007 additionally forbids any Anthropic subscription/OAuth credential. |
| **III. Separation of Concerns** | PASS | Terraform owns only the LXC's existence and sizing (`module.llm_router_lxc`). Ansible owns everything inside: Docker, compose, `config.yaml`, virtual keys. No mixing. |
| **IV. Code Economy (YAGNI)** | PASS | The Redis container was dropped — it carries no consumer at one worker, and FR-014 was amended to make it conditional. Everything else is justified: the alias Jinja loop iterates 3 items (>1, so templating earns its keep), and the role follows the existing `market_model` shape rather than inventing an abstraction. |
| **V. Dual-Provisioning Parity** | PASS | Allowlist entry, healthcheck script and all three workflow dropdowns land in the same PR (FR-011). `pve-service-deploy` runs identically from CI and laptop. |
| **Token Privilege Tiers** | PASS | Tier 1 only. The userspace-networking decision (D-102) specifically avoids needing Tier-2 `pct set` device passthrough for `/dev/net/tun`. |
| **Provider Strategy** | PASS | `telmate/proxmox` via the existing `modules/lxc_service`. |
| **Networking** | PASS | Static IP `192.168.1.220/24` allocated centrally in `service_ips`, not scattered. |
| **State Management** | PASS | Unchanged — local state on PVE, backed up to Synology. |
| **Test-Driven Changes** | PASS | `pve-service-deploy plan` is the non-destructive check; SC-008's downed-backend drill is an explicit acceptance step, not an assumption. |

**Post-Phase-1 re-evaluation**: unchanged. The design added no new abstraction layer — one role, one
compose file, one templated config.

**Post-analyze re-evaluation**: Constitution I was **violated and is now repaired**. Phase 0 changed
the architecture in three ways (Redis dropped, Mac probe replaced, tailnet sidecar added) without
amending `spec.md` in the same change, which Principle I requires. The spec now carries FR-017,
FR-018, SC-013, an amended FR-008/FR-009/FR-014, and a Decisions note recording the amendments.
Principle IV moves from "pass with a correction" to a clean pass.

## Project Structure

### Documentation (this feature)

```text
specs/064-llm-router/
├── spec.md
├── plan.md              # This file
├── research.md          # Phase 0 — six decisions, incl. the two design corrections above
├── data-model.md        # Phase 1 — alias/deployment/client-key entities and validation rules
├── quickstart.md        # Phase 1 — deploy, verify, and run the downed-backend drill
├── contracts/
│   ├── alias-mapping.md     # group_vars → config.yaml data contract (FR-003)
│   ├── gateway-api.md       # client-facing OpenAI-compatible surface + health endpoints (FR-002)
│   └── monitoring.md        # monitoring_contract shape and alert semantics (FR-009)
├── checklists/
│   └── requirements.md
└── tasks.md             # Phase 2 — created by /speckit.tasks, NOT by this command
```

### Source Code (repository root)

```text
terraform/
├── main.tf                                   # + module "llm_router_lxc"
└── environments/prod.tfvars.template         # + service_ips["llm-router"] = "192.168.1.220/24"

ansible/
├── group_vars/services/
│   ├── vars.yml                              # + llm_router_version pin, ports, alias mapping data
│   └── vault.yml                             # + provider keys, master key, DB password, TS auth key
├── roles/monitoring_stack/templates/
│   └── prometheus.yml.j2                     # ~ optional bearer auth on scrape_targets (SHARED FILE)
├── host_vars/llm-router.yml                  # + healthcheck_* and monitoring_contract
├── inventories/prod/hosts.yml                # + llm-router host entry
├── playbooks/llm-router.yml                  # + lxc_base → geerlingguy.docker → llm_router
└── roles/llm_router/
    ├── defaults/main.yml
    ├── handlers/main.yml
    ├── tasks/main.yml
    ├── tasks/preflight.yml                   # pin, vault vars, docker daemon, alias-mapping shape
    ├── tasks/virtual_keys.yml                # per-client keys + budgets (FR-010, FR-015)
    ├── files/llm-router-dashboard.json        # Grafana dashboard (FR-009)
    └── templates/
        ├── docker-compose.yml.j2             # litellm + postgres + tailscale sidecar (no redis)
        ├── config.yaml.j2                    # alias loop + router_settings (FR-003, FR-004)
        └── canary.sh.j2                      # synthetic all-backends-down probe (FR-018)

scripts/
├── healthcheck/llm-router.sh                 # + post-apply healthcheck
└── lab/service-scope-allowlist.json          # + "llm-router": ["module.llm_router_lxc"]

.github/workflows/
├── lxc-deploy-lab.yml                        # + llm-router in the service dropdown
├── lxc-promote-lab.yml                       # + llm-router
└── lxc-promote-prod.yml                      # + llm-router
```

**Structure Decision**: This feature follows the repository's established one-LXC-per-service
pattern, mirroring `market-model` (the closest precedent: containerised, no NFS mount, no public
Caddy route). No new directory conventions are introduced. The only structural addition is the
`llm_router` role; every other change is an entry appended to an existing central file, which is
what Constitution IV asks for.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| **Postgres container** | FR-010 and FR-015 require per-client virtual keys and budgets, and LiteLLM enforces budgets only with a Postgres database (confirmed in Phase 0). It is also the source for per-alias spend if the metrics endpoint disappoints. | Config-only LiteLLM cannot enforce per-client budgets at all, which would fail FR-010 outright. |
| **Tailscale sidecar container** | FR-017 — the LXC has no other path to a roaming Mac (D-102). Without it FR-013 is unsatisfiable. | A LAN IP fails the moment the Mac leaves the house — the exact scenario the feature exists for. Host-level TUN passthrough needs Tier-2 `pct set` and collides with the bind-mount allowlist. |
| **Synthetic canary request** | FR-018 — an all-backends-failing gateway is otherwise silent when no client traffic flows, leaving the spec's headline edge case unmitigated. | A failure-rate alert alone only fires under load, which is precisely when the trap is *not* the problem. |

**Resolved during `/speckit.analyze` remediation**: the Redis container was removed from this table —
the operator confirmed dropping it and FR-014 was amended to make it conditional on worker count, so
it is no longer a deviation to justify.
