# Implementation Plan: LXC Lifecycle Workflow Consolidation

**Branch**: `031-lxc-lifecycle-pipeline` | **Date**: 2026-01-18 | **Spec**: [specs/031-lxc-lifecycle-pipeline/spec.md](specs/031-lxc-lifecycle-pipeline/spec.md)
**Input**: Feature specification from [specs/031-lxc-lifecycle-pipeline/spec.md](specs/031-lxc-lifecycle-pipeline/spec.md)

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

Formalize full LXC removal cleanup across Terraform, Ansible, inventory, proxy/DNS, healthchecks, and data locations, and consolidate add/change/delete into a single LXC lifecycle pipeline that always runs plan + apply, blocks destructive actions without protected confirmation, and captures evidence. Clarifications include explicit confirmation for data deletion, protected label/tag approval for destructive actions, and failure-on-verification for removal runs.

## Technical Context

<!--
  ACTION REQUIRED: Replace the content in this section with the technical details
  for the project. The structure here is presented in advisory capacity to guide
  the iteration process.
-->

**Language/Version**: Terraform (HCL), Ansible (YAML), Python 3.x, GitHub Actions (YAML), shell scripts
**Primary Dependencies**: telmate/proxmox Terraform provider, Ansible, Taskfile, GitHub Actions, Python automation scripts
**Storage**: Local Terraform state on PVE host; NFS mounts for service data (NAS)
**Testing**: `act` for workflow validation, terraform plan/apply, ansible playbook runs, healthcheck drift checks
**Target Platform**: Linux (PVE host) + GitHub Actions runners
**Project Type**: Infrastructure automation repository
**Performance Goals**: N/A (operational automation)
**Constraints**: No paid GitHub features for approvals; destructive actions require explicit confirmation; Terraform/Ansible separation; telmate/proxmox provider only; local state
**Scale/Scope**: Dozens of services/LXCs across lab/prod environments

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Spec-Driven Workflow**: PASS (spec and plan artifacts updated in `specs/031-lxc-lifecycle-pipeline/`).
- **Secrets Policy**: PASS (no secrets handled in plan artifacts).
- **Separation of Concerns**: PASS (Terraform manages infra; Ansible manages configuration).
- **Provider Strategy**: PASS (telmate/proxmox remains in scope).
- **CI/CD Destructive Barriers**: PASS (explicit confirmation required for replace/destroy).
- **State Management**: PASS (local state retained).

**Gate Result**: PASS

## Project Structure

### Documentation (this feature)

```text
specs/031-lxc-lifecycle-pipeline/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)
<!--
  ACTION REQUIRED: Replace the placeholder tree below with the concrete layout
  for this feature. Delete unused options and expand the chosen structure with
  real paths (e.g., apps/admin, packages/something). The delivered plan must
  not include Option labels.
-->

```text
.github/
└── workflows/

ansible/
├── group_vars/
├── host_vars/
├── inventories/
├── playbooks/
└── roles/

docs/
└── runbooks/

scripts/
└── [automation helpers]

terraform/
├── modules/
└── *.tf

specs/
└── 031-lxc-lifecycle-pipeline/
```

**Structure Decision**: Single infrastructure repository with Terraform, Ansible, GitHub Actions workflows, and supporting scripts/docs.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No constitution violations requiring justification.

## Phase 0: Research

**Output**: [specs/031-lxc-lifecycle-pipeline/research.md](specs/031-lxc-lifecycle-pipeline/research.md)

## Phase 1: Design & Contracts

**Data Model**: [specs/031-lxc-lifecycle-pipeline/data-model.md](specs/031-lxc-lifecycle-pipeline/data-model.md)
**Contracts**: [specs/031-lxc-lifecycle-pipeline/contracts/README.md](specs/031-lxc-lifecycle-pipeline/contracts/README.md)
**Quickstart**: [specs/031-lxc-lifecycle-pipeline/quickstart.md](specs/031-lxc-lifecycle-pipeline/quickstart.md)

## Phase 1: Agent Context Update

Run `.specify/scripts/bash/update-agent-context.sh copilot` after Phase 1 artifacts are generated.

## Constitution Check (Post-Design)

- **Spec-Driven Workflow**: PASS
- **Secrets Policy**: PASS
- **Separation of Concerns**: PASS
- **Provider Strategy**: PASS
- **CI/CD Destructive Barriers**: PASS
- **State Management**: PASS

**Gate Result**: PASS
