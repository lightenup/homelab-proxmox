## Implementation Plan: Gated LXC Deploy (Least Privilege)

**Branch**: `022-lxc-gated-deploy` | **Date**: 2026-01-04 | **Spec**: specs/022-lxc-gated-deploy/spec.md
**Input**: Feature specification from specs/022-lxc-gated-deploy/spec.md

## Summary

Deliver a fully gated, least-privilege CI/CD flow for provisioning and configuring a new Proxmox LXC service (baseline example: Jellyfin) with:

- A non-destructive plan/preflight that reports create/update/no-op intent.
- Separate LAB vs PROD behavior (LAB can auto-apply; PROD requires environment approval + explicit confirmation input).
- Durable evidence bundles stored on the Proxmox host and verified offline.

Key architectural decision (from research): Terraform provisions the LXC (existence/sizing) and Ansible configures the service inside the LXC.

## Technical Context

**Language/Version**: Bash (5.x), Terraform (1.x), Ansible (2.x), Python (3.x), GitHub Actions (YAML)
**Primary Dependencies**: Terraform `telmate/proxmox` provider + existing `terraform/modules/lxc_service`, Ansible, `jq`, SSH/rsync, `act` (local CI simulation)
**Storage**: Local Terraform state on runner; filesystem evidence packs on PVE under `/var/lib/homelab-proxmox/artifacts/service-deploy-runs/<run_id>`
**Testing**: `act` runs for workflows; offline evidence verification; CI posture validation scripts
**Target Platform**: Self-hosted GitHub Actions runner (Linux) + Proxmox host accessed via `ci@pve` (no root SSH)
**Project Type**: Infrastructure-as-Code repo (Terraform + Ansible + supporting scripts)
**Performance Goals**: Plan/preflight <2 minutes; LAB apply+verify <15 minutes
**Constraints**: No committed secrets; Terraform/Ansible separation; least-privilege SSH/sudo; offline-verifiable evidence for every run
**Scale/Scope**: Single-service baseline example (Jellyfin) with safe parameterization for future services

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Spec-driven workflow**: Pass for planning. No implementation work may begin until `specs/022-lxc-gated-deploy/tasks.md` exists and is approved.
- **Secrets policy**: Must not introduce committed secrets; all workflows/scripts must use secrets from GitHub Secrets / environment variables.
- **Separation of concerns**: Terraform provisions LXC existence/sizing; Ansible configures inside LXC.
- **Provider strategy**: Continue using `telmate/proxmox` (no provider migration).
- **State management**: Keep Terraform state local; do not introduce remote state.

## Project Structure

### Documentation (this feature)

```text
specs/022-lxc-gated-deploy/
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
  workflows/

terraform/
  modules/
    lxc_service/

ansible/
  inventories/
  playbooks/
  roles/

scripts/
  lab/
    lib/

docs/
specs/
```

**Structure Decision**: Extend the existing IaC repo structure with a new workflow + supporting Terraform/Ansible changes and reuse the existing evidence/verification libraries.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| [e.g., 4th project] | [current need] | [why 3 projects insufficient] |
| [e.g., Repository pattern] | [specific problem] | [why direct DB access insufficient] |
