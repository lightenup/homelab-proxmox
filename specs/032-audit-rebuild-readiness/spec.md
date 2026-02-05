# Feature Specification: Audit Rebuild Readiness & Configuration Hygiene

**Feature Branch**: `032-audit-rebuild-readiness`
**Created**: 2026-02-05
**Status**: Draft
**Input**: User description: "Analyze unused/needed code and config, rebuild readiness gaps, and anti-patterns; review NFS role coverage for LXC shared mounts vs PVE backups."

## Clarifications

### Session 2026-02-05

- Q: What does “full rebuild” mean for this audit? → A: Rebuild from a machine with only PVE installed, using backups on the NAS shared over NFS.
- Q: Which nodes/environments are included in scope? → A: All environments/nodes represented in the repository.
- Q: How should DR/maintenance-only items be classified? → A: Use a separate “DR/maintenance-only” status.
- Q: What evidence sources should be used for classification? → A: Full runtime inventory for all items.
- Q: How should remediation actions be prioritized? → A: Prioritize by rebuild/DR criticality.

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

### User Story 1 - Produce an actionable audit report (Priority: P1)

As the operator, I want a clear audit report that maps each repository component to its purpose and flags unused or unneeded items, so I can simplify daily operations and reduce risk.

**Why this priority**: Day-to-day experience improves immediately when unused items are identified and the remaining inventory is clearly documented.

**Independent Test**: Can be fully tested by reviewing the report to confirm every component is inventoried, classified, and supported by evidence.

**Acceptance Scenarios**:

1. **Given** the current repository and available environment information, **When** the audit is completed, **Then** every relevant code/config/process component is listed with a purpose and usage status.
2. **Given** any item marked unused or unneeded, **When** reviewing the report, **Then** a rationale and evidence source are provided for the classification.

---

### User Story 2 - Rebuild readiness assessment (Priority: P2)

As the operator, I want a rebuild readiness assessment that documents prerequisites, dependencies, and gaps, so a full rebuild can be executed with confidence.

**Why this priority**: Rebuild capability is critical for resilience and disaster recovery, even if it is used infrequently.

**Independent Test**: Can be tested by validating that the assessment includes a complete rebuild checklist, missing information, and blocking gaps.

**Acceptance Scenarios**:

1. **Given** the documented rebuild steps, **When** another operator reviews the checklist, **Then** they can identify all prerequisites and blockers without needing unstated knowledge.

---

### User Story 3 - Storage and shared mount coverage review (Priority: P3)

As the operator, I want a review of shared storage coverage (including NFS usage for LXC shared mounts), so I can ensure storage and mount automation is complete and consistent.

**Why this priority**: Storage gaps can lead to service outages and data loss; coverage clarity reduces operational risk.

**Independent Test**: Can be tested by verifying that all shared mounts used by LXCs are documented with their management status and gaps.

**Acceptance Scenarios**:

1. **Given** the list of LXC shared mounts, **When** the storage review is completed, **Then** each mount is mapped to its management coverage and identified gaps.

---

[Add more user stories as needed, each with an assigned priority]

### Edge Cases

- Critical environment access (e.g., hypervisor login) is delayed or unavailable during the audit.
- A component appears unused but is only exercised during disaster recovery or maintenance windows.
- Conflicting sources disagree about whether an item is active, causing ambiguous status.

## Requirements *(mandatory)*

<!--
  ACTION REQUIRED: The content in this section represents placeholders.
  Fill them out with the right functional requirements.
-->

### Functional Requirements

- **FR-001**: The audit MUST inventory all relevant code, configuration, and operational processes in the repository, including their stated purpose.
- **FR-002**: The audit MUST classify each item as in use, unused, or requires review, with evidence for the classification.
- **FR-003**: The assessment MUST document rebuild prerequisites, dependencies, and missing information required for a full rebuild.
- **FR-004**: The assessment MUST identify gaps and incomplete processes that prevent a full rebuild from being executed end-to-end.
- **FR-005**: The storage review MUST map all shared mounts used by LXCs and note whether automation or documentation covers them.
- **FR-006**: The audit MUST include a prioritized list of remediation actions, with rationale and impact.
- **FR-007**: The rebuild assessment MUST provide a stepwise checklist suitable for another operator to follow.
- **FR-008**: A "full rebuild" MUST mean starting from a machine with only PVE installed, using backups stored on the NAS and shared over NFS.
- **FR-009**: The audit MUST include all environments/nodes represented in the repository.
- **FR-010**: The audit MUST use a separate “DR/maintenance-only” status for items used only in disaster recovery or maintenance windows.
- **FR-011**: The audit MUST include a full runtime inventory for all in-scope items to validate usage and classification.
- **FR-012**: The audit MUST prioritize remediation actions by rebuild/DR criticality.

### Key Entities *(include if feature involves data)*

- **Inventory Item**: Any repository component or operational process under review, with purpose, usage status, and evidence.
- **Finding**: A documented issue, gap, or anti-pattern discovered during the audit.
- **Recommendation**: A prioritized action that resolves a finding or reduces operational risk.
- **Rebuild Step**: A discrete step required to reach a functional baseline system.
- **Storage Mount**: A shared mount used by LXCs, including its management coverage status.
- **Environment Scope**: The set of nodes and environments included in the audit.

## Success Criteria *(mandatory)*

<!--
  ACTION REQUIRED: Define measurable success criteria.
  These must be technology-agnostic and measurable.
-->

### Measurable Outcomes

- **SC-001**: 100% of in-scope repository components are inventoried with a purpose and usage status.
- **SC-002**: At least 90% of inventory items have evidence-backed classification; the remainder are explicitly marked for review.
- **SC-003**: The rebuild checklist can be executed by a second operator to reach the defined baseline within one working day.
- **SC-004**: All LXC shared mounts in scope are mapped to their management coverage, with zero untracked mounts.

## Assumptions

- Operators can provide access to necessary environment details when requested.
- Existing documentation reflects intended system behavior unless evidence suggests otherwise.
- The audit focuses on improving reliability and rebuild readiness without expanding system scope.
