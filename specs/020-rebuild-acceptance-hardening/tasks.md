# Tasks: Rebuild Acceptance Gate Hardening (020)

**Feature Branch**: `020-rebuild-acceptance-hardening`
**Spec**: [spec.md](spec.md)

## Phase 1: Setup (Shared)

- [X] T001 [P] Ensure validation phase directory structure for fixtures exists in scripts/lab/fixtures/evidence-packs/validation/
- [X] T002 [P] Add validation phase note to docs/operations.md for upcoming changes

## Phase 2: Foundational (Blocking)

- [X] T003 Update scripts/lab/checks.d/catalog.json with TEARDOWN-001/002 (phase cleanup, owner harness, severity high, evidence paths reports/cleanup/teardown-*.txt)
- [X] T004 Add VAL-001 (phase validation, owner harness, severity low, allow_missing_evidence true) to scripts/lab/checks.d/catalog.json
- [X] T005 Update scripts/lab/profiles.d/rebuild-hypervisor-nested-workload.json to include TEARDOWN-001/002 and VAL-001 expectations
- [X] T0N1 [P] Audit dependency changes to confirm stdlib-only for scripts/lab/verify_evidence.py and no new runtime deps added (NFR-001)
- [X] T0N2 [P] Confirm no CI pipeline additions/changes were introduced; document “no CI changes” in plan/PR notes (NFR-002)
- [X] T0N3 Validate evidence pack contract_version compatibility after verify_evidence.py/checks.json updates and record result in artifacts/notes (NFR-003)

## Phase 3: User Story 1 — Deterministic Teardown Evidence (Priority: P1)

**Goal**: Quiet, deterministic teardown with TEARDOWN evidence and no ignored errors.
**Independent Test**: Create VM 100/LXC 101, run rebuild cleanup, confirm TEARDOWN-001/002 PASS with evidence files and no rc=25 noise.

- [X] T006 [P] [US1] Implement VM teardown loop (stop → wait → destroy with retries) in scripts/lab/lib/rebuild.sh writing reports/cleanup/teardown-vm-100.txt
- [X] T007 [P] [US1] Implement LXC teardown loop (stop → wait → destroy with retries) in scripts/lab/lib/rebuild.sh writing reports/cleanup/teardown-lxc-101.txt
- [X] T008 [US1] Integrate teardown helpers into rebuild flow in scripts/lab/pve-lab to ensure TEARDOWN checks run and failures propagate
- [X] T009 [US1] Emit TEARDOWN-001/002 entries into checks.json with evidence_refs in scripts/lab/lib/rebuild.sh
- [X] T010 [US1] Update ansible/playbooks/lab_tier2_pve.yml (or relevant teardown tasks) to remove rc=25 ignore and rely on deterministic teardown helpers

## Phase 4: User Story 2 — Verification Messaging Unambiguous (Priority: P1)

**Goal**: Single verification source of truth; verify.json and summary.verification populated without misleading skips.
**Independent Test**: Run rebuild with verification enabled; see no "verification skipped" warning; verify.json + summary fields present.

- [X] T011 [US2] Add verification mode flag propagation between rebuild and suite in scripts/lab/pve-lab (defer messaging to parent)
- [X] T012 [P] [US2] Suppress skip warning and log info-level deferral in suite/rebuild handoff (scripts/lab/lib/rebuild.sh and related suite hooks)
- [X] T013 [US2] Update scripts/lab/verify_evidence.py to always write reports/verify.json and summary.verification.* fields using Python stdlib
- [X] T014 [US2] Ensure pve-lab verify-evidence command writes verify.json (and optional verify.txt) in scripts/lab/pve-lab
- [X] T0V1 [US2] Populate summary.verification.reason for SKIP/FAIL paths in scripts/lab/verify_evidence.py and validate it appears in summary.json

## Phase 5: User Story 3 — Zero Deprecation Warnings (Priority: P1)

**Goal**: Normal rebuild emits zero Ansible deprecation warnings.
**Independent Test**: Run rebuild; Ansible output contains no deprecation warnings.

- [X] T015 [P] [US3] Refactor ansible/roles/assertion_utils/tasks/*.yml to use ansible_facts[...] instead of injected top-level facts
- [X] T016 [P] [US3] Update ansible/roles/assertion_utils/templates/generate_report.* to avoid deprecated fact access
- [X] T017 [US3] Verify rebuild run logs zero Ansible deprecation warnings and document result in reports/logs if applicable

## Phase 6: User Story 4 — Optional Validation Governance (Priority: P2)

**Goal**: VAL-001 governed optional fetch with quiet logging and allow-missing semantics.
**Independent Test**: Simulate unavailable validation endpoint; VAL-001 recorded as SKIP with reason; no WARN spam.

- [X] T018 [US4] Implement validation fetch with allow_missing handling and evidence to reports/validation.json in scripts/lab/lib/rebuild.sh
- [X] T019 [US4] Emit VAL-001 entry into checks.json with phase validation and allow_missing metadata in scripts/lab/lib/rebuild.sh
- [X] T020 [P] [US4] Adjust console logging to INFO for optional validation fetch in scripts/lab/pve-lab (or calling context)

## Phase 7: User Story 5 — Offline Fixtures (Priority: P2)

**Goal**: Offline gate covers teardown/verification/validation behaviors.
**Independent Test**: Run scripts/lab/ci-verify.sh; new fixtures report expected PASS/FAIL without WARN noise.

- [X] T021 [P] [US5] Add fixture invalid-teardown-missing-evidence under scripts/lab/fixtures/evidence-packs/
- [X] T022 [P] [US5] Add fixture invalid-summary-missing-verification under scripts/lab/fixtures/evidence-packs/
- [X] T023 [US5] Update scripts/lab/ci-verify.sh to include new fixtures and validate expected outcomes

## Final Phase: Polish & Cross-Cutting

- [X] T024 [P] Update docs/operations.md with teardown/verification/validation behaviors and examples
- [X] T025 [P] Add quickstart validations to specs/020-rebuild-acceptance-hardening/quickstart.md if gaps identified
- [X] T026 Run full `pve-lab rebuild --apply --verify` and confirm SC-001 through SC-005; record results in artifacts/ notes
- [X] T0S1 Execute 10 consecutive `pve-lab rebuild --apply --verify` runs on lab host and log pass/fail streak to satisfy SC-001 (runs completed: 10/10)

## Dependencies

- Setup (Phase 1) → Foundational (Phase 2) → US1 (P1) → US2 (P1) → US3 (P1) → US4 (P2) → US5 (P2) → Polish.
- TEARDOWN catalog/profile updates (T003-T005) must precede US1 and later phases that emit checks.
- Verification mode and verify.json changes (T011-T014) depend on teardown integration (T006-T010) to ensure pack structure is stable.
- VAL-001 tasks (T018-T020) depend on catalog/profile updates (T004-T005) and verification mode changes (T011-T014) for summary alignment.

## Parallel Execution Examples

- After Foundational completes, US1 tasks T006 and T007 can run in parallel (VM vs LXC teardown helpers).
- US3 refactors (T015, T016) can proceed in parallel once US1/US2 code paths are stubbed, as they touch Ansible only.
- US5 fixture creation tasks (T021, T022) can run in parallel, followed by T023 to wire ci-verify.

## Implementation Strategy

- MVP scope: Complete through US1 and US2 to achieve deterministic teardown and unambiguous verification (meets P1 gate).
- Incremental delivery: US3 (deprecation cleanup) next; then US4 optional validation governance; then US5 fixtures; finish with polish.
