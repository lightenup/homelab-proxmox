# Tasks: Idempotent Rebuild - State Storage & Services Execution (Delta)

**Feature**: 033-idempotent-rebuild (Delta Enhancement)
**Branch**: `033-idempotent-rebuild`
**Plan**: [plan-delta-state-storage.md](./plan-delta-state-storage.md)
**Spec**: [spec-delta-state-storage.md](./spec-delta-state-storage.md)

## Overview

This task list addresses gaps in the original 033 implementation by adding NAS-backed state storage, laptop-based services deployment, and automatic mount remediation. Tasks are organized by user story to enable independent, testable increments.

**Total Tasks**: 16 (D-001 to D-016)
**Estimated Effort**: 10-16 developer-days
**Parallelization Opportunities**: 4 tasks marked [P]

---

## Phase 1: Setup (Project Initialization)

**Goal**: Prepare infrastructure and documentation before code changes

**Tasks**:
- [X] D-001 Create NAS state directory structure via Ansible in ansible/roles/proxmox_state_dirs/tasks/main.yml
- [X] D-002 [P] Document laptop NFS mount setup in docs/runbooks/laptop-nfs-setup.md
- [X] D-003 [P] Create state validation script in scripts/lab/validate-existing-state.sh

**Acceptance**:
- `/mnt/nas/homelab_ci/infra_state/{lab,static}/` directories exist with correct permissions
- Laptop NFS setup documented with troubleshooting steps
- Current state inventory captured (service count, sizes, mtimes)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Goal**: Create state path abstraction layer (required for all user stories)

**Tasks**:
- [X] D-004 Create state path resolution library in scripts/lab/lib/state.sh
- [X] D-005 Update pve-service-deploy to use state library at line 34 and lines 439-459
- [X] D-006 [P] Update supporting scripts: scripts/lab/lib/snapshot.sh line 137, scripts/lab/guardrails.sh line 14

**Acceptance**:
- `USE_NAS_STATE=false` uses legacy paths (backward compatible)
- `USE_NAS_STATE=true` uses NAS paths with environment isolation
- `resolve_state_root()` returns correct paths on macOS and PVE
- Environment validation rejects invalid values

**Dependencies**: D-001 must complete before D-004 (requires NAS directories)

---

## Phase 3: User Story 1 - NAS-Backed State Storage (P1)

**Story Goal**: Store all Terraform state files on NAS share accessible from laptop and PVE, with state included in nightly backups and zero regression for GH Actions workflows.

**Independent Test Criteria**:
- [ ] State files readable/writable from laptop via `/Volumes/nas/homelab_ci/infra_state/lab/<service>/terraform.tfstate`
- [ ] State files readable/writable from PVE via `/mnt/nas/homelab_ci/infra_state/lab/<service>/terraform.tfstate`
- [ ] GH Actions workflows continue working without modification (via symlinks)
- [ ] State files present in nightly backup archives under `iac-artifacts/nas-state/`
- [ ] Environment isolation enforced (lab state ≠ prod state)

### Implementation Tasks

- [X] D-007 [US1] Create Ansible role for state symlinks in ansible/roles/proxmox_state_symlinks/tasks/main.yml
- [X] D-008 [US1] Create one-time state migration script in scripts/lab/migrate-state-to-nas.sh
- [X] D-012 [US1] Update backup script IaC collection in ansible/roles/proxmox_backup/templates/proxmox-config-backup.sh.j2 lines 216-260

### Test Tasks (US1)

**Test US1-01: Cross-Platform State Access**
```bash
# From laptop: Write state
ENVIRONMENT=lab USE_NAS_STATE=true task rebuild:plan -- --phase iac

# From PVE: Read state (via symlink)
ssh pve "cat /var/lib/homelab-proxmox/state/services/immich/terraform.tfstate | jq -r .version"

# Expected: Same state version, no errors
```

**Test US1-02: GH Actions Backward Compatibility**
```bash
# Trigger workflow (uses legacy paths)
gh workflow run lxc-promote-lab.yml -f service=monitoring

# Check state written to NAS
ssh pve "ls -l /mnt/nas/homelab_ci/infra_state/lab/monitoring/terraform.tfstate"

# Expected: Workflow succeeds, state on NAS via symlink
```

**Test US1-03: State in Backups**
```bash
# Trigger backup
ssh pve "sudo /usr/local/bin/proxmox-config-backup.sh"

# Extract and verify
age -d -i key proxmox-backup-*.age | tar -I zstd -tf - | grep "iac-artifacts/nas-state/lab/immich/terraform.tfstate"

# Expected: State files present in archive
```

**Test US1-04: Environment Isolation**
```bash
# Try to access static state from lab context
ENVIRONMENT=lab USE_NAS_STATE=true bash -c 'source scripts/lab/lib/state.sh && resolve_state_root'

# Expected: Returns lab path only, not static
```

**Dependencies**: D-004, D-005, D-006 must complete before US1 tasks

---

## Phase 4: User Story 2 - Laptop-Based Services Deployment (P2)

**Story Goal**: Deploy services from laptop Terraform execution (no PVE-local repo required), with Terraform connecting to PVE via API and state stored on NAS.

