# Implementation Plan: Market-Model Service Deploy

**Branch**: `049-market-model-deploy` | **Date**: 2026-06-28 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/049-market-model-deploy/spec.md`

## Summary

Stand up the `market-model` service on its own unprivileged Debian LXC, modelled on the
financial-scenario deploy (feature `048`) but reduced to its essentials: a **single** pinned GHCR
image (`ghcr.io/lightenup/market-model`) run as **two roles** (`api` on 8000, `mcp` on 8001) through
the existing `lxc_service` Terraform module + `geerlingguy.docker` + `community.docker.docker_compose_v2`
pipeline. Both ports are published directly on the LAN/tailnet (no GUI, no nginx, no auth gate); the
only state is a regenerable SQLite `path-sets.sqlite` cache on a host bind-mount that is **not**
backed up (no backup role, no in-guest NFS, no `features_mount`). Liveness uses the new api
`GET /healthz`. Monitoring is blackbox liveness only, mirroring `financial-scenario.yml`.

Technical approach: add a `market_model_lxc` block to `terraform/main.tf` (+ per-service dir
`terraform/services/market-model/` and inventory output) sized `2c/2048MB/16GB` with **no**
`features_mount`; allocate `service_ips["market-model"]`; add `market_model_*` pins to
`group_vars/services/vars.yml`; create a `market_model` Ansible role mirroring `financial_scenario`
**minus** the reference-data seed and backup wiring, with its host data dir **chowned to `100:65534`**
(the image runs non-root as `appuser`); add a two-service `docker-compose.yml.j2`; add
`host_vars/market-model.yml` + `scripts/healthcheck/market-model.sh`; add
`playbooks/market-model.yml`; and wire the service into the inventory, `services.yml`, the
service-scope allowlist, and the four CI workflow dropdowns (Dual-Provisioning Parity).

## Technical Context

**Language/Version**: HCL (Terraform, `telmate/proxmox` `2.9.11`), YAML (Ansible 2.x), Jinja2. No
application code — a pinned GHCR image only.
**Primary Dependencies**: `lxc_service` Terraform module; `geerlingguy.docker` +
`community.docker` Ansible collections; the existing `financial_scenario` role as the reference
pattern.
**Storage**: SQLite `path-sets.sqlite` at `/app/data/` inside the `api` container, backed by host
bind-mount `{{ market_model_data_dir }}/data` owned by uid `100` / gid `65534`. **No** backup
destination, **no** NFS mount, **no** reference-data bind-mount (curated library is image-baked and
self-seeds).
**Testing**: `terraform validate` + plan-only; `ansible-playbook --syntax-check` / `--check`;
`scripts/healthcheck/market-model.sh`; manual MCP round-trip + disposability check (quickstart). No
new unit-test surface (declarative IaC).
**Target Platform**: Unprivileged Debian 12 LXC on Proxmox VE; prod IP `192.168.1.218` (proposed
next free), lab `192.168.20.219` (proposed next free) — operator confirms/allocates.
**Project Type**: Infrastructure (Terraform + Ansible), single repo. No `src/`/`tests/` app layout.
**Performance Goals**: N/A beyond blackbox liveness (one human + a few agents).
**Constraints**: LAN/tailnet-only (no Caddy route, no landing card); two published ports
(`api:8000`, `mcp:8001`); MCP unauthenticated at the service (read/compute-only); host data dir MUST
be writable by uid `100` or the app cannot create the store; never clobber an existing
`path-sets.sqlite`.
**Scale/Scope**: One service LXC; sizing `2c/2048MB/16GB` (D-003, revisit only under memory
pressure). One new role, one new playbook, one new host_vars file, one new healthcheck wrapper.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Spec-Driven Workflow** — PASS. Driven from `specs/049-market-model-deploy/spec.md`; tasks will
  be enumerated in `tasks.md`. Backlog `docs/backlog/048-market-model-deploy.md` is the originating
  source; the spec is the source of truth.
- **II. Secrets Policy** — PASS. No new secrets. Reuses the existing `ghcr_pull_username` /
  `ghcr_pull_token` vault vars. There is no MCP secret (no gate, D-002) and no NFS credential.
- **III. Separation of Concerns** — PASS. Terraform owns only the LXC existence/sizing (no
  `features_mount`, since no in-guest NFS is needed). Ansible owns everything inside the guest: the
  data dir + ownership, the compose template, the GHCR login, and health verification.
- **IV. Code Economy (YAGNI)** — PASS. Reuses the `lxc_service` module, the existing GHCR creds, and
  the financial-scenario role as a pattern. Exactly one new role, one new playbook, one new host_vars,
  one new healthcheck wrapper — each justified by separation of concerns and direct precedent. The
  compose template hosts two services (loop not justified for 2 heterogeneous services; written out
  explicitly like financial-scenario). No backup role, no NFS module, no seed tasks — deliberately
  dropped vs. 048 because market-model's store is a regenerable cache (D-001).
- **V. Dual-Provisioning Parity** — PASS. The new service is added to the service-scope allowlist and
  all four CI workflow dropdowns (`lxc-deploy-lab`, `lxc-promote-lab`, `lxc-promote-prod`,
  `lab-integration-tests`) in this same change; the `pve-service-deploy` orchestrator maps the
  service name to `ansible/playbooks/market-model.yml`, runnable identically from CI and laptop.

**Result**: PASS. No deviations to justify (Complexity Tracking empty).

**Post-design re-check (after Phase 1)**: PASS — unchanged. The Phase 1 design (one role, one
playbook, one host_vars, one healthcheck wrapper, no backup/NFS module) introduces no new
abstractions and no new secrets; all five principles still hold.

## Project Structure

### Documentation (this feature)

```text
specs/049-market-model-deploy/
├── plan.md              # This file
├── research.md          # Phase 0 — decisions (no-backup, direct MCP, non-root uid, sizing)
├── data-model.md        # Phase 1 — entities (path-set store, curated library, version pin)
├── quickstart.md        # Phase 1 — deploy + MCP round-trip + upgrade + disposability verification
├── contracts/           # Phase 1 — compose topology + monitoring contracts
│   ├── compose-topology.md
│   └── monitoring-contract.md
├── checklists/
│   └── requirements.md  # From /speckit.specify
└── tasks.md             # /speckit.tasks (NOT created here)
```

### Source Code (repository root)

```text
terraform/
├── main.tf                                   # EDIT: add module "market_model_lxc" (no features_mount)
├── outputs.tf                                # EDIT: add market-model to ansible_inventory.services
├── services/market-model/                    # NEW: per-service dir mirroring services/financial-scenario/
│   ├── main.tf                               #   module "market_model_lxc" (../../modules/lxc_service)
│   ├── outputs.tf                            #   ansible_inventory output
│   ├── providers.tf / variables.tf           #   copied from services/financial-scenario/
└── environments/
    ├── prod.tfvars.template                  # EDIT: service_ips["market-model"]
    └── lab.tfvars.template                   # EDIT: service_ips["market-model"]

