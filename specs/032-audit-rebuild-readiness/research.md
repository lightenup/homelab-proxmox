# Research: Audit Rebuild Readiness & Configuration Hygiene

**Feature**: 032-audit-rebuild-readiness
**Date**: 2026-02-05

## Decision 1: Rebuild baseline source of truth

**Decision**: Use the Proxmox configuration restore runbook as the canonical baseline for a full rebuild from fresh PVE with NAS-backed configuration backups.

**Rationale**: The runbook already defines prerequisites, mount steps, decryption, restore ordering, and validation checks needed to rebuild from a clean PVE install.

**Evidence**:
- [docs/operations/backups-proxmox-config-restore.md](docs/operations/backups-proxmox-config-restore.md)

**Alternatives considered**:
- Create a new rebuild runbook specific to this audit (rejected: duplicates existing authoritative steps).
- Rely on ad-hoc operator knowledge (rejected: inconsistent and not auditable).

## Decision 2: Runtime inventory required for classification

**Decision**: Perform a full runtime inventory (PVE + guest checks) for all in-scope items to validate usage and classification.

**Rationale**: The requirement explicitly calls for full runtime inventory; existing roles and runbooks already validate mounts and container configuration, which can be extended into audit evidence.

**Evidence**:
- [docs/operations/backups-proxmox-config-restore.md](docs/operations/backups-proxmox-config-restore.md)
- [ansible/roles/shared_nfs_mount/tasks/main.yml](ansible/roles/shared_nfs_mount/tasks/main.yml)
- [ansible/roles/proxmox_host/tasks/main.yml](ansible/roles/proxmox_host/tasks/main.yml)

**Alternatives considered**:
- Repository-only classification (rejected: does not satisfy full runtime inventory requirement).
- Targeted runtime checks only (rejected: does not meet requirement).

## Decision 3: Storage/mount coverage taxonomy

**Decision**: Classify mounts into (a) host NFS mounts, (b) in-guest shared NFS mounts, and (c) Terraform-defined LXC mountpoints, and map each to its management source and policy compliance.

**Rationale**: The repo uses multiple mechanisms for mounts (host-level NFS, in-guest shared NFS, and Terraform mountpoint definitions). A clear taxonomy avoids misclassification and highlights gaps or policy conflicts.

**Evidence**:
- [ansible/roles/proxmox_mounts/tasks/main.yml](ansible/roles/proxmox_mounts/tasks/main.yml)
- [ansible/roles/shared_nfs_mount/tasks/main.yml](ansible/roles/shared_nfs_mount/tasks/main.yml)
- [ansible/roles/nfs_mount/tasks/main.yml](ansible/roles/nfs_mount/tasks/main.yml)
- [terraform/modules/lxc_service/main.tf](terraform/modules/lxc_service/main.tf)
- [terraform/environments/prod.tfvars.example](terraform/environments/prod.tfvars.example)
- [terraform/services/immich/main.tf](terraform/services/immich/main.tf)
- [ansible/roles/proxmox_host/tasks/main.yml](ansible/roles/proxmox_host/tasks/main.yml)

**Alternatives considered**:
- Standardize on a single mount mechanism as part of this audit (rejected: out of scope for audit-only work).

## Decision 4: Anti-pattern criteria for bind mounts

**Decision**: Treat Terraform host-path bind mounts as a policy violation **except** for documented baseline exceptions (Immich host bind mounts). Flag non-baseline host-path bind mounts as anti-patterns.

**Rationale**: The repository documents a policy to avoid host-path bind mounts for shared media while the storage baseline allows Immich host bind mounts. The audit must respect both.

**Evidence**:
- [specs/023-hardning-lxc-gated-deploy/spec.md](specs/023-hardning-lxc-gated-deploy/spec.md)

**Alternatives considered**:
- Allow host-path bind mounts if used by legacy services (rejected: conflicts with policy and least-privilege guidance).

## Decision 5: Operator entrypoints and removal validation

**Decision**: Use Taskfile tasks as the primary operator/rebuild entrypoints and rely on the existing removal validator to identify leftover references.

**Rationale**: Taskfile defines day-to-day and rebuild-critical flows; the removal validator already scans Terraform, inventories, and host vars for cleanup.

**Evidence**:
- [Taskfile.yml](Taskfile.yml)
- [scripts/lifecycle/remove_checks.py](scripts/lifecycle/remove_checks.py)

**Alternatives considered**:
- Introduce a new audit CLI (rejected: expands scope and duplicates existing entrypoints).
