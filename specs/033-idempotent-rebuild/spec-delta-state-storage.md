# Feature Specification: Idempotent Rebuild - State Storage & Services Execution

**Feature Branch**: `033-idempotent-rebuild` (delta)
**Created**: 2026-02-09
**Status**: Draft
**Parent Spec**: [specs/033-idempotent-rebuild/spec.md](./spec.md)

## Overview

This specification addresses critical gaps discovered during initial implementation of the idempotent rebuild orchestrator (033), specifically enabling laptop-based end-to-end rebuilds through NAS-backed state storage and direct Terraform execution.

**Context**: The rebuild orchestrator foundation is working (mounts validation, restore phase tested, evidence capture, state tracking), but three gaps prevent laptop-based service deployment: (1) services phase requires PVE-local repo, (2) state files inaccessible from laptops, (3) mount remediation requires manual intervention.

## Clarifications

### User Decisions

**Q1: Should tfvars (secrets) also move to NAS?**
**A1**: No. Keep tfvars under `/var/lib/homelab-proxmox/tfvars` on PVE filesystem. Secrets should not traverse NFS. State files contain resource metadata (CTIDs, IPs) but not credentials.

**Q2: Should we maintain symlinks for gradual migration?**
**A2**: Yes, for backward compatibility. Create symlinks from old paths (`/var/lib/homelab-proxmox/state/services/<service>`) to NAS paths (`/mnt/nas/homelab_ci/infra_state/<env>/<service>`) on PVE. Remove after confirming GH Actions workflows migrated.

**Q3: Service discovery for services phase?**
**A3**: Use existing service-scope-allowlist.json as source of truth. Each service maps to `terraform/services/<service>/` directory. Iterate over allowlist keys.

**Q4: Mount remediation timing?**
**A4**: Automatic in both plan and apply modes. Plan mode remediates then shows what would happen. Apply mode remediates then executes changes. Ansible is idempotent (safe to run repeatedly).

**Q5: Ansible inventory structure?**
**A5**: Single generated inventory file per environment:
- Lab: `ansible/inventories/generated/lab-hosts.yml`
- Prod: `ansible/inventories/generated/prod-hosts.yml`
Stored on NAS at: `infra_state/<env>/ansible/inventories/generated/hosts.yml`
Repo copy is ephemeral (regenerated from state on demand).

## User Scenarios & Testing

**Note**: Despite both US1 and US2 being P1 priority, US2 (Laptop-Based Service Deployment) depends on US1 (Persistent State Storage) completion. Laptop services require NAS state infrastructure to be operational first.

### User Story 1 - Persistent State Storage (Priority: P1)

As an operator, I want Terraform state and Ansible inventory stored on NAS, so they survive host rebuilds and are accessible from multiple execution contexts (laptop, CI runner).

**Acceptance Scenarios**:

1. **Given** services deployed via GH Actions, **When** running rebuild from laptop, **Then** Terraform detects existing resources (no recreation).

2. **Given** state files on NAS, **When** PVE host reboots, **Then** state remains available via NFS mount without manual restoration.

3. **Given** nightly backup job, **When** backup script runs, **Then** Terraform state and Ansible inventory included in backup archive under `iac-artifacts/`.

### User Story 2 - Laptop-Based Service Deployment (Priority: P1)

As an operator, I want to deploy services from my laptop without relying on PVE-local repos, so I can rebuild infrastructure remotely and incrementally.

**Acceptance Scenarios**:

1. **Given** laptop with NFS mount to NAS, **When** running `task rebuild:plan -- --backup-dir /path/to/backup`, **Then** services phase completes successfully by running Terraform from laptop via PVE API.

2. **Given** fresh PVE with no state files, **When** running rebuild, **Then** Terraform creates new resources and stores state on NAS with correct environment separation.

3. **Given** existing state on NAS, **When** running rebuild from different machine (laptop vs GH Actions runner), **Then** both see identical state and produce consistent plans.

### User Story 3 - Automatic Mount Remediation (Priority: P2)

As an operator, I want the rebuild system to automatically fix missing NAS mounts, so I don't need to manually diagnose and remediate mount issues.

**Acceptance Scenarios**:

