# Implementation Plan: Pipeline Promotion UX

**Branch**: `024-pipeline-promotion-ux` | **Date**: 2026-01-09 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/home/runner/work/homelab-proxmox/homelab-proxmox/specs/024-pipeline-promotion-ux/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

This feature improves the CI/CD pipeline UX for LXC container deployments by:
1. Replacing free-text workflow inputs with bounded choices (service selector from allowlist, boolean flags)
2. Enforcing a mandatory LAB → approval gate → PROD promotion flow to prevent accidental production-only deploys
3. Automating production tfvars provisioning and validation on the Proxmox host without committing secrets to the repository
4. Adding an explicit hotfix path for main branch deployments with required confirmation and approval
5. Generating LAB inventory snapshot artifacts (JSON format) that capture container state, service evidence pointers, and mount validation

The technical approach uses GitHub Actions workflow splits (separate LAB-only and Promote workflows), GitHub Environment protection for PROD approval gates, Bash-based tfvars templating with secret injection from GitHub Secrets, and evidence-based verification with offline validation of all artifacts including redacted tfvars provisioning proofs and LAB snapshots.

## Technical Context

**Language/Version**: Bash 5.x (Proxmox host scripts), GitHub Actions YAML (workflow definitions), Python 3.x (evidence verification)  
**Primary Dependencies**: 
- GitHub Actions (workflow_dispatch, environments, artifacts)
- Terraform 1.x (telmate/proxmox provider for LXC resources)
- Ansible 2.x (configuration management in LXCs)
- rsync/ssh (repository sync to Proxmox host)
- jq (JSON processing for snapshots and evidence)

**Storage**: 
- Terraform state: local on Proxmox host at `/var/lib/homelab-proxmox/state/services/<service>/`
- Evidence packs: local on Proxmox host at `/var/lib/homelab-proxmox/artifacts/service-deploy-runs/<run_id>/`
- Production tfvars: local on Proxmox host at `/var/lib/homelab-proxmox/tfvars/prod.tfvars` (gitignored, provisioned at runtime)
- LAB snapshots: embedded in evidence packs and uploaded as GitHub artifacts

**Testing**: 
- Evidence-based verification using `scripts/lab/ci-verify.sh` with offline validation against evidence profiles
- Destructive change detection via `blast-radius.json` in evidence packs
- Idempotency verification (second apply must produce zero-change plan)
- Fixture-based contract validation in `scripts/lab/fixtures/evidence-packs/valid/`

**Target Platform**: 
- Proxmox VE 8.x host (runs Terraform/Ansible via SSH from GitHub Actions self-hosted runner)
- Debian-based LXC containers (unprivileged, managed by Terraform)
- GitHub Actions self-hosted runner (has SSH keys for `ci@pve` user)

**Project Type**: Infrastructure-as-Code / CI/CD pipeline (single repository with Terraform, Ansible, scripts, workflows)

**Performance Goals**: 
- Plan execution: <2 minutes for single-service LXC plan
- Apply execution: <5 minutes for single-service LXC apply (includes Ansible configuration)
- Evidence verification: <10 seconds offline validation per run
- Snapshot generation: <30 seconds to collect container state

**Constraints**: 
- Secrets MUST NOT be committed to repository (use local tfvars + GitHub Secrets)
- Terraform state remains local on Proxmox host (no remote backend)
- Evidence packs must be verifiable offline (no external API calls during verification)
- All production changes require explicit approval gate (GitHub Environment protection)
- Destructive changes (replace/destroy) require explicit confirmation input
- Service scope limited to allowlist in `scripts/lab/service-scope-allowlist.json`

