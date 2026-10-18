# Tasks: Self-Hosted Nextcloud Deployment

**Branch**: `034-add-nextcloud` | **Date**: 2026-02-22
**Input**: Design documents from `/specs/034-add-nextcloud/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅, quickstart.md ✅

**Tests**: Not requested — validation is via `terraform validate`, `ansible --syntax-check`, Docker healthchecks, and HTTP health probes (IaC project).

**Organization**: Tasks grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1–US7 from spec.md)
- Exact file paths included in every description

---

## Summary

- **Total tasks**: 23
- **Estimated complexity**: High (3-layer IaC deployment — Terraform + Ansible + Docker Compose; ~17 new files, ~5 modified files)
- **Parallel tracks**: 3 independent tracks in Phase 1 (Terraform wrapper, tfvars, root module); 5 parallel tasks in Phase 2 (Ansible scaffolding)
- **MVP scope**: Complete Phase 1 + Phase 2 + Phase 3 (US5) + Phase 4 (US1) → Working Nextcloud with persistent storage

---

## Phase 1: Setup (Terraform Infrastructure)

**Purpose**: Provision the Nextcloud LXC on Proxmox via Terraform, following the Jellyfin/Immich per-service wrapper pattern. No user story label — this is shared infrastructure required by all stories.

- [X] T001 Create Terraform per-service wrapper files `terraform/services/nextcloud/main.tf`, `variables.tf`, `outputs.tf`, `providers.tf` — clone Jellyfin pattern with cores=4, memory=4096, disk_gb=32, features_mount="nfs", mountpoints from service_mountpoints["nextcloud"]
- [X] T002 [P] Add `nextcloud = "192.168.20.216/24"` to service_ips and nextcloud data mountpoint block to service_mountpoints in `terraform/environments/prod.tfvars.example` and `terraform/environments/lab.tfvars.example`
- [X] T003 [P] Add nextcloud_lxc module block (cores=4, memory=4096, disk_gb=32, features_mount="nfs", mountpoints) to `terraform/main.tf` and add `nextcloud = module.nextcloud_lxc.ipv4` to services map in `terraform/outputs.tf`

---

## Phase 2: Foundational (Ansible Role Scaffolding)

**Purpose**: Create all Ansible scaffolding required before any user story implementation can proceed. These are blocking prerequisites — no user story work can begin until this phase is complete.

**⚠️ CRITICAL**: T007 and T008 (templates) must complete before T010–T012 (role tasks) can begin.

- [X] T004 [P] Create `ansible/host_vars/nextcloud.yml` with healthcheck_url (scheme: http, port: 8080, path: /login), healthcheck_profile: lan, healthcheck_expect_status: 200 — match pattern from immich.yml and jellyfin.yml
- [X] T005 [P] Append Nextcloud variable block to `ansible/group_vars/services/vars.yml`: nextcloud_version, nextcloud_ip, nextcloud_port (8080), nextcloud_install_dir, nextcloud_data_dir, nextcloud_nfs_mount, nextcloud_domain, nextcloud_db_name/user/container names, backup path/retention/schedule — NO secrets committed
- [X] T006 [P] Create `ansible/roles/nextcloud/defaults/main.yml` with all role defaults: version, port, paths, php limits, nextcloud_apps_enable list (richdocuments, richdocumentscode, deck, twofactor_totp, bruteforcesettings), nextcloud_apps_disable list (photos, weather_status, firstrunwizard, recommendations)
- [X] T007 [P] Create `ansible/roles/nextcloud/templates/docker-compose.yml.j2` with three services: nextcloud_app (nextcloud:{{ nextcloud_version }}, port {{ nextcloud_port }}:80, NFS volume for /var/www/html/data, local volume for /var/www/html, env_file: .env, depends_on db+redis), nextcloud_db (mariadb:11, local volume for /var/lib/mysql, MariaDB READ-COMMITTED command, healthcheck), nextcloud_redis (redis:7-alpine, local volume, requirepass command, healthcheck)
- [X] T008 [P] Create `ansible/roles/nextcloud/templates/.env.j2` (mode 0600) with MYSQL_HOST, MYSQL_DATABASE, MYSQL_USER, MYSQL_PASSWORD, MYSQL_ROOT_PASSWORD, REDIS_PASSWORD, NEXTCLOUD_ADMIN_USER, NEXTCLOUD_ADMIN_PASSWORD, NEXTCLOUD_TRUSTED_DOMAINS, TRUSTED_PROXIES, OVERWRITEPROTOCOL=http, OVERWRITECLIURL, PHP_MEMORY_LIMIT, PHP_UPLOAD_LIMIT — all using Jinja {{ var }} rendering
- [X] T009 Run `terraform fmt -check` and `terraform validate` on `terraform/services/nextcloud/` and root `terraform/` module; fix any formatting or validation errors

**Checkpoint**: Scaffolding complete — user story implementation can begin.

---

## Phase 3: US5 — Data Persistence on Network Storage (Priority: P1)

**Goal**: Ensure all user-uploaded files are stored on the NAS and survive container rebuilds. NFS preflight validation guards against data loss from missing mounts.

**Independent Test**: Upload a file → destroy and recreate the nextcloud container → verify the file still exists in the NAS at `/mnt/nas/homelab_nextcloud/data/`.

- [X] T010 [P] [US5] Create `ansible/roles/nextcloud/tasks/preflight.yml` with: conditional NFS mount check at `{{ nextcloud_nfs_mount }}` (stat + assert), writable mount check (touch + cleanup), Docker daemon running check (service state), disk space ≥ 10 GB on /opt (df), required variable assertions (nextcloud_db_password, nextcloud_redis_password, nextcloud_admin_password, nextcloud_nfs_mount)
- [X] T011 [P] [US5] Create `ansible/roles/nextcloud/handlers/main.yml` with `Restart nextcloud` handler using `community.docker.docker_compose_v2` (project_src: `{{ nextcloud_install_dir }}`, state: restarted)

**Checkpoint**: NAS protection and restart handler in place. US5 acceptance: file exists after container rebuild.

---

## Phase 4: US1 — File Sync and Share (Priority: P1)

**Goal**: Deploy the Nextcloud stack so users can upload, download, organize, and sync files via web UI and WebDAV sync clients.

**Independent Test**: Log in via web browser → upload a file → download it from a different browser session → verify it appears in the NAS at `/mnt/nas/homelab_nextcloud/data/admin/files/`.

- [X] T012 [US1] Create `ansible/roles/nextcloud/tasks/main.yml` with full deployment flow: (1) include preflight.yml, (2) create directories (install_dir, html, mariadb, redis, nfs/data, nfs/backups), (3) template docker-compose.yml.j2 + notify restart, (4) template .env.j2 mode 0600 + notify restart, (5) docker_compose_v2 state=present pull=always, (6) wait_for port {{ nextcloud_port }} timeout=300, (7) uri poll for /status.php `"installed":true` (retries=30, delay=10), (8) loop occ app:install + app:enable for each item in nextcloud_apps_enable (ignore already-installed errors), (9) loop occ app:disable for each item in nextcloud_apps_disable (ignore not-installed errors), (10) occ config:system:set for redis host/port/password/timeout, memcache.local/distributed/locking, filelocking.enabled, default_phone_region, maintenance_window_start, (11) occ config:system:set auth.bruteforce.protection.whitelist 0 --value="192.168.0.0/16", (12) final HTTP health check to /status.php (changed_when: false for all occ config commands)

**Checkpoint**: Nextcloud is deployed and accessible. US1 acceptance: file upload/download/share works via web UI and WebDAV.

---

## Phase 5: US6 — Service Reliability and Manageability (Priority: P2)

**Goal**: Nextcloud starts automatically after reboot, can be deployed idempotently, and integrates with existing infrastructure-as-code deployment workflow (site.yml → services.yml chain).

**Independent Test**: Re-run `ansible-playbook playbooks/nextcloud.yml` on a running instance → verify no unnecessary changes (0 changed tasks, 0 failed). Reboot LXC → verify Nextcloud responds within 3 minutes.

- [X] T013 [P] [US6] Create `ansible/playbooks/nextcloud.yml` with two plays: (1) `hosts: nextcloud, roles: [lxc_base]`; (2) `hosts: nextcloud, vars: {nextcloud_require_nas_mount: "{{ (deploy_environment | default('prod')) != 'lab' }}"}, roles: [geerlingguy.docker, nextcloud, nextcloud_backup]`
- [X] T014 [P] [US6] Create `ansible/playbooks/services.yml` aggregating confirmed-existing service playbooks: import immich.yml (tags: immich), import jellyfin.yml (tags: jellyfin), import nextcloud.yml (tags: nextcloud) — this file resolves the missing import referenced in site.yml
- [X] T015 [US6] Verify `ansible/playbooks/site.yml` already contains `import_playbook: services.yml` and will correctly chain through the newly created services.yml → nextcloud.yml — no modification to site.yml expected; run `ansible-playbook --syntax-check playbooks/site.yml` to confirm

**Checkpoint**: Full deployment chain works. US6 acceptance: idempotent re-deploy and auto-start after reboot confirmed.

---

## Phase 6: US3 — Secure Access and Account Management (Priority: P2)

**Goal**: Nextcloud is accessible through the Caddy reverse proxy with correct header forwarding, brute-force protection is active, and 2FA is available for all users.

**Independent Test**: Access `http://nextcloud.local` through the reverse proxy → verify the login page loads with correct host headers. Attempt 6 consecutive login failures → verify subsequent attempts are blocked/delayed. Enable TOTP 2FA on admin account → verify second factor is required at next login.

