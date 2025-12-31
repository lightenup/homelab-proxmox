# Feature Specification: Assertion Alignment

**Feature Branch**: `019d-assertion-alignment`  
**Created**: December 31, 2025  
**Status**: Draft  
**Input**: User description: "Increase fidelity and readability of Tier 1 + Tier 2 validations by moving key invariants into explicit Ansible assertions and producing machine-readable assertion evidence."

## Overview

This feature increases the fidelity and readability of Tier 1 and Tier 2 validations by moving key invariants into explicit Ansible assertions. It introduces a standardized assertion style and produces machine-readable assertion reports that are integrated into the existing Evidence Pack structure. This ensures that validation logic is self-describing, readable as a contract, and machine-verifiable.

## Clarifications

### Session 2025-12-31

- Q: How should Ansible generate the JSON report? → A: Use a custom callback plugin or a standardized task pattern (e.g., `copy` content) to write the report to the evidence directory. The spec defines the artifact, implementation detail is left to the developer but must produce the specified JSON structure.
- Q: Should the harness re-implement checks that are now in Ansible? → A: No. The harness should reference the Ansible assertion report. The harness still owns orchestration and cleanup.
- Q: Are external validators like `ajv` allowed? → A: No, unless using stdlib-only python. The schema should be lightweight.

## Core Concepts

### Concept: Phase

A distinct stage of the validation pipeline.
- **Examples**: `bootstrap`, `tier2`, `workload`, `cleanup`.
- **Usage**: Assertion reports are namespaced by phase (e.g., `assertions.bootstrap.json`).

### Concept: Assertion Report

A machine-readable JSON file produced by an Ansible playbook execution containing the results of all assertions run during that phase.
- **Location**: `{{ evidence_dir }}/reports/assertions.<phase>.json`
- **Content**: List of assertions with check IDs, results, and remediation hints.
- **Behavior**: Must be generated even if assertions fail or playbook aborts.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Readable Assertion Contracts (Priority: P1)

As an operator reading the Ansible playbooks, I want to see clear, standardized assertions that act as a contract, so I can understand exactly what is being validated and how to fix it if it fails.

**Why this priority**: Readability and maintainability are the primary drivers for this refactor.

**Independent Test**: Review `ansible/playbooks/lab_bootstrap.yml` and `ansible/playbooks/lab_tier2_pve.yml`. Verify that all `assert` tasks follow the strict style guide (Check ID, symptom, remediation).

**Acceptance Scenarios**:

1. **Given** the `lab_bootstrap.yml` playbook, **When** I read the tasks, **Then** I see `ansible.builtin.assert` tasks labeled with Check IDs (e.g., `[NET-001]`).
2. **Given** a failed assertion during a run, **When** I look at the console output, **Then** I see a clear error message with the Check ID and a remediation hint.

---

### User Story 2 - Machine-Readable Assertion Evidence (Priority: P1)

As an automated harness, I want to consume structured assertion results from Ansible runs, so I can include them in the Evidence Pack without parsing unstructured logs.

**Why this priority**: Enables the harness to report on Ansible-driven checks reliably.

**Independent Test**: Run `pve-lab suite hypervisor-control-plane`. Verify that `artifacts/019-lab/<runid>/reports/assertions.tier2.json` exists and contains valid JSON data for the executed assertions.

**Acceptance Scenarios**:

1. **Given** a successful suite run, **When** I examine the evidence pack, **Then** I find `reports/assertions.<phase>.json` files.
2. **Given** the assertion report, **When** I inspect the content, **Then** it contains an array of assertions with `check_id`, `result`, and `remediation`.
3. **Given** a failed assertion, **When** I inspect the report, **Then** the corresponding entry shows `result: FAIL` and includes the failure reason.
4. **Given** a playbook execution that aborts due to assertion failure, **When** I check the evidence directory, **Then** the assertion report still exists and records the failure.

---

### User Story 3 - Integrated Evidence Pack (Priority: P2)

As an auditor, I want a single `checks.json` that references all validations, including those performed by Ansible, so I have a complete view of the system state.

**Why this priority**: Maintains the "Single Source of Truth" property of the Evidence Pack.

**Independent Test**: Run a suite. Verify `checks.json` includes checks that were performed by Ansible (e.g., `PVE-001`), and their `evidence_refs` point to the corresponding assertion report.

**Acceptance Scenarios**:

1. **Given** a suite run, **When** I examine `checks.json`, **Then** I see entries for Ansible-driven checks (e.g., `PVE-001`).
2. **Given** an Ansible-driven check entry in `checks.json`, **When** I check its `evidence_refs`, **Then** it points to `reports/assertions.<phase>.json`.
3. **Given** the harness execution, **When** Ansible finishes, **Then** the harness ingests the assertion report to update its internal check records.

---

### Edge Cases

- **What happens when Ansible fails early?** The assertion report must be generated via a `always` block or callback, ensuring partial results are captured.
- **What happens if the assertion report is malformed?** The harness logs an ERROR and marks associated checks as ERROR.
- **What happens if an assertion fails?** The playbook execution aborts (default behavior), but the report is written first (or in `always` block).

## Requirements *(mandatory)*

### Functional Requirements

#### Assertion Style Contract
- **FR-001**: All Ansible assertions MUST use `ansible.builtin.assert`.
- **FR-002**: Each assertion MUST include a `fail_msg` conforming to: `[CHECK-ID] <symptom>. Remediation: <one line>.`
- **FR-003**: Each assertion MUST include a `success_msg` conforming to: `[CHECK-ID] <short confirmation>.`
- **FR-004**: Assertions MUST be grouped and labeled by phase and namespace.

