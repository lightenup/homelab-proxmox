---
description: "Task list for Financial-Scenario v2 Deploy (Stateful)"
---

# Tasks: Financial-Scenario v2 Deploy (Stateful)

**Input**: Design documents from `/specs/048-financial-scenario-v2-deploy/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: No unit/contract test tasks — this is declarative IaC. Per the constitution
(Test-Driven Changes), validation is non-destructive: `terraform validate`, `ansible --syntax-check`,
the healthcheck script, and the quickstart verification drills. Each story ends with a verification
task that exercises its acceptance scenarios.

**Organization**: Tasks are grouped by user story. US1 and US2 are both P1 and ship in the same
`0.2.2` deploy (one compose template, one playbook run); US2's verification reuses the stack US1
deploys. US3 (P2) is independent and additive.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1 / US2 / US3 (maps to spec.md user stories)
- Exact file paths included in every task.

## Path Conventions

Infrastructure repo (no `src/`/`tests/`). Real paths: `terraform/`, `ansible/roles/…`,
`ansible/group_vars/`, `ansible/playbooks/`.

---

## Phase 1: Setup (Shared Configuration)

**Purpose**: The single shared prerequisite both P1 stories depend on — pinning the new image tag.

- [x] T001 Bump `financial_scenario_version` from `0.1.0` to `0.2.2` in `ansible/group_vars/services/vars.yml` (FR-001; the preflight already rejects empty/`latest`)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: None beyond Setup. The compose-topology and role changes are each owned by the story they
serve (US1/US2), and the backup infrastructure is owned by US3. No additional cross-story blocking
work exists.

**Checkpoint**: With T001 done, user-story implementation can begin.

---

## Phase 3: User Story 1 - Upgrade in place without losing data (Priority: P1) 🎯 MVP

**Goal**: Adopt `0.2.2` and add the durable scenario-store bind-mount so saved scenarios and
reference-data edits survive the image re-pull, with no seed/clobber of an existing store.

**Independent Test**: On a running `0.1.0` stack, save a scenario, set the version to `0.2.2`, re-run
the playbook → all three containers `healthy`, GUI 200 on `:3000`, the saved scenario still listed and
openable, reference-data edits intact.

### Implementation for User Story 1

- [x] T002 [US1] Add a "ensure scenarios store directory exists" task (never seed/copy/init a DB) to `ansible/roles/financial_scenario/tasks/main.yml`, creating `{{ financial_scenario_data_dir }}/scenarios` with `state=directory`, `mode: '0755'`, `owner: root`, `group: root` — matching the existing reference-data dir task. The api container runs as **root** (confirmed by `046`, which persists reference-data writes to a `0755` root-owned bind-mount), so a `0755` root dir is writable by the container for `scenarios.db`. Guard: if a future image changes the api runtime UID (`docker inspect financial_scenario_api --format '{{.Config.User}}'` non-empty/non-root), set `owner`/`group` to that UID instead (FR-002, FR-005, D-005)
- [x] T003 [US1] Add the `api` scenario-store bind-mount `"{{ financial_scenario_data_dir }}/scenarios:/app/data"` to the `api` service in `ansible/roles/financial_scenario/templates/docker-compose.yml.j2`, with a comment documenting the `SCENARIOS_DB_PATH` override path (left unset; FR-002, FR-003, D-001)
- [ ] T004 [US1] Verify upgrade safety per `quickstart.md` §1: deploy `0.1.0`, save a scenario, bump to `0.2.2`, re-run `ansible/playbooks/financial-scenario.yml`; confirm SC-001 (data survives) and SC-002 (all healthy, GUI 200) and that `scenarios.db` appears under `{{ financial_scenario_data_dir }}/scenarios`

**Checkpoint**: US1 fully functional — upgrade is data-safe; persistence verified.

---

## Phase 4: User Story 2 - Agent-authored scenarios appear in the GUI (Priority: P1)

**Goal**: Reconfigure `mcp` as a stateless HTTP client of `api` so agent-authored and GUI-authored
scenarios share the single `api` store.

**Independent Test**: With the stack healthy, save a scenario via the gated `/mcp` endpoint → it
appears in the GUI comparison list badged agent-authored and opens with freshly computed results.

### Implementation for User Story 2

- [x] T005 [US2] Reconfigure the `mcp` service in `ansible/roles/financial_scenario/templates/docker-compose.yml.j2`: **remove** its `reference_data` bind-mount, **add** `API_BASE_URL: http://api:8000`, **add** `depends_on: api` with `condition: service_healthy`, keeping `MCP_TRANSPORT: http` and `MCP_PORT: 8001` (FR-004, D-004). Depends on T003 (same file)
- [ ] T006 [US2] Verify topology + round-trip per `quickstart.md` §2: `docker inspect financial_scenario_mcp` shows no reference-data mount and `API_BASE_URL=http://api:8000`, `mcp` healthy only after `api`; save via `/mcp` and confirm it surfaces in the GUI (SC-003)