1. **Given** PVE with missing NAS mount, **When** running rebuild plan, **Then** mount check fails, Ansible remediation runs, mount check re-runs and passes.

2. **Given** mount remediation succeeded, **When** proceeding to services phase, **Then** state files accessible via newly mounted NAS share.

### Edge Cases

- NAS mount exists on PVE but not accessible from laptop (requires laptop autofs setup)
- State directory exists but wrong permissions (should be readable/writable by ci user and root)
- Environment mismatch: lab state accessed with prod credentials (must fail with clear error)
- Concurrent access: GH Actions and laptop both running terraform (last writer wins, document risk)
- State migration: services exist with old state paths, new rebuild reads from NAS (requires one-time sync)

## Requirements

### Functional Requirements

**State Storage Architecture**

- **FR-018**: The system MUST store Terraform state files on NAS at `/mnt/nas/homelab_ci/infra_state/<environment>/<service>/terraform.tfstate` with environment separation (lab, prod).

- **FR-019**: The system MUST store Ansible generated inventory on NAS at `/mnt/nas/homelab_ci/infra_state/<environment>/ansible/inventories/generated/hosts.yml` per environment.

- **FR-020**: PVE scripts (pve-service-deploy, guardrails.sh, snapshot.sh) MUST resolve state paths via environment-aware variable (e.g., `STATE_PATH_ROOT=/mnt/nas/homelab_ci/infra_state/$ENVIRONMENT`).

- **FR-021**: The system MUST maintain backward compatibility by creating symlinks from legacy paths (`/var/lib/homelab-proxmox/state/services/<service>`) to NAS paths during transition period.

- **FR-022**: The system MUST prevent cross-environment state pollution by enforcing environment parameter in all state path resolutions.

**Services Phase Execution**

- **FR-023**: The rebuild services phase MUST execute Terraform directly from laptop using telmate/proxmox provider pointed at PVE API (no SSH delegation to PVE-local scripts).

- **FR-024**: The services phase MUST iterate over services defined in `service-scope-allowlist.json` and execute terraform plan/apply for each `terraform/services/<service>/` directory.

- **FR-025**: The services phase MUST use environment-specific state files on NAS via `-state` flag or `TF_DATA_DIR` environment variable.

- **FR-026**: The services phase MUST support both plan and apply modes consistent with existing rebuild guardrails (plan-only default, apply requires confirmation).

**Mount Remediation**

- **FR-027**: The mount phase MUST automatically invoke `task ansible:mounts` when mount validation checks fail (MNT-001, MNT-002).

- **FR-028**: After mount remediation, the system MUST re-run mount validation checks to confirm success before proceeding.

- **FR-029**: Mount remediation failures MUST be recorded as blocker-level checks and halt rebuild execution.

**Backup Integration**

- **FR-030**: The Proxmox backup script (ansible/roles/proxmox_backup) MUST include Terraform state files from `/mnt/nas/homelab_ci/infra_state/` in the `iac-artifacts/` backup section.

- **FR-031**: The backup script MUST include Ansible generated inventories from NAS state storage in backup archives.

- **FR-032**: Backup restore procedures MUST document syncing state files from backup to NAS location (not PVE filesystem).

### Non-Functional Requirements

- **NFR-001**: State storage changes MUST maintain zero regression for existing GH Actions workflows (9+ workflow files hardcoding `/var/lib/homelab-proxmox` paths).

- **NFR-002**: Laptop NFS mount setup MUST be documented in rebuild quickstart with reference to existing DR drill runbook macOS autofs configuration.

- **NFR-003**: State path resolution MUST fail fast with clear error messages when environment parameter missing or NAS mount unavailable.

### Key Entities

- **State Root Path**: Environment-aware base path for state storage (`/mnt/nas/homelab_ci/infra_state/<environment>`)
- **Service State File**: Per-service Terraform state file at `<state_root>/<service>/terraform.tfstate`
- **Environment Inventory**: Per-environment Ansible inventory at `<state_root>/ansible/inventories/generated/hosts.yml`
- **Legacy State Symlink**: Backward-compatible symlink from `/var/lib/homelab-proxmox/state/services/<service>` to NAS location

## Success Criteria

### Measurable Outcomes

