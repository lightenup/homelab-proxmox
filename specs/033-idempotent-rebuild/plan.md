# Implementation Plan: Idempotent Rebuild Orchestrator

**Branch**: `033-idempotent-rebuild` | **Date**: 2026-02-05 | **Spec**: [specs/033-idempotent-rebuild/spec.md](specs/033-idempotent-rebuild/spec.md)
**Input**: Feature specification from [specs/033-idempotent-rebuild/spec.md](specs/033-idempotent-rebuild/spec.md)

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

Create an idempotent rebuild system that runs from macOS, uses existing Taskfile + scripts/lab orchestration, and restores a fresh PVE 9 host to a working homelab system. The rebuild follows the Proxmox restore runbook, validates required mounts, restores IaC artifacts when available, captures evidence locally, and uses phase flags with a simple state machine for incremental runs.

## Technical Context

<!--
  ACTION REQUIRED: Replace the content in this section with the technical details
  for the project. The structure here is presented in advisory capacity to guide
  the iteration process.
-->

**Language/Version**: Shell scripts + Python (existing orchestration), Terraform (HCL), Ansible (YAML)
**Primary Dependencies**: Taskfile, scripts/lab, telmate/proxmox Terraform provider, Ansible
**Storage**: Local Terraform state on PVE; NAS-backed NFS mounts for backups and shared data
**Testing**: Plan-only runs, preflight summaries, mount validation, drift checks
**Target Platform**: macOS laptop driving Linux PVE host
**Project Type**: Infrastructure automation repository
**Performance Goals**: N/A (rebuild automation)
**Constraints**: Lab-first default, explicit prod confirmation, plan-only default, destructive confirmation, reuse existing workflows
**Scale/Scope**: PVE host + core LXCs from existing repo services

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Spec-Driven Workflow**: PASS (spec and plan located under specs/033-idempotent-rebuild/).
- **Secrets Policy**: PASS (no secrets committed; placeholders only).
- **Separation of Concerns**: PASS (Terraform for infra, Ansible for config).
- **Provider Strategy**: PASS (telmate/proxmox remains in scope).
- **State Management**: PASS (local state on PVE retained).
- **Storage Baseline**: PASS (host NFS mounts + bind mounts for Immich covered).

**Gate Result**: PASS

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

### Source Code (repository root)
<!--
  ACTION REQUIRED: Replace the placeholder tree below with the concrete layout
  for this feature. Delete unused options and expand the chosen structure with
  real paths (e.g., apps/admin, packages/something). The delivered plan must
  not include Option labels.
-->

```text
ansible/
├── inventories/
├── playbooks/
└── roles/

docs/
└── operations/

scripts/
└── lab/

terraform/
├── modules/
└── services/

specs/
└── 033-idempotent-rebuild/
```

**Structure Decision**: Reuse existing infra automation layout; new rebuild artifacts live under specs/033-idempotent-rebuild.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No constitution violations requiring justification.

## Phase 0: Research

**Output**: [specs/033-idempotent-rebuild/research.md](specs/033-idempotent-rebuild/research.md)

## Phase 1: Design & Contracts

**Data Model**: [specs/033-idempotent-rebuild/data-model.md](specs/033-idempotent-rebuild/data-model.md)
**Contracts**: [specs/033-idempotent-rebuild/contracts/README.md](specs/033-idempotent-rebuild/contracts/README.md)
**Quickstart**: [specs/033-idempotent-rebuild/quickstart.md](specs/033-idempotent-rebuild/quickstart.md)

## Phase 1: Agent Context Update

Run `.specify/scripts/bash/update-agent-context.sh copilot` after Phase 1 artifacts are generated.

## Constitution Check (Post-Design)

- **Spec-Driven Workflow**: PASS
- **Secrets Policy**: PASS
- **Separation of Concerns**: PASS
- **Provider Strategy**: PASS
- **State Management**: PASS
- **Storage Baseline**: PASS

**Gate Result**: PASS
