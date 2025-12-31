# Tasks: Rebuild Orchestrator & Baseline Proof (019f)

**Feature Branch**: `019f-rebuild-orchestrator`
**Spec**: [spec.md](spec.md)

## Phase 1: Catalog & Profile Definition

- [ ] **T001**: Update `scripts/lab/checks.d/catalog.json` with `HOST-*` and `TPL-*` checks.
    - [ ] Define `HOST-001` (SSH), `HOST-002` (Bridge), `HOST-003` (Storage), `HOST-004` (Nested).
    - [ ] Define `TPL-001` (Base VMID), `TPL-002` (Tier2 VMID), `TPL-003` (Template State), `TPL-004` (Tags), `TPL-005` (Cloud-init), `TPL-006` (Naming).
    - [ ] Ensure correct phases (`baseline-host`, `baseline-templates`) and ownership (`harness`).
- [ ] **T002**: Create `scripts/lab/profiles.d/rebuild-hypervisor-nested-workload.json`.
    - [ ] Define profile metadata (ID, name, safety level).
    - [ ] Define prerequisite checks (HOST/TPL).
    - [ ] Map to suite `hypervisor-nested-workload`.

## Phase 2: Harness & Orchestration

- [ ] **T003**: Update `pve-lab` CLI to support `rebuild` command.
    - [ ] Add argument parsing for `--profile`, `--apply`, `--dry-run`, `--keep`, `--no-verify`.
    - [ ] Implement `rebuild` command handler.
- [ ] **T004**: Create `scripts/lab/lib/rebuild.sh` library.
    - [ ] Implement `run_baseline_host_checks` function.
    - [ ] Implement `run_baseline_template_checks` function.
    - [ ] Implement `remediate_templates` function (guarded by `--apply`).
- [ ] **T005**: Implement Host Baseline Checks logic.
    - [ ] `HOST-001`: SSH connectivity check.
    - [ ] `HOST-002`: Bridge/Gateway verification.
    - [ ] `HOST-003`: Storage backend verification.
    - [ ] `HOST-004`: Nested virtualization check.
    - [ ] Ensure evidence is written to `reports/host/`.
- [ ] **T006**: Implement Template Baseline Checks logic.
    - [ ] `TPL-001`/`TPL-002`: VMID existence check.
    - [ ] `TPL-003`: Template state check (`qm config`).
    - [ ] `TPL-004`: Tag verification (`ManagedBy`).
    - [ ] `TPL-005`: Cloud-init verification.
    - [ ] Ensure evidence is written to `reports/templates/`.

## Phase 3: Remediation & Suite Integration

- [ ] **T007**: Implement Template Remediation logic.
    - [ ] Reuse/adapt existing template creation scripts.
    - [ ] Ensure idempotency (don't recreate if valid).
    - [ ] Log actions to `logs/events.jsonl`.
- [ ] **T008**: Integrate Suite Execution.
    - [ ] Call existing `suite` logic from `rebuild` command.
    - [ ] Ensure evidence pack continuity (single pack for rebuild + suite).
- [ ] **T009**: Implement Auto-Verification.
    - [ ] Ensure `verify-evidence` runs at the end of `rebuild`.
    - [ ] Update `verify_evidence.py` if needed to support new phases (`baseline-host`, `baseline-templates`).

## Phase 4: Validation & Documentation

- [ ] **T010**: Create Offline Fixtures.
    - [ ] `valid-rebuild-pack`: A complete, passing evidence pack.
    - [ ] `invalid-rebuild-host-bridge-mismatch`: Pack with HOST-002 failure.
    - [ ] `invalid-rebuild-missing-template-evidence`: Pack missing required evidence files.
- [ ] **T011**: Update `scripts/lab/ci-verify.sh` to include new fixtures.
- [ ] **T012**: Update Documentation.
    - [ ] `docs/operations.md`: Add `pve-lab rebuild` usage and workflow.
- [ ] **T013**: Manual Verification.
    - [ ] Run `pve-lab rebuild --dry-run` on lab host.
    - [ ] Run `pve-lab rebuild --apply` (if safe).
    - [ ] Verify evidence pack structure and content.
