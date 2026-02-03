# Implementation Plan: Separate LAB + PROD Promotion Pipeline (Spec 026)

**Branch**: `026-separate-prod-apply` | **Date**: 2026-01-12 | **Spec**: specs/026-separate-prod-apply/spec.md
**Input**: Feature specification from `/specs/026-separate-prod-apply/spec.md`

## Summary

Implement a safer promotion UX by splitting LAB-only promotion from PROD promotion, while enforcing strict SHA alignment across LAB deploy, confidence suite, and PROD plan/apply evidence.

Operator UX improvements for promotion safety:

- PROD promotion accepts an explicit `ref`, checks it out, and treats the checked-out SHA as the source of truth.
- The run summary includes a bounded list of recent commits (SHAs + subjects) for easier future `ref` selection.
- Evidence provenance (`provenance.json`) must record the checked-out SHA even if the remote machine cannot infer git metadata (e.g., because `.git` is excluded from rsync).

## Technical Context

**Language/Version**: Bash + Python 3 (repo scripts), YAML (GitHub Actions)
**Primary Dependencies**: GitHub Actions (workflow_dispatch), ssh/rsync, jq, Terraform CLI (on PVE), existing scripts under `scripts/lab/*`
**Storage**: Files on PVE host; evidence packs under `/var/lib/homelab-proxmox/artifacts/...`
**Testing**: Local workflow parse validation via `act` when available; offline evidence verification via `scripts/lab/ci-verify.sh`
**Target Platform**: Self-hosted GitHub Actions runner(s) + Proxmox VE host accessed via SSH
**Project Type**: Infrastructure repo (Terraform/Ansible/scripts/workflows)
**Performance Goals**: N/A (human-operated deployment pipeline)
**Constraints**: Do not print secrets; keep summaries bounded; keep Terraform state local on PVE; preserve separation of concerns (Terraform vs Ansible)
**Scale/Scope**: Single homelab deployment; a small allowlisted set of services

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Spec-Driven Workflow**: PASS — plan and implementation are driven from `specs/026-separate-prod-apply/` and its `tasks.md`.
- **Secrets Policy**: PASS — no secrets in logs/summaries; secrets are restricted to remote apply execution context.
- **Separation of Concerns**: PASS — changes are limited to workflow orchestration + existing scripts; no Terraform/Ansible responsibility changes.

## Project Structure

### Documentation (this feature)

```text
specs/026-separate-prod-apply/
├── plan.md              # This file
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
├── tasks.md
└── checklists/
    └── requirements.md
```

### Source Code (repository root)

```text
.github/
└── workflows/
    ├── lxc-promote-lab.yml
    ├── lxc-promote-prod.yml
    ├── lxc-apply-prod.yml
    └── lxc-promote.yml              # legacy combined workflow (guard / deprecated)

scripts/
└── lab/
    ├── pve-service-deploy           # generates service-deploy evidence packs
    ├── pve-lab
    ├── ci-verify.sh
    ├── render_failure_evidence.sh
    └── fetch_evidence_pack.sh

docs/
terraform/
ansible/
```

**Structure Decision**: This is an infra repository; implement changes in `.github/workflows/*` and `scripts/lab/*` only.

## Complexity Tracking

No constitution violations required for this feature.