- [X] T016 [P] [US3] Create `ansible/roles/reverse_proxy/templates/nextcloud.caddy.j2` with `http://nextcloud.local { reverse_proxy {{ nextcloud_ip }}:{{ nextcloud_port }} { header_up X-Forwarded-Proto http; header_up X-Real-IP {remote_host}; header_up X-Forwarded-For {remote_host} } }` — standalone valid Caddyfile that can be validated by `caddy validate`
- [X] T017 [US3] Add Nextcloud Caddy deployment task to `ansible/roles/reverse_proxy/tasks/main.yml` following the exact Immich pattern: template src=nextcloud.caddy.j2, dest={{ caddy_conf_dir }}/nextcloud.caddy, mode=0644, validate="caddy validate --adapter caddyfile --config %s", notify "Restart caddy"

**Checkpoint**: Reverse proxy routes `http://nextcloud.local` to Nextcloud. US3 acceptance: proxy access works, brute-force blocks after failures, TOTP 2FA prompts correctly.

---

## Phase 7: US7 — Backup and Restore (Priority: P2)

**Goal**: Database contents and config.php are backed up daily to the NAS with GFS retention. Backups enable full recovery of user accounts, shares, and file metadata after data loss.

**Independent Test**: Manually trigger `/usr/local/bin/backup_nextcloud.sh` → verify `.tar.gz` file created in `/mnt/nextcloud/backups/` → drop the database → restore from backup SQL → restart service → verify user accounts and file metadata are intact.

