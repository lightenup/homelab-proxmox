# Feature Specification: Automated Testing Refactor

**Feature Branch**: `027-automated-testing-refactor`
**Created**: 2026-01-13
**Status**: Draft
**Input**: User description: "Automated testing refactor: introduce a single automation runner for LAB/PROD plan+apply while preserving evidence packs and workflow UX; add strong automated tests including unit+golden tests, nightly mutation testing, infrastructure role testing, and infrastructure test harness checks."

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

### User Story 1 - Deterministic Automation Entry Point (Priority: P1)

As an operator, I want a single automation entry point for running LAB/PROD plan and apply flows for a service, so that automation behavior is consistent, easier to test, and easier to reason about.

**Why this priority**: A stable entry point is the foundation for reducing shell glue and for adding meaningful automated tests without changing the workflow UX.

**Independent Test**: Run the automation runner in a safe, self-contained mode (using fixtures or a non-production target) and confirm it produces a bounded run summary and expected exit code without requiring changes to the workflow UX.

**Acceptance Scenarios**:

1. **Given** a service name and environment, **When** the automation runner is invoked to run a plan, **Then** it produces a bounded summary and an evidence pointer that can be used for troubleshooting.
2. **Given** a service name and environment, **When** the automation runner is invoked to run an apply, **Then** it produces a bounded summary and evidence pointers covering each executed phase.

---

### User Story 2 - Evidence-First Summaries With Golden Coverage (Priority: P1)

As an operator, I want run summaries to be deterministic, bounded, and derived from evidence packs, so I can quickly understand outcomes without downloading large artifacts or exposing secrets.

**Why this priority**: Run summary quality is a core part of operational safety and workflow usability; it must remain stable while refactoring orchestration.

**Independent Test**: Generate summaries from known fixture evidence packs and compare output to expected “golden” results.

**Acceptance Scenarios**:

1. **Given** a known-good evidence pack fixture, **When** a summary is generated, **Then** it matches the stored expected output.
2. **Given** a failure evidence pack fixture, **When** a summary is generated, **Then** it includes bounded error context and clear next steps.

---

### User Story 3 - PR Validation Suite That Catches Regressions Early (Priority: P2)

As a maintainer, I want fast, automated checks on pull requests that detect orchestration and infrastructure regressions, so failures are caught before they reach LAB or PROD runs.

**Why this priority**: Most mistakes should be prevented before they require remote executor debugging; this improves reliability and shortens feedback loops.

**Independent Test**: Run the validation suite locally (or in CI) and confirm it fails on known-bad inputs (formatting errors, invalid configurations, failing unit tests) and passes on known-good baselines.

**Acceptance Scenarios**:

1. **Given** a pull request with broken formatting or invalid infrastructure configuration, **When** CI runs, **Then** it fails with actionable output.
2. **Given** a pull request that changes summary generation behavior unintentionally, **When** CI runs, **Then** golden tests fail and show a bounded diff.

---

### User Story 4 - Nightly Deeper Verification (Priority: P2)

As a maintainer, I want nightly deeper verification (including mutation-style checks and broader role/infrastructure tests), so silent logic bugs are more likely to be detected even when unit tests pass.

**Why this priority**: Refactoring orchestration benefits from stronger correctness checks than unit tests alone.

**Independent Test**: Run the nightly suite on a scheduled run and confirm it produces a clear pass/fail signal and stores artifacts/logs without leaking secrets.

**Acceptance Scenarios**:

1. **Given** a nightly run, **When** deeper verification completes, **Then** it reports a clear overall status and links to relevant evidence/artifacts.
2. **Given** a logic defect that normal unit tests do not detect, **When** deeper verification runs, **Then** it fails and points to the impacted module/behavior.

---

### User Story 5 - Incremental Migration Without Workflow UX Changes (Priority: P3)

As an operator, I want the existing automation workflows to keep the same intent and surface area while the internals are refactored, so operational habits and approval flows do not change.

**Why this priority**: Operational safety depends on stable, familiar workflow behavior.

**Independent Test**: Validate that existing workflows continue to accept the same inputs, produce the same key outputs (summaries, evidence pointers), and enforce the same gates.

