# Tasks: Nextcloud Major Upgrade 32 → 34

**Input**: Design documents from `specs/060-nextcloud-upgrade-33-34/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, quickstart.md

**Tests**: none requested. This is an operational upgrade; the "tests" are non-destructive `occ`
assertions and the restore drill, generated below as implementation tasks (not a separate TDD phase).

**Organization**: grouped by user story. Note the dependency ordering — US1 (the upgrade, P1) is
sequenced **after** US2 (P1) and US3 (P2) because each hop must be drill-fenced (US2) and the
built-in office editor must be uninstalled before the compat pass (US3).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US1 / US2 / US3 (Setup, Foundational, Polish carry no story label)

---

## Phase 1: Setup (baseline)

**Purpose**: Establish and record the known-good pre-feature state.

- [x] T001 Record baseline health: `docker exec -u www-data nextcloud_app php occ status` on LXC 105 reports `versionstring 32.x`, `maintenance:false`, `needsDbUpgrade:false` — capture as the pre-feature good state.
- [x] T002 [P] Confirm the Synology NFS mounts are present rw on the nextcloud LXC: `/mnt/nextcloud/backups` and `/mnt/nextcloud/data`.
- [x] T003 [P] Capture a data sentinel for SC-002: record a known user's file checksum (and `occ` user/file counts) to re-compare after each hop.

---

## Phase 2: Foundational (blocking safety gate)

**Purpose**: Harden the `nextcloud` role so every subsequent deploy (US1 hops and the US3 apply)
verifies a clean upgrade. **⚠️ Must complete before any hop.**

- [x] T004 Add a post-recreate **upgrade-verification block** to `ansible/roles/nextcloud/tasks/main.yml`, placed after "Wait for Nextcloud installation to complete" and **before** the app-config `occ` steps: run idempotent `occ upgrade`; `occ maintenance:mode --off` if stuck; then `occ status` and assert `versionstring` starts with `{{ nextcloud_version }}`, `maintenance` is false, and `needsDbUpgrade` is false — fail the play otherwise.
- [x] T005 In the same file, raise the post-recreate readiness timeout (the `status.php` `until` retries/delay) to tolerate a longer `occ upgrade` DB migration.
- [x] T006 Validate the hardened role is a **no-op** against the live 32 instance: deploy `nextcloud` with the pin unchanged at `32`; the verification block passes and reports no upgrade change (idempotence confirmed before any hop).

**Checkpoint**: safety gate in place; deploys now fail loudly on a dirty upgrade.

---

## Phase 3: User Story 2 - Backup taken and restore proven before each hop (Priority: P1)

**Goal**: A verified, on-demand rollback point exists and can fence each hop.
**Independent Test**: Run the drill against the live 32 instance — a fresh artefact is produced,
its DB dump imports into a scratch database, the sentinel matches, and the rollback artefact path is
printed. No upgrade required.

- [x] T007 [US2] Create `scripts/nextcloud/restore_drill.sh`: (1) trigger `nextcloud-backup.service` to force a fresh artefact; (2) select the newest `/mnt/nextcloud/backups/nextcloud-backup-*.tar.gz`; (3) start a scratch `mariadb:11` container; (4) import the artefact's DB dump; (5) assert import rc=0 and a sentinel (`oc_users` row count > 0, matching the live instance); (6) print `ROLLBACK_ARTEFACT=<path>`; (7) tear down the scratch DB; (8) exit non-zero (fail-closed) if the NFS target is unreachable.
- [x] T008 [US2] Add a documented **live-restore** procedure (via `--help` or a header comment in `scripts/nextcloud/restore_drill.sh`) describing how to restore an artefact's DB dump into the live MariaDB for the FR-010 rollback.
- [x] T009 [US2] Run `scripts/nextcloud/restore_drill.sh` against the live 32 instance; confirm `Verification Status: PASS`, sentinel match, and `ROLLBACK_ARTEFACT` printed; confirm it runs identically from a laptop and via CI (Dual-Provisioning Parity, constitution V).

**Checkpoint**: rollback proven; hops can be fenced.

---

## Phase 4: User Story 3 - App compatibility reconciled; built-in editor removed (Priority: P2)

**Goal**: The flaky built-in office editor is uninstalled and remaining apps are confirmed
upgrade-compatible.
**Independent Test**: Apply the role to the live 32 instance — `occ app:list` shows
`richdocuments`/`richdocumentscode` absent and the other enabled apps present/healthy. No upgrade
required.

- [x] T010 [P] [US3] In `ansible/roles/nextcloud/defaults/main.yml`: remove `richdocuments` and `richdocumentscode` from `nextcloud_apps_enable`; add `nextcloud_apps_remove: [richdocumentscode, richdocuments]` (uninstall the connector last).
- [x] T011 [US3] In `ansible/roles/nextcloud/tasks/main.yml`: add an **uninstall loop** over `nextcloud_apps_remove` running `occ app:disable` then `occ app:remove` (idempotent — tolerate "not installed"/"No such app"), after the existing enable/disable tasks. (Depends on T010.)
- [x] T012 [US3] In the same file, add a **post-hop app-compat assertion**: `occ app:update --all`, then `occ app:list` — fail if any enabled app is disabled-by-incompatibility (FR-007). (Depends on T004 placement.)
- [x] T013 [US3] Apply the `nextcloud` role to the live 32 instance; assert `occ app:list` shows `richdocuments*` absent and `deck`/`calendar`/`weather_status`/`twofactor_totp`/`bruteforcesettings` present and healthy.

**Checkpoint**: built-in CODE gone; app set clean on 32.

---

## Phase 5: User Story 1 - Nextcloud reaches 34 healthy, data intact (Priority: P1) 🎯

**Goal**: The instance is on major 34, out of maintenance mode, with all data intact.
**Independent Test**: After both hops, `occ status` reports 34.x/healthy, the sentinel file is
byte-identical, and `nextcloud.hus-sky.no` returns 302.
**Depends on**: Phase 2 (verification gate), US2 (drill), US3 (app removal) all complete.

- [x] T014 [US1] **Hop 1 pre**: run `scripts/nextcloud/restore_drill.sh`; record the printed `ROLLBACK_ARTEFACT` as the hop-1 rollback point (FR-002/FR-003). → `/mnt/nextcloud/backups/nextcloud-backup-20260709-164928.tar.gz`
- [x] T015 [US1] **Hop 1 bump**: set `nextcloud_version: "33"` in `ansible/group_vars/services/vars.yml`; land via the `gh`-API PR path → merge (Zscaler blocks `git push`).
- [x] T016 [US1] **Hop 1 deploy**: run `Prod 1 - LXC Promote` (service=nextcloud, ref=main), then `Prod 2 - LXC Apply` (promotion_run_id=<id>, confirm_apply_prod=deploy-prod).
- [x] T017 [US1] **Hop 1 verify**: `occ status` → 33.x, maintenance:false, needsDbUpgrade:false; `occ app:update --all` clean; `curl https://nextcloud.hus-sky.no/` → 302; sentinel (T003) intact; record the migration duration to size hop 2. → 33.0.6 healthy, users=2, URL 302, migration ≈15s.
- [x] T018 [US1] **Hop 2 pre**: run `scripts/nextcloud/restore_drill.sh`; record the hop-2 `ROLLBACK_ARTEFACT`. → `/mnt/nextcloud/backups/nextcloud-backup-20260709-172226.tar.gz`
- [x] T019 [US1] **Hop 2 bump**: set `nextcloud_version: "34"`; land via the `gh`-API PR path → merge.
- [x] T020 [US1] **Hop 2 deploy**: `Prod 1 - LXC Promote` then `Prod 2 - LXC Apply` for `nextcloud`.
- [x] T021 [US1] **Hop 2 verify**: `occ status` → 34.x + all gates; `nextcloud.hus-sky.no` → 302; sentinel intact; a spot-check of users/files/shares present (SC-001, SC-002, SC-005). → 34.0.1 healthy, users=2/files=8698/shares=3, URL 302.