#### Assertion Evidence Report
- **FR-005**: Each playbook execution MUST produce a JSON report at `{{ evidence_dir }}/reports/assertions.<phase>.json`.
- **FR-005a**: The report MUST be generated even when assertions fail or the playbook aborts (e.g., using `block/rescue/always`).
- **FR-005b**: Assertion entries MUST be accumulated during execution and serialized once at the end of the phase.
- **FR-006**: The report schema MUST include `run_id`, `profile_id`, `phase`, `timestamp`, and an `assertions` array.
- **FR-007**: Each assertion entry in the report MUST include `check_id`, `title`, `result` (`PASS`|`FAIL`|`SKIP`|`ERROR`), `reason`, `remediation` (optional), and `evidence_refs`.

#### Harness Integration
- **FR-008**: The harness MUST NOT re-implement logic covered by Ansible assertions.
- **FR-009**: The harness MUST ingest `reports/assertions.*.json` files and include their contents in the final `checks.json`.
    - If report missing: Mark related checks as `ERROR` (or `SKIP` if phase not executed).
    - If JSON malformed: Mark related checks as `ERROR`.
    - If duplicate `check_id`: Last writer wins (same phase) or `ERROR` (cross-phase).
- **FR-009a**: Checks sourced from Ansible MUST include `source: "ansible"` and `source_ref: "reports/assertions.<phase>.json"` in `checks.json`.
- **FR-015**: The harness MUST pass `run_id`, `profile_id`, `phase`, and `evidence_dir` (absolute or repo-relative) as extra vars to Ansible playbooks.

#### Scope & Coverage
- **FR-011**: Tier 1 bootstrap assertions MUST be refactored to the new style.
- **FR-012**: Tier 2 PVE assertions MUST be refactored to the new style.
- **FR-014**: Guardrail checks `GUARD-001` and `GUARD-002` MUST be implemented as assertions where applicable (e.g., inventory guards).
    - Note: In normal execution, these are expected to `PASS`. Negative testing is handled separately by the suite.

### Non-Functional Requirements
- **NFR-001**: No new non-stdlib runtime dependencies on the controller.
- **NFR-002**: Assertion messages MUST be readable (<120 chars target per msg, single remediation line).
- **NFR-003**: Check IDs MUST be stable and MUST NOT suffer semantic drift.

### Key Entities

- **Assertion Report**: JSON file containing results of Ansible assertions.
- **Phase**: Logical grouping of assertions (bootstrap, tier2, etc.).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Running `pve-lab suite hypervisor-nested-workload` produces readable console output and `reports/assertions.*.json` files.
- **SC-002**: `checks.json` contains 100% of expected checks, with Ansible-driven checks referencing their assertion reports and including `source` attributes.
- **SC-003**: Idempotent re-runs yield consistent results (PASS/PASS).
- **SC-004**: 100% of Ansible assertions follow the defined style contract (Check ID, remediation).
- **SC-005**: Assertion reports exist and are valid JSON even on failed runs.

## Check Catalog Updates

The following checks are mapped to Ansible Assertions:

| Check ID | Namespace | Description | Implementation | Evidence Ref |
| :--- | :--- | :--- | :--- | :--- |
| **PVE-001** | PVE | Packages installed | Ansible | `reports/assertions.tier2.json` |
| **PVE-002** | PVE | Services running | Ansible | `reports/assertions.tier2.json` |
| **PVE-003** | PVE | pmxcfs mounted | Ansible | `reports/assertions.tier2.json` |
| **PVE-004** | PVE | API reachable | Ansible | `reports/assertions.tier2.json` |
| **PVE-005** | PVE | Version check | Ansible | `reports/assertions.tier2.json` |
| **NET-001** | NET | DNS resolution | Ansible | `reports/assertions.bootstrap.json` |
| **NET-002** | NET | Internet connectivity | Ansible | `reports/assertions.bootstrap.json` |
| **GUARD-001** | GUARD | Inventory safety | Ansible | `reports/assertions.tier2.json` |
| **GUARD-002** | GUARD | Hostname safety | Ansible | `reports/assertions.tier2.json` |

*(Note: NET-003 removed from Ansible mapping as it is a harness/host-level check)*

## Evidence Pack Structure

Updated structure including assertion reports:

```
artifacts/019-lab/<runid>/
├── evidence_manifest.json
├── checks.json
├── provenance.json
├── summary.json
├── logs/
│   ├── events.jsonl
│   └── ...
└── reports/
    ├── assertions.bootstrap.json  <-- NEW
    ├── assertions.tier2.json      <-- NEW
    ├── validation.json
    └── ...
```

## Implementation Guidance

### Assertion Style Example

```yaml
- name: "[NET-001] Verify DNS resolution"
  block:
    - name: "Check DNS resolution for deb.debian.org"
      ansible.builtin.command: getent hosts deb.debian.org
      register: dns_check
      ignore_errors: true

    - name: "Assert DNS resolution success"
      ansible.builtin.assert:
        that:
          - dns_check.rc == 0
        fail_msg: "[NET-001] DNS resolution failed inside lab VM. Remediation: verify /etc/resolv.conf and vmbr0 dns-nameservers."
        success_msg: "[NET-001] DNS resolution OK."
  always:
    - name: "Record assertion result"
      ansible.builtin.set_fact:
        assertion_results: "{{ assertion_results | default([]) + [{ 'check_id': 'NET-001', 'result': (dns_check.rc == 0) | ternary('PASS', 'FAIL'), ... }] }}"
```

### Reporting Mechanism
Use a `block/rescue/always` structure in the main playbook or a dedicated role to ensure `reports/assertions.<phase>.json` is written using `copy` or `template` module at the end of execution, dumping the accumulated `assertion_results` variable.
