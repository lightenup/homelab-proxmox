# Feature Specification: Pipeline Promotion UX

**Feature Branch**: `024-pipeline-promotion-ux`  
**Created**: 2026-01-09  
**Status**: Draft  
**Input**: User description: "Improve CI pipeline dispatcher UX, enforce LAB→PROD promotion with approval, automate prod.tfvars provisioning/validation on the Proxmox host without committing secrets, and generate a LAB inventory snapshot artifact in evidence + GitHub Actions artifacts."

## Problem Statement

The current single-service LXC deploy workflow is effective but has operational friction:

- Workflow dispatch UX is cluttered (free-text inputs where bounded choices exist; redundant inputs that do not apply to every mode).
- Promotion is not enforced: a PROD deploy can be triggered without an earlier LAB run in the same workflow execution.
- Production runs fail due to manual tfvars provisioning and secret rotation drift on the Proxmox host.
- Prerequisite gating assumes feature branches and can block promotion runs from main.
- It is hard to answer “what’s currently in LAB” without manual inspection (pct list/config, SSH in guests).

This feature introduces a clearer dispatcher UX, a mandatory promotion pipeline (LAB → approval → PROD), automated/validated production variables provisioning on the Proxmox host, and a lightweight LAB snapshot included in evidence and uploaded as a GitHub Actions artifact.

## Goals

### A) Improve dispatcher UX

- Replace free-text inputs with bounded inputs (choices/booleans) wherever possible.
- Remove redundant inputs by splitting workflows when it improves clarity.
- Make it obvious which inputs apply to LAB-only runs vs promotion runs.

### B) Enforce promotion flow

- A PROD deploy MUST always include a LAB deploy earlier in the same workflow run.
- Require explicit approval between LAB and PROD (protected production approval gate).
- Preserve destructive-change gating as a separate explicit acknowledgement.

### C) Automate prod.tfvars provisioning/validation (without committing secrets)

- Ensure `prod.tfvars` exists on the Proxmox host before any PROD apply.
- Render `prod.tfvars` from a committed template/example plus secrets sourced from the pipeline’s production secrets store.
- Validate token id equals `terraform@pve!terraform-token` and secret is present/non-placeholder.
- Capture proof in evidence (redacted summary + hash) and never emit the secret.
- Keep Terraform state local on the Proxmox host.

### D) Promote from any branch

- Prerequisite gating MUST not require a feature branch by default.
- Promotion runs MUST not require any special override input; operators rely on destructive confirmations and the protected production approval gate.

### E) LAB inventory snapshot artifact

- Produce a lightweight snapshot during plan/apply runs and optionally on-demand.
- Include containers (vmid/hostname/status/IPv4), per-service pointers to latest evidence/state paths, and mount status checks (e.g. `/media/video` mounted RO when declared).
- Store snapshot in the evidence pack and upload it as a GitHub Actions artifact.

## Non-goals

- Do not redesign Terraform modules or Ansible roles for services.
- Do not move Terraform state to a remote backend.
- Do not refactor the whole harness/scripts into a different language.

## Assumptions

- Terraform state continues to live locally on the Proxmox host (per-service state).
- The orchestration model remains “single service per run” with a service allowlist.
- Shared media remains mounted in guests at `/media/video` read-only from `192.168.1.109:/volume1/video` for services that declare it.
- The pipeline supports a protected production approval gate with required reviewers.

## Terminology

- **LAB / PROD**: Non-production vs production environments.
- **Evidence pack**: A run-specific audit bundle (logs + reports) used to prove what happened in a deploy.
- **`prod.tfvars`**: The production variables/configuration file consumed by the deploy process (contains both non-secret settings and secret values).
- **Hash**: A one-way fingerprint used to prove a file’s contents without exposing the contents.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Run a LAB deploy with clean inputs (Priority: P1)

As an operator, I want to run a LAB plan/apply for a single service using a minimal, clear dispatcher UI so I can safely iterate and validate changes.

**Why this priority**: Most executions are LAB. A clear UX reduces operator error and makes the pipeline easy to use.

**Independent Test**: Can be fully tested by dispatching the LAB pipeline for a service and confirming that it runs to completion and produces a valid evidence pack and uploaded snapshot artifact.

**Acceptance Scenarios**:

1. **Given** a service in the allowlist, **When** I dispatch “LXC Deploy (LAB)” with plan-only, **Then** the job runs plan, produces an evidence pack, and uploads a snapshot artifact.
2. **Given** a service in the allowlist, **When** I dispatch “LXC Deploy (LAB)” with apply enabled, **Then** the job runs plan+apply and evidence verifies offline.

---

### User Story 2 - Promote a service from LAB to PROD with approval (Priority: P1)

As an operator, I want a single “promote” workflow that always deploys to LAB first, then pauses for explicit approval, then deploys to PROD, so PROD is only changed after a successful LAB run in the same execution.

