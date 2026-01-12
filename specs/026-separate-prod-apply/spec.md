# Feature Specification: Separate PROD Apply Workflow

**Feature Branch**: `026-separate-prod-apply`  
**Created**: 2026-01-10  
**Status**: Draft  
**Input**: User description: "Separate LAB vs PROD workflows: interactive PROD approval and separate PROD apply using saved plan"

## Clarifications

### Session 2026-01-10

- Q: How should the PROD promotion pipeline select the git SHA it enforces? → A: Add `ref` input to PROD promote dispatch; checkout that ref; enforce all evidence/provenance equals that ref's SHA.
- Q: If LAB deploy or confidence suite fails, should the pipeline still be able to continue to PROD? → A: Yes; still generate the PROD plan, and allow continuing to PROD approval/apply only when an operator explicitly sets an override checkbox at the PROD approval/apply gate (override does not affect LAB).
- Q: When the override checkbox is set, what confirmation mechanism should be required? → A: Checkbox only (boolean input).
- Q: When override is used, should destructive confirmation still be required? → A: No; override also bypasses destructive confirmation requirements.
- Q: If the LAB deploy step fails, what should happen with the confidence suite step? → A: Still run confidence suite anyway (best-effort).

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

### User Story 1 - Promote to LAB Without Triggering PROD (Priority: P1)

As an operator, I want to run the LAB promotion flow without automatically attempting any production steps, so I can iterate safely and avoid accidentally reaching production gates.

**Why this priority**: This is the core UX change: production should never be “along for the ride” during a LAB-focused run.

**Independent Test**: Trigger a LAB promotion run for a service and confirm the run completes without any production approval or production apply being requested.

**Acceptance Scenarios**:

1. **Given** I start a LAB promotion run for a service, **When** the run completes, **Then** no production approval is requested and no production apply is attempted.
2. **Given** I start a LAB promotion run, **When** I review the run output, **Then** it clearly communicates that production is not being applied in this run.

---

### User Story 2 - Promote to PROD With Interactive Approval After LAB Confidence (Priority: P1)

As an operator, I want production promotion to be a separate, explicitly triggered run that first deploys to LAB and runs the full confidence suite (strictly for the same git SHA), then shows me the LAB results and the PROD plan, and only then pauses for interactive approval, so I can review evidence before I approve production apply.

**Why this priority**: Production changes must be explicit and reviewable. A separate run with an approval pause makes the operator intent unambiguous.

**Independent Test**: Trigger a production promotion run; confirm it runs LAB deploy + full confidence suite, generates a PROD plan, publishes both LAB evidence pointers and PROD plan summary, then pauses at an approval gate and only proceeds after approval.

**Acceptance Scenarios**:

1. **Given** I start a production promotion run, **When** LAB deploy and the full confidence suite complete successfully, **Then** the workflow generates and publishes the PROD plan summary before requesting approval.
2. **Given** the workflow reaches the approval gate, **When** approval is not granted, **Then** production apply is not executed.
3. **Given** LAB deploy fails or the confidence suite fails, **When** the workflow generates and publishes the PROD plan summary, **Then** it MUST clearly indicate the LAB gate failure and require an explicit override checkbox to proceed to production apply.
4. **Given** LAB deploy fails or the confidence suite fails, **When** approval is granted but the override checkbox is not set, **Then** production apply is not executed.
5. **Given** LAB deploy fails or the confidence suite fails, **When** approval is granted and the override checkbox is set, **Then** the workflow may proceed to production apply.
6. **Given** LAB deploy fails, **When** the workflow continues, **Then** the confidence suite is still attempted (best-effort) and its outcome is surfaced in the run summary.

---

### User Story 3 - PROD Apply Uses a Saved Plan Reference (Priority: P2)

As an operator, I want production apply to use a saved production plan reference, so I can ensure what I approve and apply is stable and reviewable.

**Why this priority**: This prevents accidental drift and makes the approval decision traceable to a specific planned change set.

**Independent Test**: In the production promotion run, confirm PROD apply uses the saved plan bytes from the PROD plan generated earlier in the run; confirm the run fails fast if the plan reference is missing or mismatched.

**Acceptance Scenarios**:

1. **Given** a PROD plan reference exists for the same service and git SHA, **When** production apply runs, **Then** it applies changes corresponding to that saved plan.
2. **Given** the PROD plan reference is missing or mismatched, **When** production apply starts, **Then** it fails immediately with guidance.

---

### Edge Cases