**Scale/Scope**: 
- 6 services in allowlist (adguard, homeassistant, immich, jellyfin, monitoring, reverse_proxy)
- Single Proxmox host with ~10-20 LXC containers total (LAB + PROD environments)
- GitHub Actions workflow runs: ~5-20 per day (primarily LAB iterations)
- Evidence pack size: ~500KB-2MB per run (logs, JSON reports, redacted configs)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### I. Spec-Driven Workflow ✅
- All changes are driven by `specs/024-pipeline-promotion-ux/spec.md`
- Implementation will update spec documentation as UX and evidence contracts evolve
- Changes are scoped to workflow improvements and evidence collection (no fundamental architecture changes)

### II. Secrets Policy ✅
- **Critical**: This feature explicitly addresses the secrets policy by automating prod.tfvars provisioning WITHOUT committing secrets
- Production Proxmox API token secret will be sourced from GitHub Secrets (already configured as `PROXMOX_TOKEN_SECRET`)
- tfvars rendering happens on Proxmox host only; evidence includes redacted summary + hash proof
- No secrets will be logged or stored in evidence packs

### III. Separation of Concerns ✅
- Terraform continues to own LXC existence/sizing (no changes to Terraform modules)
- Ansible continues to own configuration inside LXCs (no changes to Ansible roles)
- This feature only modifies CI/CD orchestration and evidence collection (workflow layer)

### Provider Strategy ✅
- No changes to Terraform provider (continues using `telmate/proxmox` with `proxmox_lxc`)

### Networking ✅
- No changes to networking configuration (static IPs remain centrally defined)

### Access Control ✅
- No changes to SSH key injection or Ansible authentication model

### State Management ✅
- Terraform state remains local on Proxmox host (explicitly preserved in spec Non-goals)
- State backup to Synology continues via existing scripts (no changes)

### Storage ✅
- No changes to Immich data storage on Synology NAS
- No changes to NFS mount model for shared media

### Services Model ✅
- Service allowlist remains authoritative (`scripts/lab/service-scope-allowlist.json`)
- One LXC per service model unchanged

### CI/CD Expectations ✅
- Workflow structure improved: LAB deploy and LAB→PROD promotion explicitly separated
- Approval gates added for PROD (aligns with "clear barriers" principle)
- Destructive automation barriers preserved and enhanced (separate confirmations for LAB and PROD)

### Repo Layout ✅
- No changes to repository structure (`docs/`, `terraform/`, `ansible/`, `.github/workflows/`, `scripts/`)
- New workflows will be added to `.github/workflows/` (lxc-deploy-lab.yml, lxc-promote.yml)
- Existing `lxc-deploy.yml` may be deprecated or kept for backward compatibility during transition

**GATE RESULT**: ✅ **PASS** - All constitution principles satisfied. No violations requiring justification.

## Project Structure

### Documentation (this feature)

```text
specs/[###-feature]/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

## Project Structure

### Documentation (this feature)

```text
specs/024-pipeline-promotion-ux/
├── spec.md              # Feature specification (input)
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (workflow patterns, tfvars approaches)
├── data-model.md        # Phase 1 output (evidence entities, snapshot schema)
├── quickstart.md        # Phase 1 output (operator documentation)
├── contracts/           # Phase 1 output (workflow schemas, evidence schemas)
│   ├── workflow-lab-deploy.schema.json
│   ├── workflow-promote.schema.json
│   ├── evidence-tfvars-proof.schema.json
│   └── evidence-lab-snapshot.schema.json
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

This is an infrastructure/CI-CD project with existing structure. Changes are localized to workflows and scripts:

```text
.github/workflows/
├── lxc-deploy.yml              # EXISTING (may deprecate or keep for compatibility)
├── lxc-deploy-lab.yml          # NEW: LAB-only workflow with bounded inputs
├── lxc-promote.yml             # NEW: LAB→PROD promotion workflow with approval
└── proxmox-apply.yml           # EXISTING (unchanged)

scripts/lab/
├── pve-service-deploy          # EXISTING (extend with tfvars provisioning + snapshot)
├── guardrails.sh               # EXISTING (may extend with tfvars validation)
├── ci-verify.sh                # EXISTING (extend to validate new evidence fields)
├── verify_evidence.py          # EXISTING (extend profile to include tfvars proof + snapshot)
├── service-scope-allowlist.json # EXISTING (unchanged, used for workflow choice input)
├── lib/
│   ├── tfvars.sh               # NEW: tfvars provisioning and validation library
│   └── snapshot.sh             # NEW: LAB snapshot generation library
├── profiles.d/
│   └── service-deploy.json     # EXISTING (extend with tfvars-proof and lab-snapshot fields)
└── contracts/
    └── evidence-v2/            # NEW: extended evidence contract definitions
        ├── tfvars-proof.json
        └── lab-snapshot.json

terraform/
└── (no changes - Terraform modules unchanged)

ansible/
└── (no changes - Ansible roles unchanged)

docs/
└── (may add operator runbook for new workflows)
```

**Structure Decision**: This is a single-repository infrastructure-as-code project. Changes are surgical:
1. Add two new GitHub Actions workflows (`.github/workflows/lxc-deploy-lab.yml`, `.github/workflows/lxc-promote.yml`)
2. Extend the existing `pve-service-deploy` Bash script with tfvars provisioning and snapshot generation
3. Add two new library scripts (`lib/tfvars.sh`, `lib/snapshot.sh`) for reusable logic
4. Extend existing evidence verification to validate new evidence fields
5. Add contract schemas to document the new evidence formats

No changes to Terraform modules, Ansible roles, or repository layout. All new functionality is additive and scoped to the CI/CD orchestration layer.

## Complexity Tracking

> **No violations to track.** The Constitution Check passed without requiring any justifications. This feature is fully aligned with the homelab principles and introduces no architectural complexity.

---

## Phase 0: Outline & Research

**Goal**: Resolve all technical unknowns before design phase. Generate `research.md` with decisions, rationale, and alternatives.

### Research Tasks

#### R1: GitHub Actions Workflow Dispatch Choice Inputs
**Question**: How to generate dynamic choice lists for `workflow_dispatch` inputs from repository files (service allowlist)?

**Research areas**:
- GitHub Actions workflow_dispatch `type: choice` syntax and limitations
- Static vs dynamic choice generation (can choices reference a file in repo?)
- Workarounds if dynamic choices not supported (e.g., validation in first workflow step)
- Best practices for keeping workflow inputs in sync with allowlist files

**Decision needed**: Approach for service selector (hardcode choices vs generate from allowlist vs validate at runtime)

#### R2: GitHub Environment Protection Rules
**Question**: How to configure GitHub Environment protection for PROD approval gates?

**Research areas**:
- GitHub Environment configuration (required reviewers, wait timers)
- How `environment:` keyword in workflow jobs triggers approval gates
- Best practices for approval notifications and auditing
- Fallback/bypass mechanisms for emergencies

**Decision needed**: Environment configuration strategy (who reviews, how many approvals, timeout settings)

#### R3: Bash Templating for tfvars Provisioning
**Question**: What's the safest approach to render `prod.tfvars` from a template + secrets without exposing secrets in logs?

**Research areas**:
- Bash templating techniques (envsubst, heredocs, sed/awk, jq)
- Secret handling best practices (avoid command-line args, use file descriptors, secure temp files)
- Validation patterns for rendered files (regex checks, jq schema validation)
- Idempotency strategies (compare existing file before overwriting)

**Decision needed**: Templating approach and validation rules for prod.tfvars rendering

#### R4: tfvars Validation Rules
**Question**: How to validate prod.tfvars without exposing secrets in evidence?

**Research areas**:
- Hashing approaches (SHA256 of full file vs redacted subset)
- Redaction strategies (replace secret values with placeholders for evidence)
- Validation rules for Proxmox token format (token ID pattern, secret non-empty check)
- Evidence proof format (JSON schema for validation report)

**Decision needed**: Validation rule implementation and evidence proof schema

