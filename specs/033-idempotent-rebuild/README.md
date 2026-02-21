# Feature 033: Idempotent Rebuild Orchestrator

## Overview

Complete specification for the idempotent rebuild system that enables recovery from PVE host failure through automated, evidence-based orchestration.

## Specification Documents

### Primary Specification
- **[spec.md](./spec.md)** - Original specification (2026-02-05)
  - Defines core rebuild orchestrator requirements
  - Status: Implementation 80% complete (foundation working)
  - Covers: mounts validation, restore phase, evidence capture, state tracking

### Delta Specification
- **[spec-delta-state-storage.md](./spec-delta-state-storage.md)** - State storage & services execution (2026-02-09)
  - Addresses gaps discovered during initial implementation
  - Status: Specification complete, pending implementation
  - Covers: NAS-backed state storage, laptop-based services deployment, mount auto-remediation

## Implementation Status

### ✅ Completed (Original Spec)
- [x] Plan/apply command structure with guardrails
- [x] Evidence capture and state tracking
- [x] Mount validation phase (6 checks passing)
- [x] Restore phase (tested in plan mode)
- [x] Preflight summaries and confirmation gates
- [x] Lab/prod environment separation
- [x] Taskfile integration (rebuild:plan, rebuild:apply)
- [x] Argument validation (--backup-dir enforcement)

### 🚧 In Progress (Delta Spec)
- [ ] NAS-backed state storage infrastructure
- [ ] Services phase laptop-based execution
- [ ] Mount auto-remediation
- [ ] State backup integration
- [ ] GH Actions backward compatibility maintenance

### ⏸️ Not Started
- [ ] IaC phase validation (depends on state storage)
- [ ] Verify phase (depends on services deployment)
- [ ] Documentation updates
- [ ] Migration plan execution

## Quick Start

### For Operators

**Test Existing Functionality**:
```bash
# Mount validation (working)
task rebuild:plan -- --phase mounts

# Restore validation (working, requires backup)
task rebuild:plan -- --phase restore --backup-dir /root/restore-YYYYMMDD
```

**After Delta Implementation** (not yet working):
```bash
# Full rebuild from laptop
task rebuild:plan -- --backup-dir /root/restore-YYYYMMDD

# Apply changes
task rebuild:apply CONFIRM=rebuild-lab -- --backup-dir /root/restore-YYYYMMDD
```

### For Developers

**Key Files**:
- Core orchestration: `scripts/lab/lib/rebuild.sh`
- Mount checks: `scripts/lab/checks.d/rebuild-mounts.sh`
- Service deployment: `scripts/lab/pve-service-deploy` (needs refactoring per delta spec)
- State management: Multiple files (see delta spec FR-020)
- Configuration: `scripts/lab/rebuild-config.json`

**Testing**:
```bash
# Run specific phase
task rebuild:plan -- --phase <mounts|restore|iac|services|verify>

# Evidence location
ls -l artifacts/rebuild-runs/rebuild-$(date +%Y%m%d)*
```

## Related Documentation

### Implementation Plans
- **[plan.md](./plan.md)** - Original implementation plan (80% complete, Phases 0-4 done)
- **[plan-delta-state-storage.md](./plan-delta-state-storage.md)** - Delta implementation plan
  - 16 tasks (D-001 to D-016) across 6 phases
  - Adds: NAS state, laptop services, mount remediation, restore documentation
  - Estimated effort: 10-16 developer-days

### Task Breakdowns
- **[tasks.md](./tasks.md)** - Original task breakdown (T001-T023)
- **[tasks-delta-state-storage.md](./tasks-delta-state-storage.md)** - Delta tasks (D-001 to D-016)
  - Organized by user story (US1: Persistent State, US2: Laptop Services, US3: Mount Remediation)
  - Includes test criteria, dependencies, parallel opportunities
  - MVP scope defined (US1 only = 8 tasks)

### Supporting Documents
- **[quickstart.md](./quickstart.md)** - Quick reference guide
- **[research.md](./research.md)** - Decision records
- **[data-model.md](./data-model.md)** - State machine and entities
- **[contracts/](./contracts/)** - Interface contracts

## Key Decisions

### Original Spec Decisions
1. Laptop-first execution (not PVE-local)
2. Plan-only by default, apply requires confirmation
3. Evidence stored locally on operator laptop
4. Reuse existing Terraform/Ansible workflows

### Delta Spec Decisions
1. NAS-backed state storage (not PVE filesystem)
2. Environment separation: `infra_state/<lab|static>/<service>/`
3. Symlinks for GH Actions backward compatibility
4. Auto-remediation for mount failures
5. Services phase runs Terraform from laptop (not SSH delegation)

## Success Metrics

**Original Spec**:
- SC-001: Full rebuild in <1 working day ⏸️
- SC-002: 100% mount validation (6/6 checks) ✅
- SC-003: Zero destructive changes on re-run ✅
- SC-004: 100% evidence artifacts ✅

**Delta Spec**:
- SC-005: Laptop completes all phases ⏸️
- SC-006: State persists across reboots ⏸️
- SC-007: Zero GH Actions regression ⏸️
- SC-008: Auto-mount remediation ⏸️
- SC-009: State in backups ⏸️
- SC-010: Cross-env isolation ⏸️

## Next Steps

1. Review delta spec: [spec-delta-state-storage.md](./spec-delta-state-storage.md)
2. Run `/speckit.plan` on delta spec to generate implementation plan
3. Execute migration Phase 1: Add NAS state support
4. Test with single service (immich)
5. Deploy symlinks for backward compatibility
6. Implement services phase refactor
7. Add mount auto-remediation
8. Update documentation
9. Execute full laptop-based rebuild test
10. Remove symlinks after 30 days

## Questions or Issues

- Delta spec clarifications needed? See "Questions to Clarify" section in spec-delta-state-storage.md (all answered)
- Implementation blockers? Document in tasks.md with blocker label
- Testing failures? Evidence artifacts in artifacts/rebuild-runs/

---

**Maintainer**: Infrastructure team  
**Last Updated**: 2026-02-09  
**Branch**: 033-idempotent-rebuild