- [X] T018 [P] [US7] Create `ansible/roles/nextcloud_backup/tasks/main.yml` with: (1) ensure backup directory exists at `{{ nextcloud_backup_path }}`, (2) template backup script to `/usr/local/bin/backup_nextcloud.sh` mode 0755, (3) deploy `nextcloud-backup.service` systemd unit (Type=oneshot), (4) deploy `nextcloud-backup.timer` unit (OnCalendar={{ nextcloud_backup_schedule }}), (5) enable + start timer, (6) notify `Reload systemd` handler on unit changes
- [X] T019 [P] [US7] Create `ansible/roles/nextcloud_backup/templates/backup_nextcloud.sh.j2` with: set -euo pipefail, source .env from {{ nextcloud_install_dir }} for MYSQL_PASSWORD, trap maintenance:mode --off on EXIT (ensures cleanup on failure), enable maintenance mode via occ, mysqldump --single-transaction --default-character-set=utf8mb4, docker cp config.php, compress to `nextcloud-backup-$(date +%Y%m%d-%H%M%S).tar.gz` in {{ nextcloud_backup_path }}, GFS retention pruning (7 daily / 4 weekly / 6 monthly), exit non-zero on failure
- [X] T020 [P] [US7] Create `ansible/roles/nextcloud_backup/handlers/main.yml` with `Reload systemd` handler using `ansible.builtin.systemd` (daemon_reload: true) — matches immich_backup handler pattern

