# Runbooks

Step-by-step procedures for operational tasks. For system design see [architecture](../architecture.md); for day-to-day ops reference see [operations](../operations/).

## Disaster Recovery
- [Disaster Recovery Drill](disaster-recovery-drill.md) -- Immich backup recovery from Hetzner S3
- [DR Drill Playbook](dr-drill-playbook.md) -- PVE/NAS/DSM drill procedure
- [DR Drill Report Template](dr-drill-report-template.md) -- post-drill report format

## Rebuild & Restore
- [Rebuild Orchestrator Restore](rebuild-orchestrator-restore.md) -- full bare-metal to operational restore
- [Proxmox API Token Setup](proxmox-api-token-setup.md) -- create tokens for rebuild orchestrator
- [Laptop NFS Setup](laptop-nfs-setup.md) -- macOS NFS mount for Terraform state access

## Patching & Upgrades
- [Monthly Patching](monthly-patching.md) -- security-only monthly patch cycle
- [Manual Upgrades](manual-upgrades.md) -- full system upgrade (features + bugfixes)

## Remote Access
- [Tailscale Setup](tailscale-setup.md) -- subnet router configuration and troubleshooting
- [Tailscale ACL](tailscale-acl.md) -- access control policy management

## Service-Specific
- [Immich Backup/Restore](immich-backup-restore.md) -- database backup and recovery drill
- [Immich Maintenance](immich-maintenance.md) -- upgrades, troubleshooting, health checks
- [Reverse Proxy](reverse-proxy.md) -- Caddy reverse proxy configuration
