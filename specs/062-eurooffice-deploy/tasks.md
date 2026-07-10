---
description: "Task list for Euro-Office Document Server Deploy"
---

# Tasks: Euro-Office Document Server Deploy

**Input**: Design documents from `/specs/062-eurooffice-deploy/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: This is an infrastructure feature. No unit-test suite is generated; validation is
non-destructive (`terraform plan`, Ansible preflight asserts, post-apply `uri` healthchecks, blackbox
liveness) per the constitution's "Test-Driven Changes". Each story ends with explicit verification
tasks drawn from the spec's Success Criteria and `quickstart.md`.

**Organization**: Tasks are grouped by user story. Because this is a layered infra deploy, the phases
are sequenced in **build order** (server healthy → exposed at the domain → connector editing), which
means the P2 exposure story (US3) is delivered before the P1 editing story (US1). All three together
form the deliverable P1 vertical — editing (US1) cannot function without the server (US2) and route
(US3). See Implementation Strategy.

## Decisions locked from `/speckit.analyze`

- **Port (F1)**: `eurooffice_port = 80`; the container publishes `80:80`, so the connector's
  `DocumentServerInternalUrl` (`http://<ip>/`, port 80), the Caddy upstream (`<ip>:80`), and the
  monitoring probe (`<ip>:80/healthcheck`) all agree on one port. Do **not** introduce a non-80 host
  port.
- **Environment / IP (I1, I2)**: Mirror `market-model` exactly — eurooffice is defined in
  `prod.tfvars.template` and `lab.tfvars.template` (both on the `192.168.1.x` network) at
  `192.168.1.219`, and `eurooffice_ip: "192.168.1.219"` in `group_vars`. Do **not** add it to the
  real `terraform/environments/lab.tfvars` (the divergent `192.168.20.x` file that also omits
  market-model). The prod IP in `group_vars` is what feeds the Caddy backend + monitoring contract,
  consistent with `market_model_ip`.

## Path Conventions

Infrastructure monorepo: `terraform/` (existence/sizing), `ansible/` (in-guest config),
`.github/workflows/` (pipeline). Paths are absolute-from-repo-root.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Confirm prerequisites and pin decisions before any code changes.

- [x] T001 Verify the pinned tag exists and is pullable: **RESOLVED — image pivot**. Full GHCR tag enumeration (anon + authenticated) confirmed `ghcr.io/euro-office/documentserver` publishes NO release tags (only CI build artifacts). Pivoted to `onlyoffice/documentserver:9.3` (Docker Hub, no auth required). Volume paths verified by pulling image on market-model LXC. Implementation updated: `eurooffice_image`, compose template volumes, preflight (GHCR creds removed), `eurooffice_version: "9.3"`. Research D-002 + D-003 updated. (research D-002)
- [ ] T002 Confirm the static IP allocation *(manual — verify 192.168.1.219 free on PVE)*: verify `192.168.1.219` is free in `terraform/environments/prod.tfvars.template` and `lab.tfvars.template` `service_ips` (both `192.168.1.x`); if taken, pick the next free host and update the locked decision (research D-007, analyze I1/I2).
- [ ] T003 Confirm PVE RAM headroom *(manual — run pvesh/free on PVE host before apply)* **before** provisioning (FR-002, edge "Host RAM exhaustion"): check the target Proxmox node has ≥ 4 GB free memory (`pvesh get /nodes/<node>/status` or `free -g` on the host). MUST NOT proceed to `terraform apply` if headroom is insufficient (analyze C1).
- [ ] T004 Confirm the connector install path *(manual — check Euro-Office Nextcloud integration doc + occ app:install on NC34)*: check that app id `eurooffice` (v11.0.1) is `occ app:install`-able on Nextcloud 34 and record the exact `config:app:set` key names from the Euro-Office Nextcloud integration doc; note the tarball fallback if not app-store-installable (research D-005). Record findings inline in `specs/062-eurooffice-deploy/research.md`.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: LXC existence/sizing, secrets, central vars, playbook, and pipeline registration that ALL stories depend on.

**⚠️ CRITICAL**: No user-story work can begin until this phase is complete.

