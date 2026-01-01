# Tasks: Rebuild Orchestrator & Baseline Proof (019f)

**Feature Branch**: `019f-rebuild-orchestrator`
**Spec**: [spec.md](spec.md)

## Phase 1: Catalog & Profile Definition

- [X] **T001**: Update `scripts/lab/checks.d/catalog.json` with `HOST-*` and `TPL-*` checks.
    - [X] Define `HOST-001` (SSH), `HOST-002` (Bridge), `HOST-003` (Storage), `HOST-004` (Nested - Severity: `high`).
    - [X] Define `TPL-001` (Base VMID), `TPL-002` (Tier2 VMID), `TPL-003` (Template State), `TPL-004` (Tags), `TPL-005` (Cloud-init), `TPL-006` (Naming).
    - [X] Ensure correct phases (`baseline-host`, `baseline-templates`) and ownership (`harness`).
- [X] **T002**: Create `scripts/lab/profiles.d/rebuild-hypervisor-nested-workload.json`.
    - [X] Define profile metadata (ID, name, safety level).
    - [X] Define prerequisite checks (HOST/TPL).
    - [X] Map to suite `hypervisor-nested-workload`.

## Phase 2: Harness & Orchestration

- [X] **T003**: Update `pve-lab` CLI to support `rebuild` command.
    - [X] Add argument parsing for `--profile`, `--apply`, `--dry-run`, `--keep`, `--no-verify`.
    - [X] Implement `rebuild` command handler.
- [X] **T004**: Create `scripts/lab/lib/rebuild.sh` library.
    - [X] Implement `run_baseline_host_checks` function.
    - [X] Implement `run_baseline_template_checks` function.
    - [X] Implement `remediate_templates` function (guarded by `--apply`).
- [X] **T005**: Implement Host Baseline Checks logic.
    - [X] `HOST-001`: SSH connectivity check.
    - [X] `HOST-002`: Bridge/Gateway verification.
    - [X] `HOST-003`: Storage backend verification.
    - [X] `HOST-004`: Nested virtualization check.
    - [X] Ensure evidence is written to `reports/host/`.
- [X] **T006**: Implement Template Baseline Checks logic.
    - [X] `TPL-001`/`TPL-002`: VMID existence check.
    - [X] `TPL-003`: Template state check (`qm config`).
    - [X] `TPL-004`: Tag verification (`ManagedBy`).
    - [X] `TPL-005`: Cloud-init verification.
    - [X] `TPL-006`: Naming policy verification (`lab-tpl-*`).
    - [X] Ensure evidence is written to `reports/templates/`.

## Phase 3: Remediation & Suite Integration

- [X] **T007**: Implement Template Remediation logic.
    - [X] Reuse/adapt existing template creation scripts (`scripts/lab/create_tier1_template.sh`, `scripts/lab/create_tier2_template.sh`).
    - [X] Ensure idempotency (don't recreate if valid).
    - [X] Log actions to `logs/events.jsonl`.
- [X] **T008**: Integrate Suite Execution.
    - [X] Call existing `suite` logic from `rebuild` command.
    - [X] Ensure evidence pack continuity (single pack for rebuild + suite).
- [X] **T009**: Implement Auto-Verification.
    - [X] Ensure `verify-evidence` runs at the end of `rebuild`.
    - [X] Ensure output is written to `reports/verify.json`.
    - [X] Update `verify_evidence.py` if needed to support new phases (`baseline-host`, `baseline-templates`).

## Phase 4: Validation & Documentation

- [X] **T010**: Create Offline Fixtures.
    - [X] `valid-rebuild-pack`: A complete, passing evidence pack.
    - [X] `invalid-rebuild-host-bridge-mismatch`: Pack with HOST-002 failure.
    - [X] `invalid-rebuild-missing-template-evidence`: Pack missing required evidence files.
- [X] **T011**: Update `scripts/lab/ci-verify.sh` to include new fixtures.
- [X] **T012**: Update Documentation.
    - [X] `docs/operations.md`: Add `pve-lab rebuild` usage and workflow.
- [X] **T013**: Manual Verification.
    - [X] Run `pve-lab rebuild --dry-run` on lab host.
    - [X] Run `pve-lab rebuild --apply` (if safe).
    - [X] Verify evidence pack structure and content.
