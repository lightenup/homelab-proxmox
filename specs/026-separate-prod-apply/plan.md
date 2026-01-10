# Implementation Plan: Separate LAB + PROD Promotion Pipeline (Spec 026)

**Branch**: `026-separate-prod-apply` | **Date**: 2026-01-10 | **Spec**: specs/026-separate-prod-apply/spec.md
**Input**: Feature specification from `/specs/026-separate-prod-apply/spec.md`

## Summary

Introduce two explicit GitHub Actions workflows:

1. **LAB promote** (`.github/workflows/lxc-promote-lab.yml`): plan+apply for LAB only, never reaches PROD approval/apply.
2. **PROD promote** (`.github/workflows/lxc-promote-prod.yml`): a single pipeline that runs Apply(LAB) → confidence suite (best-effort even if LAB deploy fails) → Plan(PROD) → publish summaries → GitHub Environment approval → Apply(PROD from saved plan).

Key constraints captured in the spec:

- PROD promote accepts an explicit git `ref`, checks out that ref, and enforces strict SHA alignment across evidence.
- If LAB deploy or suite fails, the workflow still generates and publishes the PROD plan; PROD apply remains blocked unless approval is granted **and** an override checkbox is set.
- When override is set, destructive confirmation requirements are bypassed.

## Technical Context

**Language/Version**: Bash + Python 3 (repo scripts), YAML (GitHub Actions), Terraform (HCL), Ansible (YAML)  
**Primary Dependencies**: GitHub Actions (workflow_dispatch, environments), Terraform CLI, Ansible, Proxmox (PVE) host, existing repo scripts under `scripts/lab/*`  
**Storage**: Files on PVE host (Terraform state local on PVE; evidence packs under `/var/lib/homelab-proxmox/artifacts/...`)  
**Testing**: `act -l` / `act -n` workflow parsing (when available), existing CI verification scripts (`scripts/lab/ci-verify.sh`)  
**Target Platform**: GitHub Actions runner(s) + PVE host accessed via SSH  
**Project Type**: Infrastructure repo (Terraform/Ansible/scripts/workflows)  
**Performance Goals**: N/A (human-operated deploy pipeline)  
**Constraints**: No secrets in logs/summaries; keep state local on PVE; preserve Terraform/Ansible separation of concerns; bounded summaries  
**Scale/Scope**: Single homelab deployment; handful of allowlisted services

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Spec-Driven Workflow**: PASS — all behavioral changes are represented in specs/026 (spec + tasks + contracts) and will be implemented strictly from those tasks.
- **Secrets Policy**: PASS — workflows/summaries must not print secrets; only pass secrets to the SSH/apply step.
- **Separation of Concerns**: PASS — changes are limited to GitHub Actions/workflow orchestration and existing scripts; no Terraform/Ansible responsibility changes.

## Project Structure

### Documentation (this feature)

```text
specs/026-separate-prod-apply/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
.github/
└── workflows/
    ├── lxc-promote-lab.yml
    ├── lxc-promote-prod.yml
    └── lxc-promote.yml              # legacy combined workflow (to deprecate/remove)

scripts/
└── lab/
    ├── pve-service-deploy
    ├── pve-lab
    ├── ci-verify.sh
    ├── render_failure_evidence.sh
    └── fetch_evidence_pack.sh       # to add (shared)

terraform/
ansible/
docs/
```

**Structure Decision**: This is an infrastructure repository; implement changes in `.github/workflows/*` and `scripts/lab/*` only. No new application source tree is introduced.

## Complexity Tracking

No constitution violations required for this feature.
