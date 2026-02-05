# Implementation Plan: Audit Rebuild Readiness & Configuration Hygiene

**Branch**: `032-audit-rebuild-readiness` | **Date**: 2026-02-05 | **Spec**: [specs/032-audit-rebuild-readiness/spec.md](specs/032-audit-rebuild-readiness/spec.md)
**Input**: Feature specification from [specs/032-audit-rebuild-readiness/spec.md](specs/032-audit-rebuild-readiness/spec.md)

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

Deliver an audit that inventories all in-scope repo components, validates usage via full runtime inventory, and identifies unused items, rebuild gaps, and anti-patterns. The rebuild baseline is a fresh PVE install restored from NAS backups, using the existing Proxmox restore runbook and runtime validation of mounts and LXC configuration.

## Technical Context

<!--
  ACTION REQUIRED: Replace the content in this section with the technical details
  for the project. The structure here is presented in advisory capacity to guide
  the iteration process.
-->

**Language/Version**: Terraform (HCL), Ansible (YAML), Python 3.x, shell scripts
**Primary Dependencies**: telmate/proxmox Terraform provider, Ansible, Taskfile, Python orchestration scripts
**Storage**: Local Terraform state on PVE host; NAS-backed NFS mounts for backups and shared data
**Testing**: Terraform validate/plan, Ansible playbook runs, runtime inventory checks, `act` for workflow validation (when needed)
**Target Platform**: Linux (PVE host + Debian LXCs)
**Project Type**: Infrastructure automation repository
**Performance Goals**: N/A (audit and operational automation)
**Constraints**: Spec-driven workflow, secrets policy, Terraform/Ansible separation, telmate/proxmox provider only, local state on PVE
**Scale/Scope**: All environments/nodes represented in the repository

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Spec-Driven Workflow**: PASS (plan and artifacts in specs/032-audit-rebuild-readiness/).
- **Secrets Policy**: PASS (audit artifacts contain no secrets; placeholders only).
- **Separation of Concerns**: PASS (audit respects Terraform vs Ansible responsibilities).
- **Provider Strategy**: PASS (telmate/proxmox usage unchanged).
- **Networking**: PASS (no changes to IP or gateway policy).
- **Access Control**: PASS (no changes to SSH or admin access flow).
- **State Management**: PASS (local state on PVE remains; audit only).
- **Storage**: PASS (NFS usage documented; no Ceph changes).
- **Services Model**: PASS (one LXC per service model unchanged).
- **CI/CD Expectations**: PASS (no pipeline changes).
- **Local Workflow Testing**: PASS (no workflow changes requiring act runs).
- **Repo Layout**: PASS (existing structure retained).

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
.github/
└── workflows/

ansible/
├── group_vars/
├── host_vars/
├── inventories/
├── playbooks/
└── roles/

docs/
├── operations/
├── runbooks/
└── architecture/

python/
├── src/
└── tests/

scripts/
├── dr/
├── lifecycle/
├── lab/
└── healthcheck/

terraform/
├── modules/
├── services/
└── environments/

specs/
└── 032-audit-rebuild-readiness/
```

**Structure Decision**: Single infrastructure repository with Terraform, Ansible, scripts, and documentation; audit artifacts live under specs/032-audit-rebuild-readiness.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No constitution violations requiring justification.

## Phase 0: Research

**Output**: [specs/032-audit-rebuild-readiness/research.md](specs/032-audit-rebuild-readiness/research.md)

## Phase 1: Design & Contracts

**Data Model**: [specs/032-audit-rebuild-readiness/data-model.md](specs/032-audit-rebuild-readiness/data-model.md)
**Contracts**: [specs/032-audit-rebuild-readiness/contracts/README.md](specs/032-audit-rebuild-readiness/contracts/README.md)
**Quickstart**: [specs/032-audit-rebuild-readiness/quickstart.md](specs/032-audit-rebuild-readiness/quickstart.md)

## Phase 1: Agent Context Update

Run `.specify/scripts/bash/update-agent-context.sh copilot` after Phase 1 artifacts are generated.

## Constitution Check (Post-Design)

- **Spec-Driven Workflow**: PASS
- **Secrets Policy**: PASS
- **Separation of Concerns**: PASS
- **Provider Strategy**: PASS
- **Networking**: PASS
- **Access Control**: PASS
- **State Management**: PASS
- **Storage**: PASS
- **Services Model**: PASS
- **CI/CD Expectations**: PASS
- **Local Workflow Testing**: PASS
- **Repo Layout**: PASS

**Gate Result**: PASS
