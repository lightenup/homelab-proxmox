# Implementation Plan - Confidence Suite Correctness & Workload Reliability

**Feature**: 019d1-confidence-suite-correctness
**Goal**: Fix validation semantics, eliminate fragile dependencies, and improve nested LXC reliability in the Lab Confidence Suite.

## Phase 1: Harness & Framework Core (P1)

**Objective**: Implement core framework changes for check ownership, dedup enforcement, and cleanup semantics.

- [ ] **T001**: Update `scripts/lab/pve-lab` to implement `SUITE-DEDUP-001`.
    - Logic: Track all emitted `check_id`s in a temporary file/array.
    - On collision: Emit `SUITE-DEDUP-001` with severity `blocker` and fail the suite.
    - Evidence: Reference conflicting sources.
- [ ] **T002**: Implement `CLEANUP-PRE-001` (Preflight Check).
    - Logic: Scan for VMs in lab range (`9000-9009`) *before* provisioning.
    - Action: If found, attempt destroy.
    - Result: PASS if clean/cleaned, FAIL if destroy fails.
- [ ] **T003**: Refactor `CLEANUP-001` (Post-Teardown).
    - Logic: Move execution to *after* the teardown phase.
    - Condition: SKIP if `--keep` is active.
    - Evidence: `qm list` output to `reports/cleanup/post-teardown-inventory.txt`.

## Phase 2: Bootstrap & DNS Reliability (P1)

**Objective**: Fix NET-001 ownership and remove `nslookup` dependency.

- [ ] **T004**: Refactor `NET-001` in `ansible/playbooks/lab_bootstrap.yml`.
    - Change: Use `getent hosts deb.debian.org` (shell module) instead of `nslookup`.
    - Fallback: Python `socket.getaddrinfo` inline script.
    - Evidence: Register output and write to `reports/net/NET-001-dns.txt` using `copy` module with `always` condition.
- [ ] **T005**: Remove `NET-001` from any other producers.
    - Check `scripts/lab/lib/checks.sh` or other playbooks to ensure they don't emit `NET-001`.

## Phase 3: Workload Reliability & Diagnostics (P1)

**Objective**: Make nested LXC checks robust and self-diagnosing.

- [ ] **T006**: Update `ansible/playbooks/lab_tier2_pve.yml` for `WORK-002` (LXC Start).
    - Prereq: Ensure `pct create` or `pct set` uses `--features nesting=1,keyctl=1`.
    - Evidence: Capture `pct config <vmid>` to `reports/workload/CT-<vmid>-config.txt`.
    - Idempotency: Check if CT exists; if so, validate config matches requirements.
- [ ] **T007**: Implement Deep Diagnostics for `WORK-002` failure.
    - Logic: Use `block/rescue` in Ansible.
    - On Failure:
        - `pct start <vmid>` (capture stdout/stderr).
        - `journalctl -u pve-container -n 500`.
        - `cat /var/log/pve/tasks/active`.
    - Store in `reports/workload/`.
- [ ] **T008**: Refactor `WORK-003` (Connectivity).
    - Change: Use `pct exec <vmid> -- apt-get update` (check return code).
    - Remove: `curl`/`wget` dependency inside container.
    - Evidence: Capture stdout/stderr to `reports/workload/WORK-003-apt-update.txt`.

## Phase 4: Verification & Polish (P2)

**Objective**: Verify all success criteria.

- [ ] **T009**: Verify `SUITE-DEDUP-001` by artificially injecting a duplicate check.
- [ ] **T010**: Verify `NET-001` passes on a fresh PVE (no `dnsutils`).
- [ ] **T011**: Verify `WORK-002` failure diagnostics by intentionally breaking LXC config (e.g., remove `nesting=1`).
- [ ] **T012**: Run full suite `hypervisor-nested-workload` and validate `checks.json` structure and evidence paths.
