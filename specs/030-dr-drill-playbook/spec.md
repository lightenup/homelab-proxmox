# Feature Specification: DR Drill Playbook

**Feature Branch**: `030-dr-drill-playbook`
**Created**: 2026-01-17
**Status**: Draft
**Input**: User description: "Create a spec for an end-to-end Disaster Recovery drill that downloads a full encrypted Synology Hyper Backup from Hetzner S3 to a NAS share mounted on the PVE host, then validates decryption via DSM Hyper Backup Explorer."

## Clarifications

### Session 2026-01-17

- Q: What free-space threshold should the readiness check enforce? → A: Require free space >= 2× the rclone size estimate.
- Q: Where should the DR drill playbook live? → A: Add a dedicated runbook in docs/runbooks (e.g., docs/runbooks/dr-drill-playbook.md).
- Q: Which NAS share should the drill target by default? → A: Use the dedicated DR test share `/volume1/homelab_dr_test`, mounted on PVE at `/mnt/nas/homelab_dr_test`.

## User Scenarios & Testing *(mandatory)*

<!--
  IMPORTANT: User stories should be PRIORITIZED as user journeys ordered by importance.
  Each user story/journey must be INDEPENDENTLY TESTABLE - meaning if you implement just ONE of them,
  you should still have a viable MVP (Minimum Viable Product) that delivers value.

  Assign priorities (P1, P2, P3, etc.) to each story, where P1 is the most critical.
  Think of each story as a standalone slice of functionality that can be:
  - Developed independently
  - Tested independently
  - Deployed independently
  - Demonstrated to users independently
-->

### User Story 1 - Complete DR Drill Playbook (Priority: P1)

As a maintainer, I want a step-by-step DR playbook that downloads the full encrypted backup to NAS storage and validates decryption in DSM, so I can prove the recovery path works end-to-end.

**Why this priority**: It validates the primary disaster recovery objective and addresses the previous drill failure due to incomplete backup data.

**Independent Test**: A full drill can be executed using only the playbook, resulting in a complete backup download and DSM decryption success.

**Acceptance Scenarios**:

1. **Given** a NAS share with sufficient free space, **When** the playbook is followed, **Then** the full backup is downloaded with the correct Pool directory structure.
2. **Given** a completed download, **When** DSM Hyper Backup Explorer opens the backup with the encryption key, **Then** the backup can be browsed successfully.

---

### User Story 2 - Space and Readiness Validation (Priority: P2)

As a maintainer, I want the playbook to include clear capacity and readiness checks, so I can avoid mid-drill failures due to insufficient space or missing prerequisites.

**Why this priority**: The prior drill failed due to disk constraints; explicit checks reduce risk and wasted time.

**Independent Test**: The readiness steps can be executed without downloading data and confirm prerequisites are satisfied.

**Acceptance Scenarios**:

1. **Given** a target NAS share, **When** readiness checks are performed, **Then** they confirm sufficient free space and access.

---

### User Story 3 - Drill Reporting (Priority: P3)

As a maintainer, I want a consistent way to record drill outcomes, so future drills can compare results and track improvements.

**Why this priority**: Repeatability and evidence capture are essential for ongoing DR confidence.

**Independent Test**: A report entry can be created without completing the full download.

**Acceptance Scenarios**:

1. **Given** a drill run, **When** it is completed or halted, **Then** a drill report is captured with outcomes and blockers.

---

[Add more user stories as needed, each with an assigned priority]

### Edge Cases

- What happens when the NAS share is mounted but lacks sufficient free space for the full backup?
- How does the playbook handle a partial download or interrupted transfer?
- What happens if DSM Hyper Backup Explorer reports corruption due to missing bucket data?
- What happens when credentials are missing or invalid (Hetzner or encryption key)?

## Requirements *(mandatory)*

<!--
  ACTION REQUIRED: The content in this section represents placeholders.
  Fill them out with the right functional requirements.
-->

### Functional Requirements

- **FR-001**: The playbook MUST define the end-to-end DR drill steps from download to DSM decryption validation.
- **FR-002**: The playbook MUST require a NAS target location with free space >= 2× the rclone size estimate and validate readiness before download.
- **FR-003**: The playbook MUST ensure the backup download preserves the full Pool bucket structure required by DSM.
- **FR-004**: The playbook MUST include a DSM Hyper Backup Explorer validation step that proves decryption and browsing work.
- **FR-005**: The playbook MUST define how to capture drill outcomes in a durable report.
- **FR-006**: The playbook MUST state that sensitive configuration files remain untracked and are populated from secure sources.
- **FR-007**: The playbook MUST be published as a dedicated runbook under docs/runbooks (for example, docs/runbooks/dr-drill-playbook.md).
- **FR-008**: The playbook MUST target the dedicated DR test NAS share `/volume1/homelab_dr_test`, mounted on PVE at `/mnt/nas/homelab_dr_test`.

### Key Entities *(include if feature involves data)*

- **Encrypted Backup Set**: The complete Hyper Backup dataset containing metadata, indexes, and all bucket data.
- **DR Staging Location**: The NAS share path used to store the full backup for validation.
- **Drill Report**: A record of the drill execution, outcomes, and blockers.

## Success Criteria *(mandatory)*

<!--
  ACTION REQUIRED: Define measurable success criteria.
  These must be technology-agnostic and measurable.
-->

### Measurable Outcomes

- **SC-001**: A full encrypted backup is downloaded to the NAS share in a single drill attempt.
- **SC-002**: DSM Hyper Backup Explorer completes decryption and browsing without corruption errors.
- **SC-003**: Readiness checks prevent starting a drill when free space is below 2× the rclone size estimate.
- **SC-004**: A drill report is saved for every run, including failures and reasons.