**Checkpoint**: instance healthy on 34, data intact.

---

## Phase 6: Polish & Cross-Cutting

- [x] T022 [P] SC-006 hand-off: dry `docker exec -u www-data nextcloud_app php occ app:install eurooffice --keep-disabled` — confirm no "not compatible" error (dependency ≥33 satisfied); do **not** enable it (that is feature `058`). → Satisfied by evidence: running **34.0.1** is inside the connector's declared `min 33 / max 35` window (research.md). The literal install-dry-run is a prod write deferred to feature 058 (which installs the connector anyway).
- [x] T023 [P] Confirm the reverse proxy is untouched (`/etc/caddy/conf.d/nextcloud.caddy` unchanged on proxy 108) and the Nextcloud blackbox/monitoring liveness is green (SC-005).
- [x] T024 [P] Update `docs/backlog/backlog.md`: mark `057-nextcloud-upgrade-33-34` as In progress / Delivered and reference the feature dir `specs/060-nextcloud-upgrade-33-34/`.
- [x] T025 Push branch `060-nextcloud-upgrade-33-34` to the remote via the `gh`-API path and open its PR (Zscaler blocks `git push`). → PR #186

---

## Dependencies & Execution Order

### Phase dependencies

- **Setup (P1)** → no deps.
- **Foundational (P2)** → after Setup; **blocks US1 and the US3 apply** (both run the role).
- **US2 (Phase 3)** → after Setup; independent of Foundational (script only). Should land before US1.
- **US3 (Phase 4)** → after Foundational (its apply uses the verification gate).
- **US1 (Phase 5)** → after Foundational **and** US2 **and** US3.
- **Polish (Phase 6)** → after US1.

### Story dependency note

US1 is P1 but intentionally last among the story phases: an upgrade hop is only allowed once it is
drill-fenced (US2) and the incompatible built-in editor is gone (US3). US2 and US3 are each
independently testable on the live 32 instance without performing any upgrade.

### Parallel opportunities

- Setup: T002, T003 in parallel.
- US3: T010 (defaults edit) is independent of the US2 script work; T011/T012 depend on T010/T004.
- Polish: T022, T023, T024 in parallel.
- With capacity, US2 (T007–T009) and US3 (T010–T013) can proceed in parallel after Foundational.

---

## Implementation Strategy

### MVP (first shippable increment)

Setup → Foundational → US2 → US3 → **US1 hop 1 (T014–T017)**: a healthy, drill-fenced landing on
**33** with the built-in editor removed. Stop and validate here before hop 2.

### Incremental delivery

1. Foundational safety gate + US2 drill + US3 cleanup — all validated on the live 32 instance,
   independently, with no upgrade risk.
2. US1 hop 1 (32→33) → verify → **MVP**.
3. US1 hop 2 (33→34) → verify → feature complete; hand off to `058` (SC-006).

---

## Notes

- `[P]` = different files, no incomplete-task dependency.
- Each hop is a full gated promote→apply; do not start a hop until the previous one verifies.
- Commit role/script changes via the `gh`-API path (Zscaler blocks `git push`); deploys are
  unaffected.
- Rollback for any failed hop: restore the recorded `ROLLBACK_ARTEFACT` DB dump + revert the pin to
  the prior major (FR-010; procedure in `restore_drill.sh --help`).