**Checkpoint**: US1 and US2 both verified on the `0.2.2` single-engine stack.

---

## Phase 5: User Story 3 - Saved scenarios are backed up (Priority: P2)

**Goal**: Add a `financial_scenario_backup` role + systemd timer that takes a consistent (WAL-safe)
online snapshot of the scenario store to the Synology NAS over an in-guest NFS mount, with GFS
retention.

**Independent Test**: Trigger the timer → a consistent `*.tar.gz` lands on the NFS share; restoring it
over a fresh store reproduces the saved scenarios; `PRAGMA integrity_check` returns `ok`; GFS prune
keeps the expected dailies/weeklies/monthlies.

### Implementation for User Story 3

- [x] T007 [P] [US3] Add `features_mount = "nfs"` to the `financial_scenario_lxc` module call in `terraform/main.tf` (copy the jellyfin pattern; image-independent, applied host-side by the orchestrator via `pct set`) (FR-007, D-006)
- [x] T008 [P] [US3] Add backup config vars to `ansible/group_vars/services/vars.yml`: `financial_scenario_backup_path: /mnt/financial-scenario/backups`, `financial_scenario_backup_nfs_server: 192.168.1.109`, `financial_scenario_backup_nfs_export: /volume1/homelab_financial_scenario`, `*_retention_days: 7`, `*_retention_weeks: 4`, `*_retention_months: 6`, `*_schedule: "*-*-* 04:15:00"` (data-model.md)
- [x] T009 [US3] Create `ansible/roles/financial_scenario_backup/tasks/main.yml`: install `nfs-common`; idempotently mount `{{ financial_scenario_backup_nfs_server }}:{{ financial_scenario_backup_nfs_export }}` → `{{ financial_scenario_backup_path }}` with opts `rw,nolock,nofail,_netdev,x-systemd.automount` (in-role mount, NOT `shared_nfs_mount`; `nolock` avoids `rpc.statd` EPERM on a rw mount in an unprivileged LXC); deploy the script; create + enable the `financial-scenario-backup` service and timer — mirroring `ansible/roles/nextcloud_backup/tasks/main.yml` (FR-006, FR-008, D-006)
- [x] T010 [P] [US3] Create `ansible/roles/financial_scenario_backup/handlers/main.yml` with the `Reload systemd` handler (mirror `nextcloud_backup`)
- [x] T011 [P] [US3] Create `ansible/roles/financial_scenario_backup/templates/backup_financial_scenario.sh.j2`: consistent SQLite **online backup** via `docker exec financial_scenario_api python -c "...src.backup(dst)..."` (NOT raw `cp`), copy snapshot out + remove the temp `.backup-snapshot.db` from `/app/data`, tar with the rendered `docker-compose.yml`, GFS prune identical to `backup_nextcloud.sh.j2`; no-op exit 0 if no `scenarios.db` yet (FR-008, contracts/backup-restore.md)
- [x] T012 [US3] Add the `financial_scenario_backup` role to the second play in `ansible/playbooks/financial-scenario.yml` (after `financial_scenario`)
- [ ] T013 [US3] Verify backup per `quickstart.md` §0 + §4: `terraform … apply` sets the NFS feature, `showmount -e 192.168.1.109` from the LXC; trigger `financial-scenario-backup.service`; confirm a `*.tar.gz` on the share; integrity-check the extracted DB **without a host `sqlite3` dependency** — copy it into the container and run `docker exec financial_scenario_api python -c "import sqlite3,sys; sys.exit(0 if sqlite3.connect('<path>').execute('PRAGMA integrity_check').fetchone()[0]=='ok' else 1)"`; restore reproduces scenarios (SC-004), no stray `.backup-snapshot.db` left (SC-005). GFS prune is asserted by inspection (logic copied verbatim from `backup_nextcloud.sh.j2`), as weekly/monthly retention is not observable from a single run