- Production apply is started without an approval action being granted.
- Production apply is started with a plan reference that does not exist.
- Production apply is started with a plan reference that belongs to a different service or environment.
- A destructive plan is detected and the operator did not provide the required destructive confirmation token.
- A run fails early (preflight/plan) and still needs to surface actionable evidence pointers and error context.
- The run summary output becomes too large and must remain bounded.
- LAB deploy completed, but the full confidence suite failed.
- LAB deploy and confidence suite passed, but the PROD plan failed.
- LAB deploy failed or confidence suite failed, and the operator intentionally overrides the gate to continue to PROD approval/apply.
- LAB deploy failed or confidence suite failed, and the operator proceeds with override; destructive confirmation is bypassed in this mode.
- LAB deploy failed, but the confidence suite was still attempted (best-effort) and produced evidence.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST provide a LAB promotion workflow that completes without requesting production approval and without attempting production apply.
- **FR-002**: The system MUST provide a separate production promotion workflow that is only executed when an operator explicitly triggers it.
- **FR-003**: The production promotion workflow MUST deploy to LAB and run the full confidence suite before requesting any production approval.
- **FR-003a**: The confidence suite MUST be attempted even if the LAB deploy step fails (best-effort), and the suite outcome MUST be surfaced in the run summary.
- **FR-004**: The production promotion workflow MUST enforce strict git SHA alignment between: LAB deploy, confidence suite, PROD plan, and PROD apply.
- **FR-005**: The production promotion workflow MUST include an interactive approval gate that blocks production apply until approval is granted.
- **FR-006**: The production promotion workflow MUST not proceed unless approval is granted.
- **FR-006a**: If LAB deploy fails or the confidence suite fails, the workflow MUST still generate and publish the PROD plan summary and plan reference, and MUST clearly communicate the LAB gate failure in the run summary.
- **FR-006b**: The workflow MUST support an explicit operator-provided override input (checkbox/boolean) that applies only to the production approval/apply decision (it MUST NOT affect LAB execution).
- **FR-006b1**: The override checkbox MUST be required/used only when LAB deploy fails or the confidence suite fails.
- **FR-006b2**: The override mechanism MUST be a boolean input only (no additional typed confirmation token required).
- **FR-006c**: Production apply MUST remain blocked by the production approval gate, and MUST NOT run unless approval is granted.
- **FR-006d**: When LAB deploy fails or the confidence suite fails, production apply MUST NOT run unless the override checkbox is set.
- **FR-007**: The system MUST use a saved production plan reference for production apply.
- **FR-008**: The system MUST validate that the production plan reference matches the requested service and targets production.
- **FR-009**: The system MUST fail fast with clear guidance when the production plan reference is missing, cannot be found, or does not match the requested service/environment.
- **FR-010**: “Destructive” MUST mean any replace or destroy operation.
- **FR-011**: Destructive production applies MUST be blocked by default and require an explicit destructive confirmation token, unless the override checkbox is set.
- **FR-012**: Non-destructive production applies MUST NOT require a destructive confirmation token.
- **FR-013**: Each run MUST publish a concise, bounded run summary including: service, environment, outcome, and evidence location pointers.
- **FR-014**: Before requesting production approval, the run summary MUST display:
  - the LAB deploy evidence pointer(s)
  - the confidence suite evidence pointer(s)
  - the PROD plan summary and the plan reference
- **FR-014a**: The production promotion workflow MUST publish a short, bounded list of recent commits (SHAs + subjects) for the checked-out ref in the run summary to help operators choose a `ref` for future runs.
- **FR-015**: On failures, the run summary MUST include a short excerpt of the most relevant error context (bounded) and clear next steps.
- **FR-016**: The system MUST not print secrets in logs or summaries.
- **FR-017**: The production promotion workflow MUST accept an explicit git ref input (e.g., branch/tag/SHA), MUST checkout that ref for execution, and MUST enforce the strict git SHA alignment checks against the checked-out SHA.

### Assumptions & Dependencies

- The system has a durable record for each run (“evidence packs”) that operators can use to troubleshoot outcomes.
- A “plan reference” is available to operators after a production plan completes, and it can be used to locate the corresponding planned change set.
- The production apply approval gate is administered by a controlled set of reviewers.

### Key Entities *(include if feature involves data)*

- **Promotion Run**: A single execution targeting one service and one environment (LAB or PROD), producing a run outcome and evidence.
- **Plan Reference**: A stable identifier that points to a previously produced production plan for a specific service.
- **Approval Decision**: The operator action that explicitly authorizes production apply to proceed.
- **Evidence Pack**: The durable record produced by a run containing logs, summaries, and verification outputs.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of LAB promotion runs complete without requesting production approval or attempting production apply.
- **SC-002**: 100% of production promotions require an explicit operator-triggered run and an approval action before execution.
- **SC-003**: 100% of production applies are blocked unless LAB deploy + full confidence suite succeed for the same git SHA, or an explicit override checkbox is set.
- **SC-004**: 100% of production apply runs fail fast when the plan reference is missing or does not match the requested service/environment.
- **SC-005**: For failed runs, operators can identify the failure cause and next step from the run summary in under 2 minutes (without downloading artifacts).