- [ ] T005 Add `eurooffice_jwt_secret` *(manual — `ansible-vault edit group_vars/services/vault.yml`)* (≥32 chars) to `ansible/group_vars/services/vault.yml` via `ansible-vault edit` (Secrets Policy II; never committed plaintext).
- [x] T006 Add central config vars to `ansible/group_vars/services/vars.yml`: `eurooffice_version: "9.3.1"` in the "Service versions" block (FR-011) and an "Euro-Office Configuration" section with `eurooffice_ip: "192.168.1.219"` and `eurooffice_port: 80` (F1 — port pinned to 80).
- [x] T007 [P] Add `eurooffice = "192.168.1.219/24"` to `service_ips` in `terraform/environments/prod.tfvars.template` and `terraform/environments/lab.tfvars.template` (mirroring market-model). Do NOT edit the `192.168.20.x` `lab.tfvars` (analyze I1/I2).
- [x] T008 [P] Create `terraform/services/eurooffice/main.tf` and `terraform/services/eurooffice/outputs.tf` mirroring `terraform/services/market-model/` (adjust name/hostname `eurooffice`).
- [x] T009 Add `module "eurooffice_lxc"` to `terraform/main.tf` using `modules/lxc_service`: `cores = 4`, `memory = 4096`, `disk_gb = 15`, `ip = var.service_ips["eurooffice"]`, and **nesting enabled** via the module's `features` input (Docker-in-LXC; unlike market-model). No `features_mount` (no NFS).
- [x] T010 [P] Create `ansible/playbooks/eurooffice.yml` mirroring `ansible/playbooks/market-model.yml`: play 1 `lxc_base`; play 2 `geerlingguy.docker` then `eurooffice` (host group `eurooffice`).
- [x] T011 [P] Add `eurooffice` to the `service` choice `options` in `.github/workflows/lxc-deploy-lab.yml`, `.github/workflows/lxc-promote-lab.yml`, and `.github/workflows/lxc-promote-prod.yml` (Dual-Provisioning Parity V — same PR).

**Checkpoint**: LXC can be planned/created and the pipeline knows the service; role implementation can begin.

---

## Phase 3: User Story 2 - Deploy comes up healthy through the gated pipeline (Priority: P1) 🎯 Foundation of the MVP

**Goal**: The `eurooffice` document-server container runs `Up (healthy)` on its LXC via the gated pipeline; `/healthcheck` → 200; re-apply is idempotent and the version stays pinned.

**Independent Test**: Run `scripts/lab/pve-service-deploy --service eurooffice --env prod --apply`; container reaches `Up (healthy)`, post-apply `GET /healthcheck` → 200; re-run causes no recreation.

### Implementation for User Story 2

- [x] T012 [P] [US2] Create `ansible/roles/eurooffice/defaults/main.yml`: `eurooffice_install_dir: /opt/eurooffice`, `eurooffice_data_dir: /opt/eurooffice-data`, `eurooffice_ghcr_registry: ghcr.io`, `eurooffice_image: ghcr.io/euro-office/documentserver` (tag comes from `eurooffice_version`).
- [x] T013 [P] [US2] Create `ansible/roles/eurooffice/handlers/main.yml` with a `Restart eurooffice` handler using `community.docker.docker_compose_v2` (state restarted), mirroring the market_model handler.
- [x] T014 [US2] Create `ansible/roles/eurooffice/templates/docker-compose.yml.j2` per `contracts/compose-env.md`: pinned `{{ eurooffice_image }}:{{ eurooffice_version }}`, `JWT_ENABLED=true`, `JWT_SECRET={{ eurooffice_jwt_secret }}`, `EXAMPLE_ENABLED=false`, data/logs/config volumes under `eurooffice_data_dir`, published `{{ eurooffice_port }}:80` (i.e. `80:80` — F1), container healthcheck on `/healthcheck`, `restart: unless-stopped`. Confirm exact env-var names/volume paths from the Euro-Office Docker doc (research D-003).
- [x] T015 [US2] Create `ansible/roles/eurooffice/tasks/preflight.yml` mirroring `roles/market_model/tasks/preflight.yml`: assert GHCR creds present; assert `eurooffice_version` defined/non-empty/≠`latest` (FR-001); assert `eurooffice_jwt_secret is defined and | length >= 32` (FR-003); assert Docker daemon running (FR-004 example-off is enforced in the template).
- [x] T016 [US2] Create `ansible/roles/eurooffice/tasks/main.yml`: include preflight; ensure `eurooffice_install_dir` and `eurooffice_data_dir/{data,logs,config}` exist; `community.docker.docker_login` to GHCR (`no_log`); template the compose file (notify Restart); `docker_compose_v2` state present, `pull: always`, `remove_orphans: true`; `wait_for` the port; `uri` `GET /healthcheck` expecting 200 with retries (FR-008).
- [x] T017 [P] [US2] Create `ansible/host_vars/eurooffice.yml` per `contracts/monitoring-contract.md`: `healthcheck_url` (`/healthcheck`, port 80, lan, 200) + `monitoring_contract` with an `http_2xx` liveness probe on `http://192.168.1.219:80/healthcheck` and the `EuroOfficeDown` critical alert (mirrors `host_vars/market-model.yml`).
- [ ] T018 [US2] Deploy (plan then apply): `scripts/lab/pve-service-deploy --service eurooffice --env prod` then `--apply`. Verify container `Up (healthy)`, `/healthcheck` → 200 (SC-003).
- [ ] T019 [US2] Re-run the apply and confirm idempotence: no container recreation, version stays pinned (SC-003, Acceptance US2.2).

