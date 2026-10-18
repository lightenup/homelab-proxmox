# Tasks: Consolidate Service Version Variables into group_vars

**Input**: Design documents from `/specs/047-consolidate-service-versions/`
**Prerequisites**: plan.md (required), spec.md (required for user stories)

**Tests**: No automated unit/integration tests requested. This is a variable-relocation refactor; verification is via `grep` assertions and Ansible dry-run (`--syntax-check` / `--check`), captured as explicit tasks below.

**Organization**: Tasks are grouped by user story. US1 (P1) delivers the MVP — version pins live in one file and role defaults no longer hold them.

## Path Conventions

Infrastructure-as-code repo. All edits are under `ansible/`:
- `ansible/group_vars/services/vars.yml`
- `ansible/roles/nextcloud/defaults/main.yml`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Capture a baseline so the relocation can be proven value-preserving.

- [x] T001 Record baseline values by running `grep -rn "nextcloud_version\|nextcloud_exporter_version\|immich_version\|financial_scenario_version" ansible/` and noting each current value (`nextcloud_version: "32"`, `nextcloud_exporter_version: "0.9.0"`, `immich_version: "v2.4.0"`, `financial_scenario_version: "0.1.0"`) for the final regression check.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: `group_vars` must supply the relocated values BEFORE any role default is deleted, so variable resolution never breaks at any commit.

**⚠️ CRITICAL**: T002 must complete before US1's role-default deletions (T003, T004).

- [x] T002 Add a `# Service versions` block near the top of `ansible/group_vars/services/vars.yml` (after the docker preamble, mirroring the heading style in `ansible/group_vars/monitoring/vars.yml`) containing all four pins with exact values: `nextcloud_version: "32"`, `nextcloud_exporter_version: "0.9.0"`, `immich_version: "v2.4.0"`, `financial_scenario_version: "0.1.0"`. (Old scattered `immich_version` / `financial_scenario_version` lines are removed later in T007.)

**Checkpoint**: All five version pins now resolvable from `group_vars/services/vars.yml`.

---

## Phase 3: User Story 1 - Bump a service version from a single known location (Priority: P1) 🎯 MVP

**Goal**: The three outlier pins live only in `group_vars`; no role `defaults/` file holds a service version.

**Independent Test**: `grep -rn "nextcloud_version\|nextcloud_exporter_version" ansible/roles/` returns zero matches, and the nextcloud play resolve those variables without "undefined variable" errors.

### Implementation for User Story 1

- [x] T003 [US1] Delete the `nextcloud_version` and `nextcloud_exporter_version` lines entirely from `ansible/roles/nextcloud/defaults/main.yml` (no placeholder, no comment).
- [x] T005 [US1] Verify removal: `grep -rn "nextcloud_version\|nextcloud_exporter_version" ansible/roles/` returns zero matches (satisfies SC-001).
- [x] T006 [US1] Verify resolution: <!-- requires live host — run manually: ansible-playbook --syntax-check && --check on nextcloud play --> run `ansible-playbook --syntax-check` and a `--check` dry-run of the nextcloud play (or `ansible <group> -m debug -a "var=nextcloud_version"` etc. for both) — confirm no undefined-variable errors (satisfies SC-003).

**Checkpoint**: MVP complete — version pins are single-sourced; routine upgrades need no role-defaults edits.

---

## Phase 4: User Story 2 - All version pins grouped and discoverable (Priority: P2)

**Goal**: Every service version pin sits in one consistently labeled block, with no stale duplicates left in their old per-service sections.

**Independent Test**: `ansible/group_vars/services/vars.yml` shows all five pins under the `# Service versions` block, the heading style matches `monitoring/vars.yml`, and `immich_version` / `financial_scenario_version` appear nowhere else in the file.

### Implementation for User Story 2

- [x] T007 [US2] Remove the now-duplicate `immich_version` line from the Immich section and the `financial_scenario_version` line from the Financial Scenario section of `ansible/group_vars/services/vars.yml`, so each pin is defined exactly once (inside the T002 block).
- [x] T008 [US2] Verify grouping: confirm all five pins appear under `# Service versions`, the heading matches the `monitoring/vars.yml` style, and no duplicate keys remain (satisfies SC-002).

**Checkpoint**: Both stories complete — single-sourced AND consistently grouped.

---

## Phase 5: Polish & Cross-Cutting Concerns

- [x] T009 [P] Mark `docs/backlog/consolidate-service-versions.md` as delivered (update Status from "Draft (Backlog)" and link `specs/047-consolidate-service-versions/`).
- [x] T010 Final regression check against the T001 baseline: confirm all five values are unchanged and SC-004 holds (a version bump now requires editing only `group_vars/services/vars.yml` or `group_vars/monitoring/vars.yml`, zero role-defaults edits).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately.
- **Foundational (Phase 2)**: Depends on Setup. **BLOCKS US1's deletions** (T003/T004) — group_vars must supply values first.
- **US1 (Phase 3)**: Depends on T002.
- **US2 (Phase 4)**: Depends on T002 (the block must exist before old duplicates are removed). Independent of US1's role-file edits.
- **Polish (Phase 5)**: Depends on US1 and US2 complete.

### Within / Across Stories

- T003 and T004 are [P] — different files.
- US1 (role files) and US2 (services/vars.yml duplicate removal) touch disjoint files and could proceed in parallel once T002 lands; sequential P1→P2 is the simpler default.
- T007 edits the same file as T002, so it is NOT parallel with T002.

### Parallel Opportunities

```bash
# After T002, the two role-default deletions can run together:
Task: "Delete nextcloud_version & nextcloud_exporter_version from ansible/roles/nextcloud/defaults/main.yml"
```

---

## Implementation Strategy

### MVP First (User Story 1)

1. T001 (baseline) → T002 (group_vars block) → T003/T004 (delete role defaults) → T005/T006 (verify).
2. **STOP and VALIDATE**: grep clean + dry-run resolves. This alone delivers the core value.

### Incremental Delivery

1. Setup + Foundational → all pins resolvable from group_vars.
2. US1 → role defaults gone, single-sourced (MVP) → validate.
3. US2 → duplicates removed, grouped block tidy → validate.
4. Polish → backlog marked done, final regression check.

---

## Notes

- [P] tasks = different files, no dependencies.
- Critical ordering invariant: **add to `group_vars` (T002) before deleting from role defaults (T003/T004)** so resolution never breaks mid-change.
- Values must be byte-for-byte preserved — this is a relocation, not a version bump.
- Commit after each phase; each checkpoint is independently verifiable.
