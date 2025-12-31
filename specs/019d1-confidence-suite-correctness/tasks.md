# Tasks: Confidence Suite Correctness & Workload Reliability

**Feature**: `019d1-confidence-suite-correctness`
**Status**: In Progress

## Phase 1: Harness & Framework Core (P1)
**Goal**: Ensure suite integrity with correct cleanup semantics and duplicate ID prevention.

- [x] T001 [US4] Implement `SUITE-DEDUP-001` logic in `scripts/lab/pve-lab` to track and block duplicate check IDs
- [x] T002 [US3] Implement `CLEANUP-PRE-001` preflight check in `scripts/lab/pve-lab` to detect/remove stale resources and capture evidence
- [x] T003 [US3] Refactor `CLEANUP-001` in `scripts/lab/pve-lab` to execute only after teardown (and skip on `--keep`)

## Phase 2: Bootstrap & DNS Reliability (P1)
**Goal**: Reliable DNS checks without `nslookup` dependency.

- [x] T004 [US1] Refactor `NET-001` in `ansible/playbooks/lab_bootstrap.yml` to use `getent hosts` or Python fallback
- [x] T005 [US1] Remove any duplicate `NET-001` emission from `scripts/lab/lib/checks.sh` (or other scripts)

## Phase 3: Workload Reliability & Diagnostics (P1)
**Goal**: Robust nested workload checks with deep diagnostics.

- [x] T006 [US2] Update `WORK-002` in `ansible/playbooks/lab_tier2_pve.yml` to enforce `nesting=1,keyctl=1`, capture config, and ensure idempotency
- [x] T007 [US2] Implement failure diagnostics for `WORK-002` in `ansible/playbooks/lab_tier2_pve.yml` (journal, pct start logs)
- [x] T008 [US2] Refactor `WORK-003` in `ansible/playbooks/lab_tier2_pve.yml` to use `apt-get update` exit code instead of curl

## Phase 4: Verification & Polish (P2)
**Goal**: Verify all success criteria and ensure regression-free operation.

- [x] T009 Verify `SUITE-DEDUP-001` by temporarily injecting a duplicate check ID
- [x] T010 Verify `NET-001` passes on a PVE node without `dnsutils` installed
- [x] T011 Verify `WORK-002` diagnostics by intentionally misconfiguring an LXC (e.g. removing nesting)
- [x] T012 Run full `hypervisor-nested-workload` suite and validate `checks.json` integrity

## Dependencies
- Phase 1 must be completed before Phase 2 and 3 to ensure clean runs.
- Phase 2 and 3 can be executed in parallel.

## Implementation Strategy
- Start with T001-T003 to stabilize the harness lifecycle.
- Proceed to T004-T005 to fix the immediate DNS failure.
- Finish with T006-T008 to harden the workload checks.
