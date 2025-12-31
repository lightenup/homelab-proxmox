# Feature Specification: Confidence Suite Correctness & Workload Reliability

**Feature Branch**: `019d1-confidence-suite-correctness`
**Created**: December 31, 2025
**Status**: Draft
**Input**: User description: "Fix validation semantics, eliminate fragile dependencies, and improve nested LXC reliability in the Lab Confidence Suite."

## 1. Overview

Fix remaining correctness gaps in the Confidence Suite so that Evidence Packs are trustworthy and comparable:

* Replace fragile DNS validation (`nslookup`) with reliable mechanisms.
* Make nested LXC workload checks reliable, and when failures occur, collect sufficient evidence to diagnose root cause.
* Correct cleanup proof semantics with proper phase ordering.
* Eliminate duplicate check IDs via explicit check ownership rules and enforcement.

## 2. User Scenarios & Testing (mandatory)

### US1 — DNS validation works on minimal PVE installs (P1)

**When** running `pve-lab suite hypervisor-nested-workload`
**Then** NET-001 validates DNS without requiring `dnsutils` / `nslookup`.

**Why this priority**: Critical for baseline validation on standard PVE installs without extra dependencies.

**Independent Test**: Run `pve-lab suite hypervisor-nested-workload` on a fresh PVE node. Verify NET-001 passes.

**Acceptance Scenarios**:

1. **Given** a minimal PVE install (no `dnsutils`), **When** the suite runs, **Then** NET-001 passes using `getent hosts` or python fallback.
2. **Given** a completed run, **When** inspecting evidence, **Then** `reports/net/NET-001-dns.txt` contains the command output.
3. **Given** a failure before evidence collection, **When** inspecting `checks.json`, **Then** NET-001 references partial evidence and explains the missing artifacts.

### US2 — Nested LXC workload is reliable and debuggable (P1)

**When** running the profile `hypervisor-nested-workload`
**Then** WORK-002/WORK-003 pass; if they fail, the evidence pack contains a Workload Failure Evidence Set.

**Why this priority**: The nested workload is the core value proposition of the lab; flakiness here undermines trust.

**Independent Test**: Run the suite. If WORK-002 fails, verify `reports/workload/` contains diagnostic logs.

**Acceptance Scenarios**:

1. **Given** a properly configured host, **When** WORK-002 runs, **Then** it proves LXC running state via `pct status`.
2. **Given** a running LXC, **When** WORK-003 runs, **Then** it proves connectivity via `pct exec`.
3. **Given** a failure in WORK-002/003, **When** inspecting artifacts, **Then** `pct config`, `pct status`, `pct start` logs, and journal excerpts are present.

### US3 — Cleanup proof is semantically correct (P1)

**When** suite completes without `--keep`
**Then** cleanup proof runs **after teardown** and can PASS.

**Why this priority**: Ensures the lab is actually clean and prevents false positives/negatives in cleanup verification.

**Independent Test**: Run suite without `--keep`. Verify CLEANUP-001 runs after destroy.

**Acceptance Scenarios**:

1. **Given** a standard run, **When** teardown completes, **Then** `CLEANUP-001` executes and verifies no VMs remain.
2. **Given** a run with `--keep`, **When** suite finishes, **Then** `CLEANUP-001` is skipped with a reason.
3. **Given** a new run starting, **When** preflight checks run, **Then** `CLEANUP-PRE-001` detects any stale resources.

### US4 — No duplicate check IDs (P2)

**When** a suite run completes
**Then** each `check_id` appears at most once in `checks.json`.

**Why this priority**: Duplicate IDs corrupt the evidence data model and make automated analysis impossible.

**Independent Test**: Run suite. Parse `checks.json` and assert unique `check_id`s.

**Acceptance Scenarios**:

1. **Given** a suite run, **When** `checks.json` is generated, **Then** no `check_id` appears more than once.
2. **Given** a collision (e.g., Ansible and Harness both emit NET-001), **When** ingestion happens, **Then** the suite fails with a blocker ERROR.

---

## 3. Requirements (mandatory)

### 3.1 DNS Check Robustness

* **FR-001 (NET-001 Implementation)**: NET-001 MUST use **`getent hosts deb.debian.org`** as the primary assertion mechanism.
* **FR-001a (NET-001 Ownership & Phase)**: `NET-001` is owned by **Ansible (bootstrap phase)** and MUST be produced only in `reports/assertions.bootstrap.json`. Tier2/workload phases MUST NOT emit `NET-001` again. Any DNS validation inside the nested LXC MUST be expressed as a **workload check** (e.g., `WORK-003`) and MUST NOT reuse `NET-001`.
* **FR-002 (Fallback)**: If `getent` is unavailable (unexpected), use python stdlib `socket.getaddrinfo` as fallback.
* **FR-003 (Ban nslookup)**: The suite MUST NOT use `nslookup` for NET-001. (Rationale: not present on minimal installs; adds unnecessary dependency.)
* **FR-004 (Evidence)**: NET-001 MUST store its raw output to `reports/net/NET-001-dns.txt` and reference it in `checks.json`.
* **FR-004a (Evidence Durability)**: The playbook MUST write `reports/net/NET-001-dns.txt` to the Evidence Pack via an `always:` (or equivalent) mechanism so the file exists even if assertions fail and the play aborts.
* **FR-004b (Partial Evidence Rules)**: If a check fails before evidence collection completes, the check MUST reference whatever partial evidence exists and set `reason` to explain missing artifacts; missing artifact is not allowed to silently pass.