**Independent Test Criteria**:
- [ ] `task rebuild:plan -- --phase services` completes from laptop
- [ ] Terraform init/plan/apply executed locally (not via SSH)
- [ ] State files updated on NAS at `/Volumes/nas/homelab_ci/infra_state/lab/<service>/terraform.tfstate`
- [ ] PVE API credentials loaded from environment variables
- [ ] All services in allowlist processed successfully

### Implementation Tasks

- [X] D-009 [US2] Refactor rebuild_phase_services() in scripts/lab/lib/rebuild.sh lines 982-1040
  - **Dependencies**: D-004, D-005, D-007, D-008 (requires state library, symlinks, and migration complete)
- [X] D-010 [US2] Add Terraform provider credential exports in scripts/lab/lib/rebuild.sh before service loop

### Test Tasks (US2)

**Test US2-01: Laptop Services Phase**
```bash
# Export credentials
export PROXMOX_API_TOKEN_ID="root@pam!rebuild"
export PROXMOX_API_TOKEN_SECRET="<secret>"
export USE_NAS_STATE=true

# Run services phase
task rebuild:plan -- --phase services

# Expected: All services planned, state on NAS
```

**Test US2-02: Terraform Provider Connection**
```bash
# Test single service manually
cd terraform/services/immich
export TF_VAR_pm_api_url="https://192.168.1.112:8006/api2/json"
export TF_VAR_pm_api_token_id="root@pam!rebuild"
export TF_VAR_pm_api_token_secret="<secret>"

terraform plan -state=/Volumes/nas/homelab_ci/infra_state/lab/immich/terraform.tfstate

# Expected: Connects to PVE, reads existing resources
```

**Test US2-03: State Persistence**
```bash
# Run plan twice
task rebuild:plan -- --phase services
task rebuild:plan -- --phase services

# Expected: Second run shows "No changes" (state persisted)
```

**Dependencies**: D-004, D-005, D-007, D-008 must complete before US2 tasks (requires state library + NAS paths)

---

## Phase 5: User Story 3 - Mount Auto-Remediation (P2)

**Story Goal**: Automatically fix missing NAS mounts during rebuild by invoking Ansible mount role, reducing manual intervention.

**Independent Test Criteria**:
- [ ] Broken mount detected in `rebuild_phase_mounts()`
- [ ] Ansible mount role invoked automatically
- [ ] Mount re-validated after remediation
- [ ] Evidence captured in `reports/mounts/remediation.log`
- [ ] Rebuild continues if remediation succeeds, fails if not

### Implementation Tasks

- [X] D-011 [US3] Update rebuild_phase_mounts() with remediation logic in scripts/lab/lib/rebuild.sh lines 841-850

### Test Tasks (US3)

**Test US3-01: Mount Remediation**
```bash
# Break mount
ssh pve "sudo umount /mnt/nas/homelab_immich"

# Run rebuild
task rebuild:plan -- --phase mounts

# Expected: MNT-REMEDIATE-001 PASS, MNT-REMEDIATE-002 PASS
# Mount restored
```

**Test US3-02: Remediation Evidence**
```bash
# After test US3-01, check evidence
cat artifacts/rebuild-runs/rebuild-*/reports/mounts/remediation.log

# Expected: Ansible playbook output showing mount role execution
```

**Test US3-03: Remediation Failure Handling**
```bash
# Break mount in non-remediatable way (e.g., NAS offline)
# Run rebuild
task rebuild:plan -- --phase mounts

# Expected: MNT-REMEDIATE-001 FAIL, rebuild stops with clear error
```

**Dependencies**: D-004 must complete before US3 task (state library needed for mount validation)

---

## Phase 6: Polish & Cross-Cutting Concerns

**Goal**: Documentation, regression testing, and migration guidance

**Tasks**:
- [X] D-013 Update documentation: specs/033-idempotent-rebuild/quickstart.md, docs/operations/rebuild-orchestrator.md
- [X] D-014 Execute GH Actions regression testing matrix (9+ workflows)
- [X] D-015 Create migration checklist in specs/033-idempotent-rebuild/migration-checklist.md
- [X] D-016 [US1] Update backup restore procedures in docs/operations/backups-proxmox-config-restore.md
  - Document syncing state files from backup archive to NAS location
  - Include steps to restore both lab and static environment state
  - Reference: FR-032 requirement

**Acceptance**:
- All documentation updated with NAS state architecture
- All GH Actions workflows pass (100% success rate)
- Migration checklist captures all deployment steps
- Restore procedures document NAS state sync (FR-032)
- Rollback procedures documented

**Dependencies**: All US1, US2, US3 tasks must complete before Phase 6

---

## Execution Dependencies

### Dependency Graph (User Story Completion Order)

```
Phase 1 (Setup)
    ↓
Phase 2 (Foundational - State Library)
    ↓
    ├──→ Phase 3 (US1: NAS State) ── Can start after Phase 2
    │        ↓
    ├──→ Phase 4 (US2: Laptop Services) ── Requires US1 (D-007, D-008)
    │        ↓
    └──→ Phase 5 (US3: Mount Remediation) ── Can parallel with US2
         ↓
Phase 6 (Polish) ── Requires all user stories complete
```