#### R5: LAB Snapshot Format
**Question**: What JSON schema should the LAB snapshot use for container state and evidence pointers?

**Research areas**:
- Proxmox `pct` command output parsing for container metadata
- IPv4 address extraction from LXC network config
- Mount validation approaches (check if path exists, verify read-only flag from `/proc/mounts`)
- Evidence pointer design (how to reference latest RUN_ID for a service)

**Decision needed**: JSON schema for LAB snapshot with required/optional fields

#### R6: Evidence Pack Extension Strategy
**Question**: How to extend the existing evidence profile to include tfvars proof and LAB snapshot without breaking offline verification?

**Research areas**:
- Current evidence profile schema in `scripts/lab/profiles.d/service-deploy.json`
- Evidence verification logic in `scripts/lab/verify_evidence.py`
- Backward compatibility considerations (can verification handle missing new fields for old evidence?)
- Version bumping strategy for evidence contracts

**Decision needed**: Evidence profile extension approach (new contract version vs additive fields)

#### R7: Workflow Job Dependency Patterns
**Question**: How to structure promotion workflow jobs to enforce LAB → approval → PROD sequence?

**Research areas**:
- GitHub Actions job dependency syntax (`needs:` keyword)
- Conditional job execution based on previous job outputs
- Approval gate integration (does `environment:` block job until approval?)
- Concurrency control for same-service deployments across environments

**Decision needed**: Job graph structure for promotion workflow

#### R8: Hotfix Path Design
**Question**: How to implement a safe hotfix path for main branch without weakening prerequisite gates?

**Research areas**:
- Branch name detection in workflows (`github.ref` patterns)
- Explicit override input patterns (confirmation strings, boolean flags)
- Combining override input with approval gate (both must pass)
- Audit trail considerations (how to make hotfix runs highly visible)

**Decision needed**: Hotfix input design and gate combination strategy

### Research Output

Create `specs/024-pipeline-promotion-ux/research.md` with the following structure for each research task:

```markdown
## R#: [Task Name]

### Decision
[What was chosen]

### Rationale
[Why this approach was selected]

### Alternatives Considered
[What else was evaluated and why it wasn't chosen]

### Implementation Notes
[Any specific gotchas or recommendations for implementation]
```

---

## Phase 1: Design & Contracts

**Prerequisites**: `research.md` complete with all decisions documented

**Goal**: Generate data model, API contracts, and quickstart documentation

### D1: Data Model (`data-model.md`)

Extract entities and relationships from the feature specification:

#### Entity: Evidence Pack (extended)
- **New fields**:
  - `reports/prod-tfvars/provisioning.txt` (redacted summary)
  - `reports/prod-tfvars/prod.tfvars.sha256` (hash proof)
  - `reports/prod-tfvars/validation.txt` (validation report)
  - `reports/lab-snapshot.json` (LAB inventory snapshot)
- **Validation rules**:
  - tfvars proof required only for PROD environment runs
  - LAB snapshot required for all plan/apply runs (LAB and PROD)
  - Offline verification must validate presence and schema of new fields

#### Entity: tfvars Provisioning Proof
- **Fields**:
  - `timestamp`: ISO 8601 timestamp of provisioning
  - `template_source`: path to template file used
  - `rendered_path`: path to rendered prod.tfvars
  - `validation_status`: "pass" | "fail"
  - `token_id`: Proxmox API token ID (non-secret, included in evidence)
  - `secret_present`: boolean (true if secret non-empty and non-placeholder)
  - `file_hash`: SHA256 hash of rendered prod.tfvars
- **Relationships**:
  - Embedded in Evidence Pack under `reports/prod-tfvars/`
  - Referenced by PROD apply jobs in workflow