- **SC-005**: Laptop can complete `task rebuild:plan -- --backup-dir <path>` including services phase without manual intervention (100% phase success rate).

- **SC-006**: State files persist across PVE reboots and are accessible from both PVE (via `/mnt/nas/homelab_ci`) and laptop (via `/Volumes/nas/homelab_ci`).

- **SC-007**: GH Actions workflows continue operating without modification (zero regression measured by successful promote-lab and promote-prod runs).

- **SC-008**: Mount remediation reduces operator manual intervention for mount issues from ~5 minutes to 0 minutes (automated fix).

- **SC-009**: State files included in nightly backups (verified via backup manifest inspection).

- **SC-010**: Cross-environment state isolation enforced (lab terraform plan with prod environment fails with error, not silent corruption).

## Assumptions

- NAS (192.168.1.109) remains reachable from both PVE and laptop on local network
- NFS performance sufficient for Terraform state reads/writes (typically <100KB files)
- Single operator assumption - concurrent Terraform runs not expected during rebuild
- macOS laptop has sufficient privileges to mount NFS shares (sudo for autofs)
- Existing homelab_ci NFS share has adequate storage capacity for state files (<100MB total)

## Out of Scope

- Terraform remote state backends (HTTP, S3, Consul) - using local filesystem on NAS
- State locking mechanisms (DynamoDB, Consul) - single operator, no concurrent access
- tfvars migration from PVE filesystem to NAS or vault - keeping tfvars local to PVE
- Migration automation for existing state files - manual one-time sync documented
- LXC disk data backup to NAS - separate future feature
- Terraform workspace isolation - using environment-based directories instead

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| NAS mount unavailable during rebuild | Rebuild fails immediately | Fail-fast in mount phase with clear error; document NAS prerequisites |
| Concurrent Terraform runs from laptop + GH Actions | State corruption potential | Document single-operator constraint; consider adding lock file check in future |
| State path migration breaks existing workflows | GH Actions fail | Use symlinks for backward compatibility; test promote-lab end-to-end before merge |
| NFS latency impacts Terraform performance | Slower plan/apply operations | Baseline performance; acceptable for <5 services; optimize if needed |
| Laptop loses NAS mount mid-rebuild | Partial state write | Terraform atomic writes + evidence capture allow retry; document recovery |

## Implementation Notes

### State Path Resolution Logic

```bash
# Environment-aware state path function
resolve_state_root() {
  local env="${ENVIRONMENT:?ENVIRONMENT required}"
  case "$env" in
    lab) echo "/mnt/nas/homelab_ci/infra_state/lab" ;;
    prod) echo "/mnt/nas/homelab_ci/infra_state/prod" ;;
    *) die "Unknown environment: $env" ;;
  esac
}

# For laptop: Mount point remapped
if [[ "$(uname)" == "Darwin" ]]; then
  STATE_ROOT="/Volumes/nas/homelab_ci/infra_state/${ENVIRONMENT}"
else
  STATE_ROOT="$(resolve_state_root)"
fi
```

### Services Phase Pseudocode

```bash
rebuild_phase_services() {
  local allowlist="${REBUILD_SERVICE_ALLOWLIST_PATH}"
  local -a services
  mapfile -t services < <(jq -r 'keys[]' "$allowlist")
  
  for service in "${services[@]}"; do
    local tf_dir="${REPO_ROOT}/terraform/services/${service}"
    local state_file="${STATE_ROOT}/${service}/terraform.tfstate"
    
    mkdir -p "$(dirname "$state_file")"
    
    cd "$tf_dir"
    terraform init -input=false
    
    if [[ "$REBUILD_MODE" == "plan" ]]; then
      terraform plan -state="$state_file" -var-file="${TFVARS_DIR}/${ENVIRONMENT}.tfvars"
    else
      terraform apply -state="$state_file" -var-file="${TFVARS_DIR}/${ENVIRONMENT}.tfvars" -auto-approve
    fi
    
    record_check "SRV-$(printf '%03d' $idx)" "Service ${service}" ...
  done
}
```

### Mount Remediation Flow

