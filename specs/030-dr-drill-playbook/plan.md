# Implementation Plan: DR Drill Playbook

**Branch**: `030-dr-drill-playbook` | **Date**: 2026-01-17 | **Spec**: [specs/030-dr-drill-playbook/spec.md](specs/030-dr-drill-playbook/spec.md)
**Input**: Feature specification from `/specs/030-dr-drill-playbook/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

Create a dedicated DR drill runbook in docs/runbooks that guides operators through downloading the full encrypted Synology Hyper Backup from Hetzner S3 to the dedicated NAS share mounted on PVE, validating decryption in DSM Hyper Backup Explorer, and recording outcomes. The plan emphasizes readiness checks (free space >= 2× rclone size estimate), preservation of the Pool directory structure, and strict secrets handling.

## Technical Context

<!--
  ACTION REQUIRED: Replace the content in this section with the technical details
  for the project. The structure here is presented in advisory capacity to guide
  the iteration process.
-->

**Language/Version**: Markdown for runbook + Bash (POSIX shell) for existing scripts  
**Primary Dependencies**: rclone, DSM Hyper Backup Explorer, Hetzner S3 credentials, NFS mount tooling  
**Storage**: Synology NAS share `/volume1/homelab_dr_test` mounted at `/mnt/nas/homelab_dr_test`  
**Testing**: Manual DR drill execution; `scripts/dr/verify_restore.sh` validation  
**Target Platform**: PVE host (Debian), Synology DSM 7.x  
**Project Type**: Documentation + scripts  
**Performance Goals**: N/A (operator-run drill)  
**Constraints**: No secrets committed; preserve Pool directory structure; avoid modifying production data  
**Scale/Scope**: Multi-GB/TB backup datasets; single-run operator workflow

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- Spec-driven workflow: Pass (plan aligns to spec).
- Secrets policy: Pass (no secrets stored in docs; placeholders only).
- Separation of concerns: Pass (no Terraform/Ansible boundary changes).
- Provider strategy: Pass (no provider changes).
- State management/storage constraints: Pass (uses dedicated DR share; no state changes).

Post-Phase 1 design re-check: Pass.

## Project Structure

### Documentation (this feature)

```text
specs/030-dr-drill-playbook/
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
docs/
└── runbooks/
  └── dr-drill-playbook.md

scripts/
└── dr/
  ├── README.md
  ├── hetzner_list.sh
  ├── hetzner_download.sh
  └── verify_restore.sh

Taskfile.yml
```

**Structure Decision**: Documentation lives in docs/runbooks with existing DR helper scripts under scripts/dr, wired via Taskfile.yml tasks.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No constitution violations.