**Checkpoint**: Daily backup timer active. US7 acceptance: backup file created, restore from SQL recovers all user data.

---

## Phase 8: US2 — Collaborative Document Editing (Priority: P2)

**Goal**: Users can create and collaboratively edit office documents (word processing, spreadsheets, presentations) and Markdown notes directly in the browser using the built-in Collabora CODE engine.

**Independent Test**: Log in → create a new .docx document → verify the Nextcloud Office editor opens in-browser → type text → reopen document → verify changes persisted. Open same document in two browser sessions simultaneously → verify edits appear within 5 seconds in both sessions.

- [X] T021 [US2] Verify `richdocuments` and `richdocumentscode` appear in `nextcloud_apps_enable` list in `ansible/roles/nextcloud/defaults/main.yml`, and that `occ app:install richdocuments` + `occ app:install richdocumentscode` commands are present in `ansible/roles/nextcloud/tasks/main.yml` — these are the built-in CODE server apps that deliver collaborative editing (FR-006, FR-007)

**Checkpoint**: Collaborative editing configured. US2 acceptance: in-browser document editor opens, simultaneous edits visible within 5 seconds.

---

## Phase 9: US4 — Project Tracking with Kanban Boards (Priority: P3)

**Goal**: Users can create Kanban boards with custom columns and cards for lightweight project tracking, integrated with the Nextcloud workspace.

**Independent Test**: Log in → navigate to the Deck app → create a new board with two columns → add a card → drag it to the other column → reload page → verify card position persisted. Share board with a second user → verify second user can view and interact with the board.

- [X] T022 [US4] Verify `deck` appears in `nextcloud_apps_enable` list in `ansible/roles/nextcloud/defaults/main.yml`, and that `occ app:install deck` command is present in `ansible/roles/nextcloud/tasks/main.yml` — Deck provides the Kanban board functionality (FR-013)

**Checkpoint**: Deck app configured. US4 acceptance: board creation, card management, and cross-user sharing all work.

---

## Final Phase: Documentation and Polish

**Purpose**: Update the network registry with the new service hostname, ensuring operational documentation stays current.

- [X] T023 [P] Add row `| nextcloud.local | 192.168.20.216 | Nextcloud Cloud Storage |` to the addressing table in `docs/naming-and-mdns.md` following the existing row format

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately; T001, T002, T003 all parallel-safe
- **Foundational (Phase 2)**: No dependencies — T004–T008 all parallel-safe; T009 (validation) depends on T001–T003
- **US5 (Phase 3)**: T010, T011 parallel-safe, no blocking prerequisite beyond T007 (template must exist first)
- **US1 (Phase 4)**: T012 depends on T010, T011 (preflight + handler must exist) and T006, T007, T008 (role scaffolding)
- **US6 (Phase 5)**: T013, T014 parallel-safe; T015 depends on T014; all depend on T012
- **US3 (Phase 6)**: T016 parallel-safe; T017 depends on T016; T016 depends on T005 (nextcloud_ip var)
- **US7 (Phase 7)**: T018, T019, T020 all parallel-safe; depend on T005 (vars) and T012 (container names)
- **US2 (Phase 8)**: T021 depends on T006 and T012 (verification of already-written files)
- **US4 (Phase 9)**: T022 depends on T006 and T012 (verification of already-written files)
- **Documentation (Final)**: T023 independent — parallel-safe, no code dependencies