```bash
rebuild_phase_mounts() {
  if ! run_rebuild_host_mount_checks; then
    log_warn "Mount checks failed - attempting remediation"
    
    if ! task ansible:mounts; then
      record_check "MNT-REMEDIATE" "Mount remediation" "blocker" "PASS" "FAIL"
      return 1
    fi
    
    log_info "Remediation complete - re-validating mounts"
    if ! run_rebuild_host_mount_checks; then
      record_check "MNT-REMEDIATE" "Mount remediation" "blocker" "PASS" "FAIL" "Mounts still failing after remediation"
      return 1
    fi
    
    record_check "MNT-REMEDIATE" "Mount remediation" "medium" "PASS" "PASS"
  fi
}
```

## Documentation Updates Required

1. **specs/033-idempotent-rebuild/quickstart.md**: Add laptop NFS mount setup instructions (autofs configuration)
2. **docs/operations/rebuild-orchestrator.md**: Document state storage architecture and environment separation
3. **ansible/roles/proxmox_backup/README.md**: Update backup contents to reflect NAS state collection
4. **scripts/lab/README.md**: Document STATE_ROOT environment variable and legacy path migration
5. **.github/workflows/README.md**: Document state path changes and backward compatibility approach

## Dependencies

- Ansible role `proxmox_mounts` already deployed (manages homelab_ci mount)
- Laptop autofs configuration documented in `docs/runbooks/dr-drill-playbook.md` (lines 29-48)
- Terraform module structure at `terraform/services/<service>/` (exists for immich, monitoring, etc.)
- Service allowlist at `scripts/lab/service-scope-allowlist.json` (exists)

## Testing Strategy

### Pre-Merge Testing

1. **State Migration**: Manually sync existing state from PVE to NAS, verify symlinks work
2. **Laptop Rebuild**: Run `task rebuild:plan` from laptop with all phases, verify services phase succeeds
3. **GH Actions Regression**: Trigger promote-lab workflow, verify zero changes to behavior
4. **Mount Remediation**: Unmount homelab_ci, run rebuild, verify auto-remediation works
5. **Backup Collection**: Trigger backup script, extract archive, verify state files present

### Post-Merge Validation

1. Monitor GH Actions workflows for 1 week for unexpected state-related errors
2. Perform DR drill using rebuilt backup with new state structure
3. Measure Terraform performance over NFS vs local (baseline for future optimization)

## Migration Plan

### Phase 1: Add NAS State Support (Additive)

1. Update `pve-service-deploy` to support `STATE_ROOT` environment variable
2. Modify state path resolution functions to use NAS when `STATE_ROOT` set
3. Update backup script to collect from NAS location
4. Test with single service (immich) using explicit `STATE_ROOT` override

### Phase 2: Create Symlinks (Compatibility)

1. Deploy Ansible task to create symlinks from old paths to NAS
2. Verify GH Actions workflows transparently use NAS state via symlinks
3. Document symlink purpose and removal timeline

### Phase 3: Update Rebuild Services Phase (laptop-first)

1. Refactor `rebuild_phase_services()` to run Terraform locally
2. Add mount remediation to mount phase
3. Test end-to-end rebuild from laptop

### Phase 4: Update Documentation & Remove Symlinks (Cleanup)

1. Update all documentation with new state architecture
2. After 30 days of stable operation, remove symlinks
3. Update GH Actions workflows to use `STATE_ROOT` explicitly

## Rollback Plan

If issues discovered post-merge:

1. **Immediate**: Set `STATE_ROOT=""` to disable NAS state (falls back to legacy paths)
2. **Symlink preserved**: GH Actions continue working via legacy paths
3. **Re-sync state**: Copy NAS state back to `/var/lib/homelab-proxmox/state` if needed
4. **Investigation**: Determine root cause before re-attempting migration

## Acceptance Checklist

- [ ] All functional requirements (FR-018 through FR-032) implemented
- [ ] All success criteria (SC-005 through SC-010) validated via testing
- [ ] Zero regression: GH Actions promote-lab and promote-prod workflows pass
- [ ] Laptop can complete full rebuild including services phase
- [ ] State files included in backup manifest
- [ ] Mount remediation automatically fixes missing mounts
- [ ] Documentation updated per "Documentation Updates Required" section
- [ ] Migration plan executed through Phase 3
- [ ] Test evidence captured in artifacts/rebuild-runs/