ansible/
├── group_vars/services/vars.yml              # EDIT: market_model_version, _ip, _api_port, _mcp_port
├── host_vars/market-model.yml                # NEW: blackbox liveness monitoring contract
├── playbooks/
│   ├── market-model.yml                      # NEW: lxc_base + geerlingguy.docker + market_model
│   └── services.yml                          # EDIT: import_playbook market-model.yml
└── roles/market_model/                       # NEW role (mirrors financial_scenario, minus seed/backup)
    ├── defaults/main.yml                      #   install/data dirs, image, ports
    ├── tasks/preflight.yml                    #   GHCR creds + pinned-tag + docker daemon assertions
    ├── tasks/main.yml                         #   dirs (data dir chown 100:65534), GHCR login,
    │                                          #   compose render, compose up, /healthz verify
    ├── templates/docker-compose.yml.j2        #   api + mcp from one image
    └── handlers/main.yml                      #   Restart market-model

scripts/
├── healthcheck/market-model.sh               # NEW: wrapper mirroring financial-scenario.sh
└── lab/service-scope-allowlist.json          # EDIT: "market-model": ["module.market_model_lxc"]

.github/workflows/                            # EDIT: add "market-model" to service dropdowns in
                                              #   lxc-deploy-lab, lxc-promote-lab, lxc-promote-prod,
                                              #   lab-integration-tests
```

**Structure Decision**: Infrastructure project — no `src/`/`tests/` tree. Changes are localized to
`terraform/main.tf` + a new `terraform/services/market-model/` per-service dir (mirroring
`services/financial-scenario/`), shared service vars, one new Ansible role, one new playbook, one new
host_vars file, one new healthcheck wrapper, and the dual-provisioning wiring surfaces. No new
abstractions are introduced.

## Complexity Tracking

> No Constitution Check violations — this section is intentionally empty.