### Dependency Graph

```
T001 ──────────────────┐
T002 ──────────────────┤
T003 ──────────────────┼──► T009 (Terraform validation)
                       │
T004 ──────────────────┤
T005 ──────────────────┤
T006 ──────────────────┤
T007 ──────────────────┤──► T010, T011 (preflight + handler)
T008 ──────────────────┘         │
                                 └──► T012 (tasks/main.yml)
                                           │
                                    ┌──────┴──────┐
                                    ▼             ▼
                              T013, T014     T018, T019, T020
                                    │         (Backup role)
                                    ▼
                                  T015          │
                                               ▼
                              T016 ──► T017   T021, T022
                              (Caddy)         (Verify phases)

T023 ──── (independent, no deps)
```

### Parallel Batches

| Batch | Tasks | Precondition |
|-------|-------|--------------|
| Batch 1 | T001, T002, T003, T004, T005, T006, T007, T008, T023 | None — run immediately |
| Batch 2 | T009, T010, T011, T016 | After Batch 1 |
| Batch 3 | T012, T017 | After Batch 2 |
| Batch 4 | T013, T014, T018, T019, T020 | After Batch 3 |
| Batch 5 | T015, T021, T022 | After Batch 4 |

---

## Parallel Execution Examples

### Parallel Example: Phase 1 (Terraform Setup)

```bash
# All three Terraform tasks are independent files — run together:
Task: T001 — Create terraform/services/nextcloud/ (4 files)
Task: T002 — Update prod.tfvars.example + lab.tfvars.example
Task: T003 — Update terraform/main.tf + terraform/outputs.tf
```

### Parallel Example: Phase 2 (Ansible Scaffolding)

```bash
# All five scaffolding tasks touch different files — run together:
Task: T004 — ansible/host_vars/nextcloud.yml
Task: T005 — ansible/group_vars/services/vars.yml (append)
Task: T006 — ansible/roles/nextcloud/defaults/main.yml
Task: T007 — ansible/roles/nextcloud/templates/docker-compose.yml.j2
Task: T008 — ansible/roles/nextcloud/templates/.env.j2
```

### Parallel Example: Phase 7 (Backup Role)

```bash
# Three backup role files are independent — run together:
Task: T018 — ansible/roles/nextcloud_backup/tasks/main.yml
Task: T019 — ansible/roles/nextcloud_backup/templates/backup_nextcloud.sh.j2
Task: T020 — ansible/roles/nextcloud_backup/handlers/main.yml
```

---

## Traceability Matrix