#### Entity: LAB Snapshot
- **Fields**:
  - `generated_at`: ISO 8601 timestamp
  - `environment`: "lab" | "prod"
  - `containers`: array of `{ vmid, hostname, status, ipv4 }`
  - `services`: array of `{ service, state_path, terraform_module }`
  - `latest_evidence`: object mapping `service → { run_id, path }`
  - `mount_checks`: array of `{ container_vmid, mount_path, mounted, read_only, source }`
  - `errors`: array of strings (non-fatal collection errors)
- **Validation rules**:
  - `containers` must include at least VMID and status
  - `services` must match entries in service-scope-allowlist.json
  - `mount_checks` required only for services declaring shared media mounts

#### Entity: Workflow Input (LAB Deploy)
- **Fields**:
  - `service`: choice (generated from allowlist keys)
  - `apply`: boolean (plan-only vs plan+apply)
  - `confirm_destructive`: string (required when plan detects destructive changes)
- **Validation rules**:
  - `service` must exist in allowlist
  - `confirm_destructive` must equal "apply-lab-destructive" when destructive plan detected

#### Entity: Workflow Input (Promote)
- **Fields**:
  - `service`: choice (generated from allowlist keys)
  - `confirm_destructive_lab`: string (required when LAB plan destructive)
  - `confirm_destructive_prod`: string (required when PROD plan destructive)
  - `hotfix_override`: boolean (required when running from main branch)
- **Validation rules**:
  - Hotfix override requires explicit boolean confirmation
  - Destructive confirmations must match expected strings per environment

### D2: API Contracts (`contracts/`)

#### Workflow Schema: LAB Deploy

File: `contracts/workflow-lab-deploy.schema.json`

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "title": "LXC Deploy (LAB) Workflow Inputs",
  "properties": {
    "service": {
      "type": "string",
      "enum": ["adguard", "homeassistant", "immich", "jellyfin", "monitoring", "reverse_proxy"],
      "description": "Service to deploy (from service-scope-allowlist.json)"
    },
    "apply": {
      "type": "boolean",
      "description": "Run plan+apply (true) or plan-only (false)"
    },
    "confirm_destructive": {
      "type": "string",
      "enum": ["", "apply-lab-destructive"],
      "description": "Required confirmation when plan detects destructive changes"
    }
  },
  "required": ["service", "apply"]
}
```

#### Workflow Schema: Promote

File: `contracts/workflow-promote.schema.json`

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "title": "LXC Promote (LAB → PROD) Workflow Inputs",
  "properties": {
    "service": {
      "type": "string",
      "enum": ["adguard", "homeassistant", "immich", "jellyfin", "monitoring", "reverse_proxy"],
      "description": "Service to promote (from service-scope-allowlist.json)"
    },
    "confirm_destructive_lab": {
      "type": "string",
      "enum": ["", "apply-lab-destructive"],
      "description": "Required when LAB plan is destructive"
    },
    "confirm_destructive_prod": {
      "type": "string",
      "enum": ["", "deploy-prod-destructive"],
      "description": "Required when PROD plan is destructive"
    },
    "hotfix_override": {
      "type": "boolean",
      "description": "Required confirmation when running from main branch"
    }
  },
  "required": ["service"]
}
```

#### Evidence Schema: tfvars Proof

