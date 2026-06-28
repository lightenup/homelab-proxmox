---
description: "Task list for Market-Model Service Deploy"
---

# Tasks: Market-Model Service Deploy

**Input**: Design documents from `/specs/049-market-model-deploy/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: No automated test tasks — this is declarative IaC (Terraform + Ansible). Validation is
plan-only / `--check` / `--syntax-check` plus the quickstart manual verification (per plan.md
Technical Context). No unit-test surface is introduced.

**Organization**: Tasks are grouped by user story. US1 and US2 are both P1; US1 is the MVP slice
(healthy deploy), US2 layers the MCP round-trip onto it, US3 (P2) covers upgrade safety and
disposability.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- File paths are exact and relative to the repo root.

## Reference pattern

Every artifact mirrors its `financial-scenario` (feature `048`) counterpart **minus** GUI, backup,
NFS, and reference-data seeding. Diff carefully against the reference rather than authoring from
scratch. In particular, `financial-scenario` is deployed **standalone** via `pve-service-deploy`
(which runs Terraform in `terraform/services/<service>/` and reads that dir's `ansible_inventory`
output) — it is **not** present in `services.yml`, `site.yml`, or the root `terraform/outputs.tf`.
Match that.

---

## Phase 1: Setup (Shared Scaffolding)

**Purpose**: Create the empty per-service Terraform layout and the role skeleton so every later task
has a home. No behavior yet.

- [X] T001 [P] Create the per-service Terraform directory `terraform/services/market-model/` by
  copying `providers.tf` and `variables.tf` verbatim from `terraform/services/financial-scenario/`
  (provider pin `telmate/proxmox = 2.9.11`; variables unchanged).
- [X] T002 [P] Create the `market_model` Ansible role skeleton with directories
  `ansible/roles/market_model/{defaults,tasks,templates,handlers}/` and an empty
  `ansible/roles/market_model/handlers/main.yml` containing a single `Restart market-model` handler
  (mirror `ansible/roles/financial_scenario/handlers/main.yml`).
- [X] T003 [P] Create `ansible/roles/market_model/defaults/main.yml` with `market_model_install_dir`
  (`/opt/market-model`), `market_model_data_dir` (`/opt/market-model-data`),
  `market_model_ghcr_registry` (`ghcr.io`), and `market_model_image`
  (`ghcr.io/lightenup/market-model`) — mirroring `financial_scenario/defaults/main.yml` but single
  image, no GUI image, no backup vars.

**Checkpoint**: Empty scaffolding compiles (`terraform fmt` clean, role parses) but does nothing.

---

## Phase 2: Foundational (Declarations — Blocking Prerequisites)

**Purpose**: Declare the LXC, the version pin, the service IP, and the inventory/CI wiring that every
user story depends on. MUST complete before US1 can deploy.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T004 Add `module "market_model_lxc"` to `terraform/main.tf` mirroring the
  `financial_scenario_lxc` block (`cores=2`, `memory=2048`, `disk_gb=16`,
  `ip = var.service_ips["market-model"]`) but **WITHOUT** any `features_mount` line (no in-guest NFS;
  D-001). Do **not** add the service to the root `terraform/outputs.tf` inventory — the reference
  service is absent there; its inventory comes from the per-service dir (T005).
- [X] T005 [P] Create `terraform/services/market-model/main.tf` and
  `terraform/services/market-model/outputs.tf` mirroring
  `terraform/services/financial-scenario/{main.tf,outputs.tf}` (module source `../../modules/lxc_service`,
  no `features_mount`; `ansible_inventory` output exposing `"market-model" = module.market_model_lxc.ipv4`).
  This per-service output is the inventory source `pve-service-deploy` reads.
- [X] T006 [P] Add `market-model = "192.168.1.218/24"` to `service_ips` in
  `terraform/environments/prod.tfvars.template` and `market-model = "192.168.20.219/24"` in
  `terraform/environments/lab.tfvars.template` (operator-confirmed free IPs; research §Service IP
  allocation).
- [X] T007 Add the version pin and network vars to `ansible/group_vars/services/vars.yml`:
  `market_model_version: "0.3.0"`, `market_model_ip: "192.168.1.218"`,
  `market_model_api_port: 8000`, `market_model_mcp_port: 8001` (never empty/`latest`).
- [X] T008 [P] Add `"market-model": ["module.market_model_lxc"]` to
  `scripts/lab/service-scope-allowlist.json` (Dual-Provisioning Parity).
- [X] T009 [P] Add `market-model` to the `service` choice `options` in the **three** deploy/promote
  workflows that list the reference service: `.github/workflows/lxc-deploy-lab.yml`,
  `.github/workflows/lxc-promote-lab.yml`, and `.github/workflows/lxc-promote-prod.yml`
  (Constitution V — same change as the service). Do **not** add it to
  `lab-integration-tests.yml` unless integration coverage is separately decided — the reference
  service is absent there.

**Checkpoint**: `terraform validate` + plan-only succeeds and the host resolves via the per-service
`ansible_inventory` output; no Ansible role behavior yet.

---

## Phase 3: User Story 1 - Deploy comes up healthy through the gated pipeline (Priority: P1) 🎯 MVP

**Goal**: Provision the LXC, render the two-role compose from one image, bring it up, and verify the
`api` is healthy — LAN/tailnet-only, two ports published, no GUI, no Caddy route.

**Independent Test**: Run the playbook on the host; `GET :8000/healthz` → 200, `GET :8000/` returns
the path-source index, and only `8000` + `8001` are published.

- [X] T010 [US1] Create `ansible/roles/market_model/tasks/preflight.yml` mirroring
  `financial_scenario/tasks/preflight.yml`: assert `ghcr_pull_username`/`ghcr_pull_token` are
  defined, assert `market_model_version` is defined/non-empty/not `latest`, and check the Docker
  daemon is started. **Omit** any MCP-secret, NFS, or backup assertions.
- [X] T011 [US1] Create `ansible/roles/market_model/tasks/main.yml` with: include `preflight.yml`;
  ensure `market_model_install_dir` exists (`0755`); ensure `{{ market_model_data_dir }}/data`
  exists `0755` **owned by `100:65534`** (uid/gid the non-root `appuser` runs as — D-006); GHCR
  `community.docker.docker_login` (reuse `ghcr_pull_username`/`ghcr_pull_token`, `no_log: true`).
  **Do NOT** add reference-data seed tasks or any `.db` seeding (app creates/migrates on startup).
- [X] T012 [US1] Create `ansible/roles/market_model/templates/docker-compose.yml.j2` per
  [contracts/compose-topology.md](./contracts/compose-topology.md): an `api` service (default uvicorn
  CMD; publish `{{ market_model_api_port }}:8000`; bind-mount `{{ market_model_data_dir }}/data:/app/data`
  and `/etc/localtime:/etc/localtime:ro`; `restart: unless-stopped`; healthcheck `GET /healthz`).
  Add a generated-file header note that `MARKET_MODEL_DB_PATH` is intentionally unset (D-007). The
  `mcp` service block is added in US2 (T016).
- [X] T013 [US1] In `ansible/roles/market_model/tasks/main.yml`, append: render the compose template
  to `{{ market_model_install_dir }}/docker-compose.yml` (notify `Restart market-model`); run
  `community.docker.docker_compose_v2` (`state: present`, `pull: always`, `remove_orphans: true`).
- [X] T014 [US1] In `ansible/roles/market_model/tasks/main.yml`, append health verification per
  [contracts/monitoring-contract.md](./contracts/monitoring-contract.md): `wait_for` port
  `{{ market_model_api_port }}` on `127.0.0.1`, then `uri` GET `/healthz` expecting `200` with
  retries (mirror financial_scenario wait/verify).
- [X] T015 [US1] Create `ansible/playbooks/market-model.yml` mirroring
  `ansible/playbooks/financial-scenario.yml` **minus** the `financial_scenario_backup` role: a base
  play (`roles: [lxc_base]`) and a deploy play (`roles: [geerlingguy.docker, market_model]`) on host
  `market-model`. Do **not** add an `import_playbook` to `services.yml` or `site.yml` — the reference
  service is deployed standalone via `pve-service-deploy` and is absent from both (FR-010).

**Checkpoint**: `pve-service-deploy market-model --apply` brings `market_model_api` healthy;
`:8000/healthz` → 200; only `8000`/`8001` published (mcp container present once US2 lands). MVP
deliverable.

---

## Phase 4: User Story 2 - An MCP agent generates and retrieves path sets (Priority: P1)

**Goal**: The `mcp` role (port 8001) forwards to `api:8000`, persists generated sets, and serves them
back by id — reachable directly over the tailnet.

**Independent Test**: From a tailnet client call `list_calibrations`/`list_stress_scenarios`, then
`generate_path_set` → `{id, version}`, then `get_path_set(id)` returns the byte-identical blob.

- [X] T016 [US2] Add the `mcp` service to
  `ansible/roles/market_model/templates/docker-compose.yml.j2` per
  [contracts/compose-topology.md](./contracts/compose-topology.md): same image,
  `command: ["python", "-m", "market_model.mcp.server"]`; env `MCP_TRANSPORT=http`, `MCP_PORT=8001`,
  `API_BASE_URL=http://api:8000`; publish `{{ market_model_mcp_port }}:8001`; **no** data volume
  (localtime only); `depends_on: api` `condition: service_healthy`; `restart: unless-stopped`;
  healthcheck = TCP connect to `localhost:8001`.
