# Feature Specification: Lab Harness Confidence Suite

**Feature Branch**: `019c-lab-confidence-suite`
**Created**: 2025-12-30
**Status**: Draft
**Input**: User description: "Lab Harness “Confidence Suite” + Semantic Hardening"

## Clarifications

### Session 2025-12-30

- Q: What is the execution strategy for the "Confidence Suite"? → A: Run all validation profiles (`bootstrap`, `hypervisor-control-plane`, `hypervisor-nested-workload`) sequentially plus the Safety Suite.
- Q: How should the Evidence Pack be structured? → A: Use a structured layout with subdirectories (`logs/`, `config/`, `validation/`) to keep the root clean.

## Glossary

- **Validation Profile**: A named, stable configuration for a lab run.
    - `bootstrap`: Basic connectivity and Ansible convergence (formerly Tier 1).
    - `hypervisor-control-plane`: Installs and verifies PVE control plane on Debian 13 (formerly Tier 2 Min).
    - `hypervisor-nested-workload`: Control plane + nested VM + mini-service smoke test (formerly Tier 2 Plus).
    - `rebuild-fidelity`: (Future/Tier 3) Full rebuild from ISO/IPXE, out of scope for this iteration.
- **Evidence Pack**: A directory containing all artifacts from a run, including a manifest and structured results.
- **Evidence Retention Policy**: The policy of keeping only the last N (default 5) Evidence Packs.
- **Confidence Suite**: A comprehensive test run that executes **all validation profiles (`bootstrap`, `hypervisor-control-plane`, `hypervisor-nested-workload`) sequentially** and negative tests to validate the harness itself.
- **Safety Suite**: A set of negative tests designed to verify that guardrails correctly prevent unsafe execution.

## User Scenarios & Testing

### User Story 1 - Run Validation Profiles (Priority: P1)

As a platform engineer, I want to run specific validation profiles so that I can test different layers of the infrastructure stack with appropriate fidelity.

**Why this priority**: Core functionality to replace ambiguous "tiers" with semantic profiles.

**Independent Test**: Run `pve-lab run --profile <name>` and verify correct behavior.

**Acceptance Scenarios**:

1. **Given** a clean lab environment, **When** I run `pve-lab run --profile bootstrap`, **Then** the lab VM is provisioned and the bootstrap playbook converges.
2. **Given** a clean lab environment, **When** I run `pve-lab run --profile hypervisor-control-plane`, **Then** PVE is installed, hardened, and API checks pass.
3. **Given** a host with nested virt enabled, **When** I run `pve-lab run --profile hypervisor-nested-workload`, **Then** a nested VM is created, a mini-service runs, and I can access it from the lab host.

### User Story 2 - Evidence Collection (Priority: P1)

As a platform engineer, I want a structured Evidence Pack generated for every run so that I have a reliable audit trail and debugging context.

**Why this priority**: Essential for observability and "confidence".

**Independent Test**: Run any profile and inspect `artifacts/019-lab/<runid>/`.

**Acceptance Scenarios**:

1. **Given** any run (success or fail), **When** the run completes, **Then** an Evidence Pack is created containing `evidence_manifest.json` and `checks.json`.
2. **Given** multiple runs, **When** I check the artifacts directory, **Then** only the last 5 Evidence Packs are retained.

### User Story 3 - Safety Verification (Priority: P2)

As a platform engineer, I want to run a Safety Suite of negative tests so that I can trust the harness will not damage production.

**Why this priority**: "Keep prod safe" is a non-negotiable requirement.

**Independent Test**: Run the safety suite command and verify it reports success (meaning all unsafe actions were blocked).

**Acceptance Scenarios**:

1. **Given** a command targeting the production inventory, **When** I run the safety suite, **Then** the harness blocks the action and records an `EXPECTED_FAIL`.
2. **Given** a missing lab marker, **When** I attempt a run, **Then** the harness refuses to proceed.

### Edge Cases

- **Concurrent Runs**: If a run is attempted while another is in progress, the system MUST detect the lock and abort immediately.
- **Host Resource Exhaustion**: If the host cannot support nested virtualization (e.g., insufficient RAM/CPU), the `hypervisor-nested-workload` profile MUST fail fast with a clear error message, rather than hanging.
- **Partial Failure**: If a run fails midway, the Evidence Pack MUST still be generated with all available logs up to the failure point.

## Requirements

### Functional Requirements

- **FR-001**: The CLI MUST support `--profile` argument with values: `bootstrap`, `hypervisor-control-plane`, `hypervisor-nested-workload`.
- **FR-002**: The system MUST generate an Evidence Pack for every run, containing `evidence_manifest.json` (metadata) and `checks.json` (structured results).
- **FR-003**: The system MUST implement an Evidence Retention Policy, keeping exactly the last 5 Evidence Packs.
- **FR-004**: The `hypervisor-nested-workload` profile MUST create a nested VM, run a mini-service (e.g., HTTP server), and verify connectivity.
- **FR-005**: The system MUST provide a "Confidence Suite" command that runs **all** positive tests (profiles) and negative tests (safety checks).
- **FR-006**: Negative tests MUST verify that operations against non-lab inventories or missing markers are blocked.
- **FR-007**: All assertions MUST be logged in a human-readable format and recorded structurally in `checks.json`.
- **FR-008**: The system MUST clean up all artifacts (lab VMs, nested VMs) after a successful run unless `--keep` is specified.
- **FR-009**: The Evidence Pack MUST use a structured layout with subdirectories: `logs/`, `config/`, and `validation/`.

### Key Entities

- **Validation Profile**: Configuration defining the scope and depth of a test run.
- **Evidence Pack**: Structured output artifact.
- **Check**: A single assertion (e.g., `OS_DEBIAN_13`, `REPO_SIGNED_BY`).

## Success Criteria

### Measurable Outcomes

- **SC-001**: 100% of runs (success or fail) produce a valid Evidence Pack with manifest and checks.
- **SC-002**: `hypervisor-nested-workload` profile successfully verifies a nested mini-service on compatible hardware.
- **SC-003**: Safety Suite passes 100% of negative tests (confirming guards are active).
- **SC-004**: No residual VMs (lab or nested) remain after a full Confidence Suite run.