**Checkpoint**: The document server is running and healthy on the LXC (not yet publicly reachable or wired to Nextcloud).

---

## Phase 4: User Story 3 - Reachable and secured at eurooffice.hus-sky.no (Priority: P2)

**Goal**: `eurooffice.hus-sky.no` serves over TLS with WebSocket upgrade and an adequate proxy timeout.

**Independent Test**: `curl -I https://eurooffice.hus-sky.no/healthcheck` → 200 over TLS; the editor's `wss://` upgrade succeeds.

### Implementation for User Story 3

- [x] T020 [US3] Extend `ansible/roles/reverse_proxy/templates/service.caddy.j2` with an optional `transport http { read_timeout / write_timeout }` block gated on `item.proxy_timeout is defined`, so existing entries render unchanged (per `contracts/caddy-route.md`; Code Economy IV).
- [x] T021 [US3] Add the `eurooffice` entry to `caddy_services` in `ansible/group_vars/services/vars.yml`: `host: eurooffice`, `ip: "{{ eurooffice_ip }}"`, `port: "{{ eurooffice_port }}"`, `title`/`desc`, `enabled: true`, `user_facing: true`, `proxy_timeout: "300s"` (FR-006).
- [ ] T022 [US3] Deploy the reverse proxy (`scripts/lab/pve-service-deploy --service reverse_proxy --env prod --apply`); the role's `caddy validate` passes.
- [ ] T023 [US3] Verify exposure (SC-004, Acceptance US3.1): `curl -I https://eurooffice.hus-sky.no/healthcheck` → 200 over TLS; and assert WebSocket upgrade automatically — `curl -sS -o /dev/null -w '%{http_code}' -H 'Connection: Upgrade' -H 'Upgrade: websocket' https://eurooffice.hus-sky.no/...` returns a `101`/upgrade response (not a plain 200), covering the spec's "a health assertion should cover it" edge (analyze U1). Confirm the editor `wss://` in a browser as a secondary check.

**Checkpoint**: The server is publicly reachable over TLS with working WebSockets.

---

## Phase 5: User Story 1 - Editing a document from Nextcloud works end-to-end (Priority: P1) 🎯 MVP goal

**Goal**: Clicking/creating a `.docx/.xlsx/.pptx` in Nextcloud opens the Euro-Office editor; edits persist; two users co-edit live; the admin connector test passes.

**Independent Test**: In Nextcloud Files create a `.docx`, edit, close, reopen (persists); open in a second session (live co-edit); admin connector test reports success.

### Implementation for User Story 1

- [x] T024 [US1] Add connector config vars to `ansible/roles/nextcloud/defaults/main.yml`: `nextcloud_eurooffice_public_url: "https://eurooffice.hus-sky.no/"` and `nextcloud_eurooffice_internal_url: "http://{{ eurooffice_ip }}/"` (port 80 — F1); add `eurooffice` to `nextcloud_apps_enable`; confirm `richdocumentscode`/`richdocuments` remain in `nextcloud_apps_remove` (FR-010).
- [x] T025 [US1] Extend `ansible/roles/nextcloud/tasks/preflight.yml` to assert Nextcloud ≥ 33 before connector work (parse `occ status` versionstring); MUST NOT proceed otherwise (FR-009).
- [x] T026 [US1] Add connector tasks to `ansible/roles/nextcloud/tasks/main.yml` (after the existing app enable/remove block) per `contracts/connector-occ.md`: `occ app:install eurooffice` (tolerate "already installed") — with the tarball fallback from T004 if needed; then idempotent `occ config:app:set eurooffice DocumentServerUrl`, `DocumentServerInternalUrl`, and `jwt_secret` (from `eurooffice_jwt_secret`, `no_log`) (FR-003, FR-007).
- [ ] T027 [US1] Deploy Nextcloud (`scripts/lab/pve-service-deploy --service nextcloud --env prod --apply`); verify `occ app:list` shows `eurooffice` enabled and no `richdocuments*` (SC-006, FR-010).
- [ ] T028 [US1] Editing verification (SC-001/002): create a `.docx` from the Files `+` menu, type, close, reopen → content persists; open in a second session → live co-edit; run the admin connector test → success.