- [ ] T017 [US2] Verify the MCP round-trip and topology per
  [quickstart.md](./quickstart.md) §3–§4: confirm `docker inspect market_model_mcp` shows
  `API_BASE_URL=http://api:8000`, `MCP_TRANSPORT=http`, no data mount, `depends_on` api healthy; run
  `generate_path_set` then `get_path_set(id)` and confirm the row lands in
  `{{ market_model_data_dir }}/data/path-sets.sqlite`. Record results in the quickstart/work notes.

**Checkpoint**: Full P1 scope — healthy deploy **and** a working MCP generate/retrieve round-trip.

---

## Phase 5: User Story 3 - Upgrade in place; the cache is disposable (Priority: P2)

**Goal**: A version bump redeploys cleanly without clobbering the store; a wiped store recovers by
re-seeding the curated library and reproducing assembled sets from identical inputs.

**Independent Test**: Bump `market_model_version`, redeploy → both roles healthy, rows intact.
Separately wipe `path-sets.sqlite`, restart → healthy, curated library re-seeded, assembled set
reproducible (same `sha256:` id).

- [X] T018 [US3] Confirm the data-dir task in `ansible/roles/market_model/tasks/main.yml` is
  **idempotent and never-clobbering**: `state: directory` only (no `recurse` chown that would fight
  the app), never copies/initialises a `.db`, and re-runs leave an existing `path-sets.sqlite`
  untouched. Add an inline comment citing D-001/D-006 (mirror financial_scenario's "never seed"
  comment).