File: `contracts/evidence-tfvars-proof.schema.json`

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "title": "PROD tfvars Provisioning Proof",
  "properties": {
    "timestamp": {
      "type": "string",
      "format": "date-time",
      "description": "When prod.tfvars was provisioned"
    },
    "template_source": {
      "type": "string",
      "description": "Path to template file used for rendering"
    },
    "rendered_path": {
      "type": "string",
      "description": "Absolute path to rendered prod.tfvars"
    },
    "validation_status": {
      "type": "string",
      "enum": ["pass", "fail"],
      "description": "Result of validation checks"
    },
    "token_id": {
      "type": "string",
      "pattern": "^terraform@pve!terraform-token$",
      "description": "Proxmox API token ID (non-secret)"
    },
    "secret_present": {
      "type": "boolean",
      "description": "True if secret is non-empty and non-placeholder"
    },
    "file_hash": {
      "type": "string",
      "pattern": "^[a-f0-9]{64}$",
      "description": "SHA256 hash of rendered prod.tfvars"
    },
    "validation_errors": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Validation errors if validation_status is fail"
    }
  },
  "required": ["timestamp", "validation_status", "token_id", "secret_present", "file_hash"]
}
```

#### Evidence Schema: LAB Snapshot

File: `contracts/evidence-lab-snapshot.schema.json`

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "title": "LAB Inventory Snapshot",
  "properties": {
    "generated_at": {
      "type": "string",
      "format": "date-time",
      "description": "Snapshot generation timestamp"
    },
    "environment": {
      "type": "string",
      "enum": ["lab", "prod"],
      "description": "Target environment for snapshot"
    },
    "containers": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "vmid": { "type": "integer", "description": "Proxmox container ID" },
          "hostname": { "type": "string", "description": "Container hostname" },
          "status": { "type": "string", "enum": ["running", "stopped"], "description": "Container status" },
          "ipv4": { "type": "string", "description": "Primary IPv4 address" }
        },
        "required": ["vmid", "hostname", "status"]
      }
    },
    "services": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "service": { "type": "string", "description": "Service slug" },
          "state_path": { "type": "string", "description": "Terraform state directory" },
          "terraform_module": { "type": "string", "description": "Terraform module name" }
        },
        "required": ["service", "state_path"]
      }
    },
    "latest_evidence": {
      "type": "object",
      "additionalProperties": {
        "type": "object",
        "properties": {
          "run_id": { "type": "string", "description": "Latest evidence run ID" },
          "path": { "type": "string", "description": "Evidence pack path" }
        }
      },
      "description": "Mapping of service to latest evidence metadata"
    },
    "mount_checks": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "container_vmid": { "type": "integer" },
          "mount_path": { "type": "string" },
          "mounted": { "type": "boolean" },
          "read_only": { "type": "boolean" },
          "source": { "type": "string" }
        },
        "required": ["container_vmid", "mount_path", "mounted"]
      }
    },
    "errors": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Non-fatal errors during snapshot collection"
    }
  },
  "required": ["generated_at", "environment", "containers", "services"]
}
```

### D3: Quickstart Documentation (`quickstart.md`)

Create `specs/024-pipeline-promotion-ux/quickstart.md` with operator documentation:

**Sections**:
1. **Overview**: Summary of LAB deploy vs Promote workflows
2. **Prerequisites**: GitHub permissions, Proxmox access, secrets configuration
3. **LAB Deploy Workflow**: How to run plan-only and plan+apply for LAB
4. **Promote Workflow**: How to promote LAB → PROD with approval
5. **Hotfix Path**: When and how to use hotfix override on main
6. **Destructive Changes**: Understanding destructive confirmations
7. **LAB Snapshot**: How to download and interpret snapshot artifacts
8. **Troubleshooting**: Common issues and remediation steps

### D4: Agent Context Update

After generating contracts and documentation, run:

```bash
.specify/scripts/bash/update-agent-context.sh copilot
```

This will:
- Detect that we're working with GitHub Copilot
- Update `.github/copilot-context.md` with new technology/patterns from this plan
- Preserve any manual additions between marker comments

---

## Phase 2: Task Generation Preparation

**This phase is executed by `/speckit.tasks` command (NOT by `/speckit.plan`).**

The plan stops here. Phase 2 guidance for task generation:

### Task Breakdown Strategy

When generating `tasks.md`, organize tasks into these categories:

#### Category 1: Workflow Splitting
- **T001**: Create `lxc-deploy-lab.yml` workflow with bounded inputs (service choice, apply boolean)
- **T002**: Create `lxc-promote.yml` workflow with LAB→PROD job sequence and approval gate
- **T003**: Add hotfix override logic to promote workflow for main branch runs
- **T004**: Deprecate or maintain existing `lxc-deploy.yml` for backward compatibility