| Requirement | Tasks |
|-------------|-------|
| FR-001 (web file management) | T007, T012 |
| FR-002 (file versioning) | T012 (Nextcloud built-in, enabled by deployment) |
| FR-003 (trash bin) | T012 (Nextcloud built-in) |
| FR-004 (sharing) | T012 (Nextcloud built-in) |
| FR-005 (WebDAV) | T012 (Nextcloud built-in) |
| FR-006 (collaborative editing) | T006, T012, T021 |
| FR-007 (multi-user editing <5s) | T007 (Redis config), T012 (CODE + Redis occ), T021 |
| FR-008 (Markdown editing) | T012 (text app, bundled by default) |
| FR-009 (user management) | T012 (Nextcloud built-in) |
| FR-010 (2FA TOTP) | T006, T012 (twofactor_totp app) |
| FR-011 (brute-force protection) | T006, T012 (bruteforcesettings + occ whitelist) |
| FR-012 (reverse proxy) | T016, T017 |
| FR-013 (Kanban/Deck) | T006, T012, T022 |
| FR-014 (user data on NAS) | T001, T002, T003, T007 (NFS volume mapping) |
| FR-014a (DB survives rebuild) | T007 (local mariadb volume), T018, T019 |
| FR-015 (auto-start) | T001, T003 (onboot=true in module), T007 (restart: always) |
| FR-016 (idempotent deploy) | T012 (idempotent occ), T013, T014 |
| FR-017 (version upgrades) | T005, T006 (version var), T012 (pull: always) |
| FR-018 (dedicated LXC) | T001, T002, T003 |
| FR-019 (rate limiting) | T007 (Redis), T012 (trusted_proxies occ config) |
| FR-020 (excluded apps disabled) | T006, T012 (apps_disable list) |
| FR-021 (backup) | T018, T019, T020 |
| FR-022 (restore) | T018, T019 (backup enables restore procedure) |

---

## Implementation Strategy

### MVP (User Stories 1 and 5 Only)

1. Complete Phase 1 (T001–T003) — Terraform provisions the LXC
2. Complete Phase 2 (T004–T009) — Ansible scaffolding ready
3. Complete Phase 3 (T010–T011) — NAS protection in place
4. Complete Phase 4 (T012) — Nextcloud deployed and accessible
5. **VALIDATE**: Upload file, confirm on NAS, test WebDAV sync
6. Deploy/demo as functional private cloud storage

### Incremental Delivery

After MVP:
1. Add Phase 5 (US6) → Idempotent deployment + site.yml integration
2. Add Phase 6 (US3) → Reverse proxy access + security hardening
3. Add Phase 7 (US7) → Daily automated backups
4. Add Phase 8 (US2) → Verify collaborative editing works
5. Add Phase 9 (US4) → Verify Kanban boards work
6. Add Final Phase → Documentation current

### Syntax Validation Gates

Before marking implementation complete, run:
```bash
# Terraform
cd terraform && terraform fmt -check && terraform validate

# Ansible syntax
cd ansible && ansible-playbook --syntax-check playbooks/nextcloud.yml
cd ansible && ansible-playbook --syntax-check playbooks/services.yml
cd ansible && ansible-playbook --syntax-check playbooks/site.yml
```

---

## Constitution Check

| Principle | Status | Evidence |
|-----------|--------|----------|
| I. Spec-Driven Workflow | ✅ PASS | Every task traces to FR/US IDs in spec.md; traceability matrix complete |
| II. Secrets Policy | ✅ PASS | .env.j2 rendered with mode 0600; secrets as Ansible vars (runtime-supplied); no secrets in compose or defaults |
| III. Separation of Concerns | ✅ PASS | Terraform: LXC existence/sizing/NFS; Ansible: in-LXC config; Docker Compose: service runtime |
| Provider Strategy | ✅ PASS | Existing `telmate/proxmox = 2.9.11` via lxc_service module — no provider change |
| Networking | ✅ PASS | Static IP `192.168.20.216/24` in service_ips map — centralized in tfvars |
| Access Control | ✅ PASS | SSH via Terraform-injected public keys; Ansible as root (homelab tradeoff) |
| State Management | ✅ PASS | Local Terraform state on PVE host — no remote state introduction |
| Storage | ✅ PASS | NFS from Synology for user data; local disk for MariaDB (per NFS gotchas) |
| Services Model | ✅ PASS | One LXC (`nextcloud-lxc`) running Docker Compose with 3 containers |
| Test-Driven Changes | ✅ PASS | Preflight checks, Docker healthchecks, HTTP probes, terraform validate, ansible --syntax-check |
| Repo Layout | ✅ PASS | `terraform/services/nextcloud/`, `ansible/roles/nextcloud/`, `specs/034-*` |