**Checkpoint**: Full end-to-end editing works — the deliverable P1 vertical is complete.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Security-posture confirmation, monitoring registration, promotion, and docs.

- [ ] T029 [P] Security posture check (SC-005): confirm the running container has `EXAMPLE_ENABLED=false`, `JWT_ENABLED=true`, the pinned tag (not `latest`), and the JWT secret is ≥32 chars and identical on server and connector.
- [ ] T030 [US2] Deploy the monitoring stack so the new blackbox target/alert are registered (`scripts/lab/pve-service-deploy --service monitoring --env prod --apply`), then confirm the `eurooffice` liveness probe is green (SC-007, FR-008; analyze C2). Depends on T017.
- [ ] T031 Validate workflows locally with `act -l` (and `act -n -W .github/workflows/lxc-deploy-lab.yml workflow_dispatch` if feasible) and run `scripts/lab/ci-validate-iac.sh` to confirm the Tier-1 boundary (no `root@pam` in `.tf`) still holds (constitution Local Workflow Testing + Token Tiers).
- [ ] T032 Re-run the full acceptance verification set (T018/T019, T023, T027/T028, T029, T030) end-to-end against prod as the release gate.
- [ ] T033 [P] Update docs: mark `docs/backlog/058-eurooffice-deploy.md` delivered, and run `specs/062-eurooffice-deploy/quickstart.md` end-to-end as the acceptance runbook.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately. T003 (PVE headroom) gates provisioning.
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS all stories.
- **US2 (Phase 3)**: Depends on Foundational — the server must exist and be healthy first.
- **US3 (Phase 4)**: Depends on US2 (route points at a live upstream).
- **US1 (Phase 5)**: Depends on US2 + US3 (editor loads from the public URL, callback hits the LAN URL).
- **Polish (Phase 6)**: Depends on US1/US2/US3 complete. T030 (monitoring) depends on T017.

### Why the phase order differs from priority order

US1 (editing) is P1 and is the user-visible MVP, but for a layered infra deploy it is delivered
**last** because it cannot function without the running server (US2) and public route (US3). The
"MVP" here is the full P1 vertical (US2 + US3 + US1), delivered incrementally with a healthy
checkpoint after each phase.

### Within Each Story

- Preflight/asserts before deploy; template before compose-up; deploy before verify.
- Role files marked [P] (defaults, handlers, host_vars) are independent; `tasks/main.yml` depends on the template and preflight.

### Parallel Opportunities

- T007, T008, T010, T011 (Foundational, different files) can run in parallel; T006/T009 touch shared files (vars.yml / main.tf) so keep serial.
- T012, T013, T017 (US2 role scaffolding, different files) can run in parallel; T014→T015→T016 are sequential (main.yml consumes the template + preflight).
- T029, T033 (Polish, different concerns) can run in parallel.

---

## Parallel Example: Foundational

```bash
# Different files, no interdependencies — run together:
Task: "Add eurooffice to service_ips in prod/lab tfvars templates (T007)"
Task: "Create terraform/services/eurooffice/{main,outputs}.tf (T008)"
Task: "Create ansible/playbooks/eurooffice.yml (T010)"
Task: "Add eurooffice to the three workflow service dropdowns (T011)"
```

---

## Implementation Strategy

### MVP = the full P1 vertical (incremental)

1. Phase 1 Setup → confirm tag, IP, PVE RAM headroom, connector install path.
2. Phase 2 Foundational → LXC exists, pipeline knows the service.
3. Phase 3 (US2) → server `Up (healthy)`. **Checkpoint / demo: healthcheck 200.**
4. Phase 4 (US3) → reachable at `eurooffice.hus-sky.no`. **Checkpoint: TLS + wss.**
5. Phase 5 (US1) → click-to-edit from Nextcloud. **Checkpoint: round-trip + co-edit — MVP done.**
6. Phase 6 → security/monitoring/promotion/docs.

### Notes

- [P] = different files, no dependencies. [Story] label maps to spec user stories.
- Deploys run identically locally and in CI (Constitution V); PVE has unrestricted GitHub access.
- Commit after each logical group; stop at any checkpoint to validate independently.
