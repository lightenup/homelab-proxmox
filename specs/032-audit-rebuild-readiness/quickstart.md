# Quickstart: Audit Rebuild Readiness & Configuration Hygiene

**Feature**: 032-audit-rebuild-readiness
**Date**: 2026-02-05

## Goal

Produce an audit report that inventories all in-scope items, validates usage via full runtime inventory, and identifies rebuild gaps, unused items, and anti-patterns.

## Prerequisites

- Access to the repository.
- Access to the Proxmox host (PVE) and NAS for runtime inventory.
- Restore runbook available for baseline rebuild steps.

## Steps (High Level)

1. Review the rebuild baseline runbook and extract required rebuild steps.
2. Inventory repository components (Terraform, Ansible, scripts, docs, Taskfile entrypoints).
3. Run full runtime inventory on PVE and relevant LXCs (containers, storage, mounts, service state).
4. Map shared mounts to their management source and policy compliance.
5. Classify items: in-use, unused, requires-review, or dr-maintenance-only.
6. Document findings and prioritize remediation by rebuild/DR criticality.

## References

- [docs/operations/backups-proxmox-config-restore.md](docs/operations/backups-proxmox-config-restore.md)
- [Taskfile.yml](Taskfile.yml)
- [ansible/roles/proxmox_mounts/tasks/main.yml](ansible/roles/proxmox_mounts/tasks/main.yml)
- [ansible/roles/shared_nfs_mount/tasks/main.yml](ansible/roles/shared_nfs_mount/tasks/main.yml)
- [terraform/modules/lxc_service/main.tf](terraform/modules/lxc_service/main.tf)
- [specs/032-audit-rebuild-readiness/audit-report.md](specs/032-audit-rebuild-readiness/audit-report.md)
- [specs/032-audit-rebuild-readiness/runtime-inventory.md](specs/032-audit-rebuild-readiness/runtime-inventory.md)
- [specs/032-audit-rebuild-readiness/inventory.md](specs/032-audit-rebuild-readiness/inventory.md)
- [specs/032-audit-rebuild-readiness/findings.md](specs/032-audit-rebuild-readiness/findings.md)
- [specs/032-audit-rebuild-readiness/recommendations.md](specs/032-audit-rebuild-readiness/recommendations.md)