### 3.2 Nested LXC Workload Reliability & Diagnostics

* **FR-005 (Explicit Prereqs)**: LXC creation for workload checks MUST explicitly enable required features:
  * `nesting=1` (mandatory)
  * `keyctl=1` (if required by target baseline; document in check reason/evidence)
* **FR-005a (Where nesting is set)**: The nested LXC MUST be created (or updated) with `pct set <ctid> --features nesting=1,keyctl=1` (keyctl optional) and this config MUST be captured to `reports/workload/CT-<ctid>-config.txt`.
* **FR-006 (Authoritative Start Proof)**: WORK-002 MUST determine “started” via `pct status <id>` reporting `running`.
* **FR-007 (Connectivity Proof, no extra tools)**: `WORK-003` MUST validate connectivity from inside the nested LXC using **`apt-get update` exit code** (Debian-based templates) as the primary proof. This avoids relying on `curl`/`wget`.
* **FR-007a (Template Contract)**: The workload profile MUST use a Debian-based LXC template where `apt-get` is available. If template deviates, the profile MUST mark `WORK-003` as `SKIP` with a clear reason and remediation.
* **FR-008 (Failure Evidence Set)**: On WORK-002/WORK-003 failure, the suite MUST capture:
  * `pct config 101` output
  * `pct status 101` output
  * `pct start 101` stdout/stderr
  * `journalctl` excerpt relevant to container start failures (pve-container/lxc)
  * optional `lxc-start` debug log if available (best-effort)
* **FR-008a (LXC start failure deep evidence)**: On `WORK-002` failure, capture:
  * `pct start <ctid>` stdout/stderr to `reports/workload/WORK-002-pct-start.txt`
  * `journalctl -u pve-container --no-pager -n 500` to `reports/workload/WORK-002-pve-container-journal.txt`
  * `cat /var/log/pve/tasks/active` (if present) to `reports/workload/WORK-002-pve-tasks-active.txt`
* **FR-009 (Evidence Paths)**: Store workload artifacts under `reports/workload/` with deterministic names and reference them from check entries.
* **FR-017 (Workload Idempotency)**: If the target CTID exists, the suite MUST either (a) reuse it safely (ensure config matches required features) or (b) delete+recreate it safely. The choice MUST be deterministic and recorded in `checks.json` reason field for `WORK-002`.

### 3.3 Cleanup Semantics and Phase Ordering

* **FR-010 (Split Cleanup Checks)**:
  * `CLEANUP-PRE-001`: Preflight check (before provisioning) that detects stale lab resources not matching current RunId.
  * `CLEANUP-001`: Post-teardown proof check that no lab VMs remain (range + identity markers).
  * **CLEANUP-PRE-001 semantics**:
    * If stale lab resources are found, the suite MUST attempt safe cleanup (same guardrails as destroy).
    * If safe cleanup succeeds, `CLEANUP-PRE-001` result is `PASS` with reason “stale resources found and removed”.
    * If safe cleanup fails, `CLEANUP-PRE-001` is `FAIL` with severity `blocker` and suite aborts.
* **FR-011 (Correct Timing)**: `CLEANUP-001` MUST execute only after teardown is complete (unless `--keep`, then SKIP).
* **FR-012 (Evidence)**: Cleanup checks MUST store VM inventory snapshots (e.g., filtered `qm list` + tag evidence) in `reports/cleanup/`.
* **FR-012a (Post-teardown timing)**: `CLEANUP-001` MUST run only after teardown completion AND after the suite has attempted final cleanup actions.

### 3.4 Check Ownership and Deduplication

* **FR-013 (Ownership Rules)**:
  * Checks implemented as Ansible assertions are owned by Ansible; harness ingests them.
  * Harness MUST NOT independently emit the same check_id.
* **FR-014 (Dedup Enforcement)**: If two sources attempt to publish the same `check_id`, the suite MUST mark a blocker ERROR (e.g., `SUITE-DEDUP-001`) and fail.
* **FR-014a (Dedup Check Definition)**: The suite MUST emit a dedicated check entry `SUITE-DEDUP-001` (severity `blocker`) when a collision is detected.
* **FR-015 (Evidence)**: Dedup error MUST reference both source artifacts/paths in `evidence_refs`.
* **FR-016 (Cross-phase Dedup)**: Duplicate `check_id` across phases (e.g., `NET-001` in both bootstrap and tier2 reports) MUST be treated as a dedup collision and handled per FR-014.

---

## 4. Success Criteria

* **SC-001**: `hypervisor-nested-workload` completes with **0 duplicate** check IDs across 10 consecutive runs.
* **SC-002**: NET-001 passes without installing `dnsutils` on the lab PVE VM.
* **SC-003**: WORK-002 and WORK-003 pass on a correctly configured nested environment OR produce complete Failure Evidence Set on failure.
* **SC-004**: `CLEANUP-001` passes post-teardown on runs without `--keep`; SKIP with `--keep`.
* **SC-005**: Evidence pack includes deterministic paths for DNS/workload/cleanup artifacts referenced by `checks.json`.

---

## 5. Assumptions & Dependencies

* **Assumption**: The lab environment has outbound internet access for DNS/connectivity checks.
* **Assumption**: The PVE host supports nested virtualization (KVM) and LXC nesting.
* **Assumption**: The workload profile uses a Debian-based LXC template where `apt-get` is available.
* **Dependency**: `019c1` (profiles/checks/evidence packs) and `019d` (assertion alignment) are implemented.