**Why this priority**: This enforces the desired safety policy and prevents accidental PROD-only deployments.

**Independent Test**: Can be tested by dispatching the promote workflow and confirming LAB apply runs before the PROD stage becomes available; PROD requires approval and then completes with evidence.

**Acceptance Scenarios**:

1. **Given** I dispatch “LXC Promote (LAB → PROD)”, **When** LAB apply completes successfully, **Then** the workflow pauses awaiting production approval.
2. **Given** the PROD environment approval is granted, **When** the workflow proceeds, **Then** PROD plan/apply completes for the same service and produces evidence that verifies offline.

---

### User Story 3 - Avoid PROD failures caused by missing/invalid prod tfvars (Priority: P1)

As an operator, I want PROD deployments to automatically provision and validate `prod.tfvars` on the Proxmox host so I don’t have to paste secrets manually and risk drift.

**Why this priority**: This is a common cause of deployment failures and operational drift.

**Independent Test**: Can be tested by removing/invalidating prod.tfvars on the Proxmox host and running the promote workflow; it should regenerate prod.tfvars, validate it, and proceed without exposing secrets.

**Acceptance Scenarios**:

1. **Given** `prod.tfvars` is missing on the Proxmox host, **When** PROD stage starts, **Then** the workflow provisions it and records proof in evidence without logging secrets.
2. **Given** token id does not match `terraform@pve!terraform-token`, **When** PROD stage starts, **Then** the workflow fails before apply with a clear error recorded in evidence.

---

### User Story 4 - Promote from any branch (Priority: P2)

As an operator, I want to promote from either a feature branch or main without an extra override checkbox, while still keeping the existing safety controls.

**Why this priority**: Removing special-case UX reduces operator confusion while keeping the existing approval and destructive-change gates.

**Independent Test**: Dispatch the promote workflow from `main` and from a feature branch; both should proceed normally and still require an approval gate before PROD changes.

**Acceptance Scenarios**:

1. **Given** the workflow is triggered from `main`, **When** it runs, **Then** it proceeds without requiring a special override input and still requires production approval before PROD.
2. **Given** the workflow is triggered from a feature branch, **When** it runs, **Then** it behaves the same and still requires production approval before PROD.

---

### User Story 5 - View “what’s in LAB” quickly (Priority: P2)

As an operator, I want a snapshot artifact that summarizes LAB containers, service state paths, mount checks, and evidence pointers so I can understand current LAB state quickly.

**Why this priority**: Improves observability and reduces ad-hoc debugging.

**Independent Test**: Can be tested by running plan-only and verifying the snapshot artifact contains the required fields and references.

**Acceptance Scenarios**:

1. **Given** a plan run completes, **When** I open the uploaded snapshot artifact, **Then** I can see container list and evidence pointers for the service.
2. **Given** a service declares a shared media mount, **When** snapshot is generated, **Then** it records whether `/media/video` is mounted and read-only.

### Edge Cases

- PROD approval is granted, but the container state changed since LAB (e.g., container stopped): workflow should fail safely and record evidence.
- tfvars provisioning succeeds but secrets are placeholder/empty: workflow must fail before plan/apply.
- Snapshot generation is partially available (some containers not accessible): snapshot should still be created with per-item errors captured.
- Destructive plan detected in LAB or PROD: workflow must require explicit destructive confirmation for that environment before apply.

## Workflow UX Design

### Workflow Split

Because the pipeline dispatcher cannot dynamically hide inputs based on other inputs, workflows should be split to keep inputs minimal and relevant:

1. `LXC Deploy (LAB)`
2. `LXC Promote (LAB → PROD)`



### Dispatcher Inputs

#### LXC Deploy (LAB)

- `service`: choice (generated from allowlist)
- `apply`: boolean (plan-only vs plan+apply)
- `confirm_destructive`: choice/boolean used only when destructive changes are detected

#### LXC Promote (LAB → PROD)

- `service`: choice (generated from allowlist)
- `confirm_destructive_lab`: choice/boolean (only required if LAB plan is destructive)
- `confirm_destructive_prod`: choice/boolean (only required if PROD plan is destructive)

Notes:

- There is no `environment` selector in promote; promotion always runs LAB then PROD.
- PROD remains protected by an explicit production approval gate.

## Promotion Pipeline Design

### Job Layout

Promote workflow jobs:

1. `plan_lab` → 2. `apply_lab` → 3. `approval_gate` → 4. `plan_prod` → 5. `apply_prod`

Where:

- `approval_gate` is implemented using the pipeline’s protected production approval gate.
- Both `apply_lab` and `apply_prod` are blocked when destructive changes are detected unless the respective destructive confirmation is provided.

### Concurrency

- Concurrency key: service + stage, preventing overlapping deploys for the same service.
- Promotion workflow must prevent concurrent promotions for the same service.

## tfvars Automation Design (PROD)

### Rendering Model