#### Category 2: tfvars Provisioning
- **T005**: Create `scripts/lab/lib/tfvars.sh` library with provisioning functions
- **T006**: Implement tfvars rendering from template + GitHub Secrets
- **T007**: Implement tfvars validation rules (token ID, secret presence checks)
- **T008**: Generate redacted tfvars proof for evidence pack (JSON format)

#### Category 3: LAB Snapshot
- **T009**: Create `scripts/lab/lib/snapshot.sh` library with snapshot generation
- **T010**: Implement container state collection via `pct` commands
- **T011**: Implement service evidence pointer collection
- **T012**: Implement mount validation checks for shared media
- **T013**: Upload LAB snapshot as GitHub artifact

#### Category 4: Evidence Integration
- **T014**: Extend `scripts/lab/profiles.d/service-deploy.json` with new evidence fields
- **T015**: Update `scripts/lab/verify_evidence.py` to validate tfvars proof schema
- **T016**: Update `scripts/lab/verify_evidence.py` to validate LAB snapshot schema
- **T017**: Create evidence fixtures for new fields in `fixtures/evidence-packs/valid/`

#### Category 5: Documentation & Testing
- **T018**: Update `docs/` with operator runbook for new workflows
- **T019**: Test LAB deploy workflow with plan-only and apply modes
- **T020**: Test promote workflow with approval gate and destructive confirmations
- **T021**: Test hotfix override path on main branch
- **T022**: Test tfvars provisioning and validation in PROD runs
- **T023**: Verify LAB snapshot format and artifact upload

### Testing Strategy

Each task should include acceptance criteria that can be verified:
- Workflow input validation (invalid service rejected)
- Job sequencing (PROD blocked until LAB completes)
- Approval gate integration (manual approval required)
- Evidence verification (offline validation passes with new fields)
- Snapshot artifact availability (downloadable from GitHub Actions UI)

### Rollout Plan

1. Develop and test new workflows on feature branch
2. Keep existing `lxc-deploy.yml` active during transition
3. Document migration path for operators
4. Run parallel validation (old vs new workflow) for one service
5. Deprecate old workflow once new workflows proven

---

## Phase 1 Re-evaluation of Constitution

After completing Phase 1 design:

### Constitution Check (Post-Design)

**I. Spec-Driven Workflow** ✅
- All design artifacts reference spec requirements
- Contracts codify spec entities and validation rules

**II. Secrets Policy** ✅
- tfvars provisioning design explicitly avoids committing secrets
- Evidence proof redacts secret values while proving validation occurred
- Hash-based verification ensures integrity without exposing secrets

**III. Separation of Concerns** ✅
- No Terraform module changes
- No Ansible role changes
- Changes isolated to CI/CD orchestration and evidence collection

**GATE RESULT**: ✅ **PASS** - Design phase complete and constitution-compliant.

---

## Summary

This implementation plan provides a complete roadmap for the Pipeline Promotion UX feature:

1. **Phase 0 (Research)**: 8 research tasks covering workflow patterns, tfvars provisioning, snapshot design, and evidence extension
2. **Phase 1 (Design)**: Data model with 5 entities, 4 contract schemas, quickstart documentation, and agent context update
3. **Phase 2 (Task Generation)**: Guidance for 23 implementation tasks across 5 categories

**Branch**: `024-pipeline-promotion-ux`  
**Plan Location**: `/home/runner/work/homelab-proxmox/homelab-proxmox/specs/024-pipeline-promotion-ux/plan.md`

**Next Steps**:
1. Execute Phase 0 research by generating `research.md`
2. Execute Phase 1 design by generating `data-model.md`, `contracts/`, and `quickstart.md`
3. Run agent context update script
4. Use `/speckit.tasks` command to generate `tasks.md` with detailed implementation tasks