**Acceptance Scenarios**:

1. **Given** an existing workflow dispatch, **When** the workflow runs after a refactor slice, **Then** it still accepts the same inputs and produces the same summary/evidence semantics.
2. **Given** a workflow run that fails, **When** an operator reads the run summary, **Then** it provides actionable troubleshooting guidance without requiring changes to the workflow UI.

---

### Edge Cases

- Automation runner is invoked with an unknown service name.
- Automation runner is invoked with an unknown environment.
- Evidence root is missing, not writable, or partially written due to an interruption.
- Remote executor is missing required dependencies; failure must be detected early with remediation guidance.
- A plan is produced, but apply is attempted with mismatched provenance (different source revision or mismatched plan reference).
- Partial failure: infrastructure changes succeed but post-apply validation fails.
- Partial failure: infrastructure changes fail after some steps completed; summary must reflect what did and did not run.
- Output size risks becoming unbounded; summaries must remain bounded.
- Secrets appear in raw logs; summaries must not include secrets and should avoid echoing sensitive values.
- Non-interactive environments (CI) must not block on interactive prompts.
- Drift between “what was planned” and “what is applied” must be detected or clearly communicated.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST provide a single automation entry point that can execute plan and apply flows for a given service and environment.
- **FR-002**: The system MUST accept stable, explicit inputs for orchestration runs, including at minimum: service, environment, and an optional source revision identifier.
- **FR-003**: The system MUST produce a bounded run summary and must provide evidence pointers sufficient for troubleshooting.
- **FR-004**: The system MUST preserve the existing “evidence pack” model as the source of truth for run outcomes.
- **FR-005**: The system MUST keep “plan” semantics limited to infrastructure planning outputs (planning remains distinct from configuration/application steps).
- **FR-006**: The system MUST keep the existing workflow UX effectively unchanged (same intent and surface area), while permitting internal refactors.
- **FR-007**: The system MUST preserve separation of concerns in evidence: planning evidence, apply evidence, and validation/health evidence must remain distinguishable.
- **FR-008**: The system MUST fail fast on missing prerequisites on the executor and MUST provide clear remediation guidance.
- **FR-009**: The system MUST ensure that apply operations can be associated with the intended plan/source revision and MUST detect or clearly communicate mismatches.
- **FR-010**: The system MUST provide a pull-request validation suite that is fast enough to run on every PR and that detects formatting, validity, and unit-level regressions.
- **FR-011**: The system MUST provide a scheduled deeper verification suite that increases confidence beyond PR checks.
- **FR-012**: The system MUST support incremental migration in independently shippable slices, each with its own automated tests.
- **FR-013**: The system MUST ensure summaries and logs do not leak secrets.

### Assumptions & Dependencies

- GitHub Actions remains the primary automation surface.
- A remote executor remains responsible for executing infrastructure changes and producing evidence packs.
- Evidence packs remain durable enough to support postmortems and regression analysis.
- “Deeper verification” may run on a schedule and can have a longer runtime than PR checks.

### Key Entities *(include if feature involves data)*

- **Orchestration Run**: A single invocation targeting one service and one environment, producing a summary, exit code, and evidence pointers.
- **Evidence Pack**: A durable record of what happened during a run, including logs and verification outputs.
- **Run Summary**: A bounded, operator-facing summary derived from evidence packs.
- **Validation Suite**: Automated checks intended to run on every pull request.
- **Deeper Verification Suite**: Scheduled checks intended to detect subtler regressions (including logic defects and role/infrastructure-level issues).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of automation runs produce a bounded summary and evidence pointers.
- **SC-002**: Pull-request validation completes in under 10 minutes for typical changes.
- **SC-003**: At least 80% of orchestrator decision logic is covered by automated tests (measured by a standard test coverage metric).
- **SC-004**: Nightly deeper verification completes successfully at least 95% of nights in a rolling 30-day window (excluding planned maintenance).
- **SC-005**: When a run fails, operators can identify the failing phase and a next action from the summary in under 2 minutes.
- **SC-006**: No workflow UX regressions: existing workflow inputs/outputs used by operators remain stable across migration slices.