- A committed template/example file is the source-of-truth for non-secret settings.
- Secrets (e.g., Proxmox API token secret) are sourced from the pipeline’s production secrets store.
- Rendering happens on the Proxmox host into the standard location for production variables.
- Rendering is idempotent and validated on every PROD run.

### Validation Rules

- Token id must match `terraform@pve!terraform-token`.
- Token secret must be present and must not match known placeholder patterns.
- A proof artifact is recorded:
  - A hash of the rendered file
  - A redacted summary showing non-secret fields (e.g., API URL, token id) and a “secret_present=true” boolean

### Evidence Proof

- Evidence includes:
  - `reports/prod-tfvars/provisioning.txt` (redacted)
  - `reports/prod-tfvars/prod.tfvars.sha256`
  - `reports/prod-tfvars/validation.json`

No secrets are stored in evidence.

## LAB Inventory Snapshot Design

### Snapshot Contents (Minimum)

The snapshot is a single JSON document containing:

- `generated_at`
- `environment`
- `containers`: list of { vmid, hostname/name, status, ipv4 }
- `services`: list of service roots detected + state paths
- `errors`: any collection errors (non-fatal unless required fields are missing)

Optional enhancements (later story):

- `latest_evidence`: mapping service → latest RUN_ID + path
- `mount_checks`: per-service checks for declared mounts (e.g., `/media/video` mounted and read-only)

### Storage

- Store in evidence pack: `reports/lab-snapshot.json`
- Upload as GitHub Actions artifact for each plan/apply run.

## Evidence Contract Changes

- Extend the service-deploy evidence profile to include:
  - PROD tfvars provisioning proof (redacted + hash)
  - LAB snapshot JSON
- Offline verification must validate presence/format of these artifacts for relevant phases.
- Update fixtures as needed to keep the offline verifier authoritative.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST provide a LAB deploy workflow with bounded inputs (service choice and apply boolean) and no environment selector.
- **FR-002**: The system MUST provide a promote workflow that always executes LAB before PROD in the same workflow run.
- **FR-003**: The system MUST require an explicit approval step between LAB and PROD (via a protected production approval gate).
- **FR-004**: The system MUST preserve destructive-change gating for both LAB and PROD applies.
- **FR-005**: The system MUST ensure PROD tfvars exists on the Proxmox host before any PROD plan/apply and MUST not commit secrets to the repository.
- **FR-006**: The system MUST validate the Proxmox token id equals `terraform@pve!terraform-token` before PROD apply.
- **FR-007**: The system MUST validate the Proxmox token secret is non-empty and non-placeholder before PROD apply.
- **FR-008**: The system MUST record a redacted summary and hash of the rendered prod.tfvars in the evidence pack.
- **FR-009**: The system MUST allow promotion runs from any branch without a special override input, while still enforcing destructive confirmations and production approval gating.
- **FR-010**: The system MUST generate a LAB inventory snapshot during plan/apply runs and store it in the evidence pack.
- **FR-011**: The system MUST upload the LAB snapshot as a GitHub Actions artifact for quick access.
- **FR-012**: The system MUST keep all existing guardrails (no -target, service allowlist, host-path bind mount rejection, offline evidence verification).

### Key Entities *(include if feature involves data)*

- **Evidence Pack**: A run-scoped directory containing logs and reports required for offline verification.
- **tfvars Render Proof**: A redacted record that the PROD variable file exists and was validated (hash + non-secret summary).
- **LAB Snapshot**: A structured summary of container and service state intended for quick operator visibility.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of production deploys executed via the pipeline include a successful LAB apply earlier in the same workflow run.
- **SC-002**: PROD deploy failures caused by missing/placeholder `prod.tfvars` are reduced to 0 in normal operation.
- **SC-003**: For each plan/apply run, a LAB snapshot artifact is available for download and includes vmid/hostname/status/IPv4 for all containers.
- **SC-004**: Offline evidence verification passes for 100% of successful LAB deploy and promote runs.

## Testing Plan

- Dispatcher UX tests:
  - Confirm `service` is a choice and cannot be arbitrary input.
  - Confirm inputs differ between LAB deploy and promote workflow.
- Promotion flow tests:
  - Confirm PROD jobs are blocked until LAB completes.
  - Confirm PROD requires environment approval.
- tfvars provisioning tests:
  - Start with missing prod.tfvars on the Proxmox host and confirm provisioning proof exists.
  - Start with invalid token id and confirm run is blocked with evidence.
- Branch behavior tests:
  - Trigger promote from `main`: must proceed normally and still require PROD approval.
  - Trigger promote from a feature branch: must proceed normally and still require PROD approval.
- Snapshot tests:
  - Snapshot exists in evidence pack and as artifact.
  - Snapshot includes required fields and errors are captured when checks cannot run.

## Rollback Plan

- Revert to the previous workflow(s) if promotion gating blocks necessary operations.
- If tfvars provisioning causes unexpected failures, allow a temporary bypass that still records evidence and requires approvals.
