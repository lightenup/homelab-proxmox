# Research: Gated LXC Deploy (Least Privilege)

**Spec**: specs/022-lxc-gated-deploy/spec.md
**Date**: 2026-01-04

## Decisions

### Decision: Use Terraform for LXC existence (not `pct` scripting)
- **Chosen**: Terraform `telmate/proxmox` + existing module `terraform/modules/lxc_service`.
- **Rationale**: Matches repo constitution (Terraform owns existence/sizing) and existing root module already provisions LXCs via this module.
- **Alternatives considered**:
  - Direct `pct create` / `pvesh` in scripts: rejected (mixes responsibilities; harder to plan safely).

### Decision: Use Ansible for configuration inside the LXC
- **Chosen**: Ansible roles/playbooks to install/configure the service (baseline example: Jellyfin) after Terraform creates the container.
- **Rationale**: Matches repo constitution (Ansible owns inside configuration) and current repo layout.
- **Alternatives considered**:
  - Bake everything into the LXC template: rejected (less transparent, harder to iterate and verify).

### Decision: “Plan/Preflight” is a real no-change run
- **Chosen**: Run `terraform plan` (and optionally Ansible check-mode/dry-run where feasible) and publish deterministic artifacts.
- **Rationale**: Produces reviewable intent; supports create/update/no-op without mutating Proxmox.
- **Alternatives considered**:
  - Custom diff logic against Proxmox API: rejected (complex, duplicates Terraform semantics).

### Decision: PROD safety is enforced by GitHub Environments + explicit confirmation input
- **Chosen**: Use a GitHub Environment for PROD (required reviewers) + a `workflow_dispatch` input like `confirm: "deploy"`.
- **Rationale**: Two independent gates (human approval + explicit intent confirmation) reduce accidental prod applies.
- **Alternatives considered**:
  - Only environment approval: rejected (still easy to misclick without explicit intent string).

### Decision: Evidence storage uses `ARTIFACT_ROOT` with a dedicated runs directory
- **Chosen**: Store evidence under `/var/lib/homelab-proxmox/artifacts` (existing root), with `ARTIFACT_RUNS_DIR` set to a feature-specific namespace (e.g., `service-deploy-runs`).
- **Rationale**: Keeps evidence durable and outside repo rsync; avoids mixing service deploy evidence with lab harness evidence under `lab-runs`.
- **Alternatives considered**:
  - Reuse `lab-runs` for everything: rejected (semantic mismatch; makes verification/reporting harder).

## Open Items (resolved enough for planning)

- **Service baseline**: Jellyfin (per spec) for first implementation slice (baseline example).
- **Environment split**: LAB vs PROD controlled by workflow inputs and GitHub Environments.
- **Least privilege**:
  - CI connects as `ci@pve` (no root SSH).
  - Proxmox actions use narrowly scoped `sudo` (existing pattern in `scripts/lab`).

## Notes / Constraints

- This feature is planning-only until `tasks.md` is produced and approved (constitution gate).
