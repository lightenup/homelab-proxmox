# Quickstart: Idempotent Rebuild Orchestrator

**Feature**: 033-idempotent-rebuild
**Date**: 2026-02-05

## Goal

Run an idempotent rebuild from a macOS laptop to restore a PVE 9 host to a working homelab system with evidence capture.

## Prerequisites

### Laptop Setup (macOS)

1. **Mount NAS share**: Follow [docs/runbooks/laptop-nfs-setup.md](../../docs/runbooks/laptop-nfs-setup.md)
   ```bash
   ls /Volumes/nas/homelab_ci/infra_state/
   # Should show: lab/ static/
   ```

2. **Export Proxmox API credentials**:
   ```bash
   export PROXMOX_API_TOKEN_ID="root@pam!rebuild"
   export PROXMOX_API_TOKEN_SECRET="<from Bitwarden>"
   ```

3. **Enable NAS state** (for services phase):
   ```bash
   export USE_NAS_STATE=true
   ```

### PVE Host Requirements

- macOS laptop with SSH access to PVE and NAS.
- PVE 9 installed and reachable.
- Backup archive available on NAS.
- Age key available for restore (if encryption used).
- NAS mounts configured: `/mnt/nas/homelab_ci/infra_state/{lab,static}/`

## High-Level Flow

1. Run rebuild in plan-only mode (default).
2. Review preflight summary and confirm if apply is needed.
3. Execute apply with explicit confirmation string.
4. Verify mounts, LXCs, and services; collect evidence.

## Run the Rebuild

Plan-only (default):

- task rebuild:plan -- --environment lab --backup-dir /root/restore-YYYYMMDD

Apply (requires confirmation string):

- task rebuild:apply CONFIRM=rebuild-prod -- --environment prod --backup-dir /root/restore-YYYYMMDD

Evidence outputs:

- Local evidence path: [artifacts/rebuild-runs](artifacts/rebuild-runs) (run_id subdirectory)
- Preflight summary: [artifacts/rebuild-runs](artifacts/rebuild-runs) (run_id/reports/preflight-summary.txt)
- Phase summary: [artifacts/rebuild-runs](artifacts/rebuild-runs) (run_id/reports/rebuild-phase-summary.md)

## References

- [docs/operations/backups-proxmox-config-restore.md](docs/operations/backups-proxmox-config-restore.md)
- [Taskfile.yml](Taskfile.yml)
- [scripts/lab/pve-service-deploy](scripts/lab/pve-service-deploy)
- [specs/032-audit-rebuild-readiness/audit-report.md](specs/032-audit-rebuild-readiness/audit-report.md)