- [ ] T019 [US3] Execute the upgrade-safety and disposability checks per
  [quickstart.md](./quickstart.md) §5–§6: bump the pin and redeploy (both roles healthy on the new
  tag, rows intact, curated library re-seeded via `INSERT OR IGNORE`); then wipe the host data dir,
  restart, and confirm healthy + re-seeded + a previously assembled set reproduces with an identical
  content-addressed id. Record results in the work notes.

**Checkpoint**: Upgrade and DR behavior verified; store confirmed disposable.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Monitoring contract, healthcheck wrapper, and final validation across all stories.

- [X] T020 [P] Create `ansible/host_vars/market-model.yml` mirroring
  `ansible/host_vars/financial-scenario.yml` per
  [contracts/monitoring-contract.md](./contracts/monitoring-contract.md): `healthcheck_url`
  `{scheme: http, port: 8000, path: /healthz}`, `healthcheck_profile: lan`,
  `healthcheck_expect_status: 200`, and a `monitoring_contract` with one `liveness_targets` entry
  (`market-model-api` → `http://192.168.1.218:8000/healthz`, `module: http_2xx`) and a
  `MarketModelDown` alert (`probe_success == 0 for 5m`, severity critical). `scrape_targets: []`.
- [X] T021 [P] Create `scripts/healthcheck/market-model.sh` mirroring
  `scripts/healthcheck/financial-scenario.sh` (accept `--profile lan|tailscale` and `--output-json`;
  invoke `healthcheck.py --host market-model`). Make it executable (`chmod +x`).
- [X] T022 Final validation: `terraform fmt -check` + `terraform validate` + plan-only; `ansible-lint`
  / `ansible-playbook --syntax-check ansible/playbooks/market-model.yml`; `act -l` to confirm the
  workflow dropdowns still parse; confirm preflight rejects an empty/`latest`
  `market_model_version` (SC-007); and confirm the blackbox probe `market-model-api` is green with
  `MarketModelDown` firing on stop (quickstart §7). No Caddy route, no landing-page card, only
  `8000`/`8001` published.

---

## Dependencies & Execution Order

- **Setup (T001–T003)** → before everything.
- **Foundational (T004–T009)** → before any user story; T004/T007 are sequential edits to shared
  files, T005/T006/T008/T009 are `[P]`.
- **US1 (T010–T015)** → the MVP; T011/T013/T014 edit the same `tasks/main.yml` sequentially; T012
  (compose) precedes T013 (render/up).
- **US2 (T016–T017)** → depends on US1 (compose + deploy exist). T016 extends the same compose
  template authored in T012.
- **US3 (T018–T019)** → depends on US1 (role/tasks exist); independent of US2.
- **Polish (T020–T022)** → T020/T021 are `[P]` and depend only on Foundational vars; T022 is the
  final gate after all stories.

## Parallel Opportunities

- **Setup**: T001, T002, T003 in parallel (different files).
- **Foundational**: T005, T006, T008, T009 in parallel after T004/T007 land.
- **Polish**: T020 and T021 in parallel.

## Implementation Strategy

**MVP = Phase 1 + Phase 2 + Phase 3 (US1)**: a healthy, correctly-scoped, LAN/tailnet-only deploy.
Add **US2** for the MCP round-trip (completes P1 scope), then **US3** for upgrade/DR confidence, then
**Polish** for monitoring + the final validation gate.