**Checkpoint**: All three stories independently functional; saved scenarios are recoverable.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Pipeline validation, posture confirmation, and doc closure.

- [x] T014 [P] Run `terraform -chdir=terraform validate` and `ansible-playbook -i inventories/prod/hosts.yml playbooks/financial-scenario.yml --syntax-check`; if `act` + Docker available, `act -l` to confirm workflows parse and `financial-scenario` is recognized (constitution Local Workflow Testing)
- [ ] T015 [P] Verify posture unchanged per `quickstart.md` §5 (SC-006): only `gui` publishes `3000`; `/mcp` still gated; `scripts/healthcheck/financial-scenario.sh --profile lan` green; blackbox liveness green
- [x] T016 [P] Mark `docs/backlog/047-financial-scenario-v2-deploy.md` delivered and cross-link `specs/048-financial-scenario-v2-deploy/`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: T001 — no dependencies; start immediately.
- **Foundational (Phase 2)**: none.
- **US1 (Phase 3)**: depends on T001.
- **US2 (Phase 4)**: T005 depends on T003 (same compose file); verification (T006) depends on US1's deployed stack.
- **US3 (Phase 5)**: depends on T001 (running `0.2.2` stack with the `/app/data` store from T003); otherwise independent of US2.
- **Polish (Phase 6)**: after all desired stories complete.

### User Story Dependencies

- **US1 (P1)**: the MVP — independently testable after T001.
- **US2 (P1)**: shares the compose template with US1; sequence T005 after T003. Verification reuses the US1 stack.
- **US3 (P2)**: additive backup story; needs a running `0.2.2` stack (US1) but not US2.

### Within Each User Story

- US1: T002 + T003 (different files, parallelizable) → T004 verify.
- US2: T005 (after T003) → T006 verify.
- US3: T007/T008/T010/T011 parallelizable → T009 (consumes vars + script) → T012 wire playbook → T013 verify.

### Parallel Opportunities

- T002 and T003 (US1) — different files, no dependency.
- T007, T008, T010, T011 (US3) — different files.
- T014, T015, T016 (Polish) — independent.

---

## Parallel Example: User Story 3

```bash
# Different files — launch together:
Task: "Add features_mount = nfs to terraform/main.tf"                      # T007
Task: "Add backup vars to ansible/group_vars/services/vars.yml"            # T008
Task: "Create ansible/roles/financial_scenario_backup/handlers/main.yml"   # T010
Task: "Create ansible/roles/financial_scenario_backup/templates/backup_financial_scenario.sh.j2"  # T011
# Then T009 (tasks/main.yml) → T012 (wire playbook) → T013 (verify)
```

---

## Implementation Strategy

### MVP First (User Story 1)

1. T001 (Setup) → T002, T003 → T004 verify. **STOP and validate**: upgrade is data-safe.
2. Deploy/demo — this alone delivers the safe `0.2.2` upgrade with persistence.

### Incremental Delivery

1. Setup → US1 (MVP, data-safe upgrade) → demo.
2. US2 (MCP-as-client round-trip) → demo — same stack, one compose edit + re-deploy.
3. US3 (backup/restore) → demo — additive role + timer.
4. Polish (validation, posture, docs).

### Notes

- [P] = different files, no dependency. T003 and T005 both edit the compose template → sequential.
- Each story ends with a non-destructive verification task tied to its SC-### criteria.
- Commit after each task or logical group; stop at any checkpoint to validate independently.
