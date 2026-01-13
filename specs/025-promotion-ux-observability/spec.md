# Feature Specification: Promotion UX Observability

**Feature Branch**: `025-promotion-ux-observability`  
**Created**: 2026-01-09  
**Status**: Draft  
**Input**: User description: "Improve promotion workflow UX and surface plan/failure summaries in the CI run UI (job summaries and annotations), ensuring PROD approval happens after seeing Plan(PROD), destructive applies are blocked by explicit confirms, and PROD apply uses the exact saved planfile."

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

### User Story 1 - See Plan Before Approving PROD (Priority: P1)

As an operator, I want to see a concise production plan summary before I’m asked to approve production, so I can make an informed approval decision quickly and safely.

**Why this priority**: This is the core safety and usability problem: approvals must be informed by the exact plan being approved.

**Independent Test**: Dispatch a promotion run for a service and confirm the workflow reaches a production approval step only after the production plan has completed and a plan summary is visible in the run UI.

**Acceptance Scenarios**:

1. **Given** a promotion run is started for a service, **When** the production plan completes, **Then** the run UI shows a readable production plan summary before any production approval is requested.
2. **Given** production approval is requested, **When** I review the approval step, **Then** it clearly identifies what I am approving and points to the production plan summary.

---

### User Story 2 - Destructive Changes Are Blocked by Explicit Confirms (Priority: P1)

As an operator, I want destructive changes to be blocked by default and clearly explained, so I can’t accidentally destroy or replace resources.

**Why this priority**: Preventing accidental destructive changes is a primary safety objective.

**Independent Test**: Run a promotion where the plan indicates replace/destroy operations and confirm the workflow blocks apply until the required confirmation token is provided.

**Acceptance Scenarios**:

1. **Given** the LAB plan is destructive, **When** apply would start, **Then** the run is blocked unless I provide the exact LAB destructive confirmation token.
2. **Given** the PROD plan is destructive, **When** apply would start, **Then** the run is blocked unless I provide the exact PROD destructive confirmation token, and production approval is still required.

---

### User Story 3 - Understand Changes Without Downloading Artifacts (Priority: P1)

As an operator, I want the run UI to show what will change (counts and a short resource list) and where the durable evidence is stored, so I don’t need to download and inspect evidence packs just to understand the plan.

**Why this priority**: Fast, accurate operator feedback reduces mistakes and speeds up operations.

**Independent Test**: Run a non-destructive promotion and confirm both LAB and PROD plan summaries are visible in logs and job summaries, including counts and a truncated list of affected resources.

**Acceptance Scenarios**:

1. **Given** a plan completes, **When** I look at the run output and job summary, **Then** I see counts for create/update/replace/destroy and a truncated list of affected resource addresses.
2. **Given** a plan completes, **When** I look at the summary, **Then** I see the run identifier, environment, service, and durable evidence location references.

---

### User Story 4 - Failures Are Obvious and Actionable (Priority: P2)

As an operator, I want failures to be obvious in the run UI (including key error context and next steps), so I can triage quickly without digging into large logs or evidence packs.

**Why this priority**: Failures are expected over time; minimizing time-to-triage reduces downtime and operator fatigue.

**Independent Test**: Force a failure (e.g., invalid configuration or unreachable dependency) and confirm the run UI surfaces a concise error summary with actionable next steps.

**Acceptance Scenarios**:

1. **Given** a plan fails, **When** the run ends, **Then** the run UI includes an error annotation and a short error summary explaining what failed and where to find detailed logs.
2. **Given** the production apply fails, **When** the run ends, **Then** the run UI includes clear next-step guidance and confirms that state was preserved without rollback.

---

### User Story 5 - Production Apply Uses the Exact Planned Changes (Priority: P2)

As an operator, I want production apply to use the exact saved production plan produced earlier in the run, so apply cannot drift from what I reviewed and approved.

**Why this priority**: Prevents “re-plan drift” where apply differs from what was approved.

**Independent Test**: Run a promotion and confirm the production apply stage references the specific saved production plan artifact and fails clearly if that artifact cannot be found.

**Acceptance Scenarios**:

1. **Given** the production plan succeeds, **When** production apply runs, **Then** it applies the exact saved plan artifact produced by that production plan.
2. **Given** the saved production plan artifact is missing, **When** production apply starts, **Then** it fails immediately with a clear message and operator guidance.

---

[Add more user stories as needed, each with an assigned priority]

### Edge Cases

<!--
  ACTION REQUIRED: The content in this section represents placeholders.
  Fill them out with the right edge cases.
-->

- Production approval is requested but the production plan summary is missing or incomplete.
- Apply is requested but no saved production plan artifact can be found.
- A destructive plan is detected but the operator did not provide the required confirmation token.
- State backup fails during LAB execution (non-fatal) and must be visible.
- Production apply fails after approval: run must stop, preserve state, and provide clear next steps.
- Summaries become too large: resource lists must be truncated with a clear “and N more…” indicator.

## Requirements *(mandatory)*

<!--
  ACTION REQUIRED: The content in this section represents placeholders.
  Fill them out with the right functional requirements.
-->

### Functional Requirements

- **FR-001**: The system MUST provide a single, dispatch-triggered promotion workflow that operates on exactly one service per run.
- **FR-002**: The system MUST fail fast if the requested service is not in the strict service allowlist.
- **FR-003**: The workflow MUST run in this sequence for the selected service: plan (LAB) → apply (LAB) → plan (PROD) → approval (PROD) → apply (PROD).
- **FR-004**: Production approval MUST occur only after the production plan has completed and a production plan summary is visible in the run UI.
- **FR-005**: “Destructive” MUST mean any replace or destroy operation.
- **FR-006**: When the LAB plan is destructive, LAB apply MUST be blocked by default and require the exact confirmation token `apply-lab-destructive`.
- **FR-007**: When the PROD plan is destructive, PROD apply MUST be blocked by default and require explicit operator confirmation in addition to production approval.
- **FR-008**: When a plan is not destructive, the workflow MUST NOT require a destructive confirmation token.
- **FR-009**: The run UI MUST show a concise plan summary for LAB and PROD, including:
  - run identifier
  - environment and service
  - plan counts (create/update/replace/destroy)
  - a truncated list of affected resource addresses
  - whether destructive is true/false and which confirmation token is required (if any)
  - durable evidence references (where evidence is stored and how to retrieve it)
- **FR-010**: The workflow MUST surface failures prominently in the run UI with concise context and actionable next steps.
- **FR-011**: The system MUST produce and preserve a durable evidence pack for each stage as the authoritative record.
- **FR-012**: LAB state backups MUST be best-effort (non-fatal) and their success/failure MUST be visible in the run UI summaries.
- **FR-013**: If production apply fails, the workflow MUST stop and preserve state (no automatic rollback) and MUST provide clear next steps in the run UI.
- **FR-014**: Production apply MUST use the exact saved production plan artifact created during the production plan stage; it MUST NOT silently generate a new plan.

### Key Entities *(include if feature involves data)*

- **Run Identifier**: A unique identifier used to correlate the workflow run with durable evidence and summaries.
- **Evidence Pack**: The durable audit bundle containing logs and reports for a specific stage.
- **Plan Summary**: A concise, human-readable summary of planned changes for a stage.
- **Execution Plan Artifact**: The saved “exact changes to apply” artifact created during production planning and consumed during production apply.
- **Run Log**: A controller-friendly log stream/file reference that can be surfaced in the run UI on failures.
- **Destructive Confirmation Token**: A specific operator-provided token required only when destructive changes are detected.

## Success Criteria *(mandatory)*

<!--
  ACTION REQUIRED: Define measurable success criteria.
  These must be technology-agnostic and measurable.
-->

### Measurable Outcomes

- **SC-001**: 100% of production approvals occur only after a production plan summary is visible in the run UI.
- **SC-002**: 100% of destructive applies are blocked by default and require the correct confirmation token.
- **SC-003**: 100% of successful runs publish LAB and PROD plan summaries in the run UI, including counts and a resource list (truncated when needed).
- **SC-004**: For production runs, 100% of production apply stages can be shown to reference the exact saved production plan artifact produced by the production plan stage.
- **SC-005**: For failures (plan/apply), the run UI provides a concise failure summary and actionable next steps, reducing time-to-triage compared to downloading evidence packs.