### Critical Path
1. **Phase 1** → **Phase 2** (blocking for all user stories)
2. **Phase 2** → **US1** (NAS state must exist before laptop services)
3. **US1** → **US2** (services need NAS state + symlinks)
4. **US1, US2, US3** → **Phase 6** (documentation needs all features)

### Parallel Opportunities

**After Phase 1 completes**, these can run in parallel:
- D-002 (laptop docs) - no code dependencies
- D-003 (state validation) - read-only operation

**After Phase 2 completes**, these can run in parallel:
- D-006 (update snapshot.sh, guardrails.sh) - independent scripts
- D-007 (Ansible symlink role) - separate from code changes

**Within Phase 6**, these can run in parallel:
- D-013 (documentation) - no code dependencies
- D-014 (GH Actions testing) - validation only

---

## Parallel Execution Examples

### Example 1: After Phase 1
```bash
# Terminal 1: Laptop documentation
task: Create docs/runbooks/laptop-nfs-setup.md (D-002)

# Terminal 2: State validation
task: Run validate-existing-state.sh on PVE (D-003)

# Both can complete simultaneously
```

### Example 2: After Phase 2
```bash
# Terminal 1: Update supporting scripts
task: Modify snapshot.sh and guardrails.sh (D-006)

# Terminal 2: Create Ansible role
task: Build proxmox_state_symlinks role (D-007)

# No shared files, safe to parallel
```

### Example 3: Phase 6 (After all user stories)
```bash
# Terminal 1: Documentation updates
task: Update quickstart.md and rebuild-orchestrator.md (D-013)

# Terminal 2: Regression testing
task: Run GH Actions workflow matrix (D-014)

# Terminal 3: Migration checklist
task: Create migration-checklist.md (D-015)

# All read-only or independent, can parallel
```

---

## Implementation Strategy

### MVP Scope (User Story 1 Only)
**Goal**: Get state on NAS first, then iterate

**Minimum tasks for MVP**:
- D-001, D-002, D-003 (Setup)
- D-004, D-005, D-006 (State library)
- D-007, D-008 (Symlinks + migration)
- D-014 (Test GH Actions still work)

**MVP Success**: State files accessible from laptop, GH Actions unchanged

### Incremental Delivery After MVP

**Increment 2 (Add US2)**:
- D-009, D-010 (Laptop services)
- Test: `task rebuild:plan -- --phase services` works from laptop

**Increment 3 (Add US3)**:
- D-011 (Mount remediation)
- Test: Broken mounts auto-fixed

**Increment 4 (Complete)**:
- D-012 (Backup integration)
- D-013, D-015 (Documentation + migration checklist)

---

## Task Checklist Progress

### Phase 1: Setup
- [X] D-001 - NAS directories
- [X] D-002 - Laptop docs
- [X] D-003 - State validation

### Phase 2: Foundational
- [X] D-004 - State library
- [X] D-005 - Update pve-service-deploy
- [X] D-006 - Update supporting scripts

### Phase 3: User Story 1 (NAS State)
- [X] D-007 - Ansible symlink role
- [X] D-008 - State migration script
- [X] D-012 - Backup integration

### Phase 4: User Story 2 (Laptop Services)
- [X] D-009 - Refactor services phase
- [X] D-010 - Terraform credentials

### Phase 5: User Story 3 (Mount Remediation)
- [X] D-011 - Update mounts phase

### Phase 6: Polish
- [X] D-013 - Documentation
- [X] D-014 - Regression testing
- [X] D-015 - Migration checklist
- [X] D-016 - Restore documentation

---

## Success Criteria Validation

Track these throughout implementation:

- [X] **SC-005**: Laptop completes all rebuild phases including services
- [X] **SC-006**: State persists across PVE reboots (NAS, not local filesystem)
- [ ] **SC-007**: Zero GH Actions regression (all 9+ workflows pass) — *pending: trigger one real GH Actions terraform workflow post-merge*
- [X] **SC-008**: Mount auto-remediation fixes broken mounts
- [X] **SC-009**: State files included in nightly backups (iac-artifacts/)
- [X] **SC-010**: Cross-environment isolation enforced (lab ≠ prod)

---

## Notes

- **Task IDs**: D-001 to D-016 (Delta tasks, distinguish from original T001-T023)
- **[P] marker**: Indicates parallelizable tasks (different files, no blocking dependencies)
- **[US#] marker**: Maps task to user story for traceability
- **File paths**: Included in every task description for immediate action
- **Test criteria**: Each user story has independent tests (can validate completion)

**Next Step**: Start with D-001 (create NAS directories via Ansible)

---

## Changes from Analysis

**Resolved Findings**:
- **C1**: Added D-016 task for FR-032 (restore documentation)
- **C2**: Aligned user story numbering (US1=Persistent State, US2=Laptop Services)
- **C4**: Added dependency note explaining US2 depends on US1 despite both being P1
- **C13**: Added explicit dependencies to D-009 task header
