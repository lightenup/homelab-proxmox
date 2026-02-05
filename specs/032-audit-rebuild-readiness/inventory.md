# Repository Inventory

**Feature**: 032-audit-rebuild-readiness
**Date**: 2026-02-05

## Inventory Table

| ID | Type | Path/Name | Purpose | Status | Evidence | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| INV-001 | process | Taskfile entrypoints | Operator/rebuild entrypoints | in-use | Taskfile.yml | Primary operator UX |
| INV-002 | code | terraform/services/immich | Immich LXC definition | in-use | terraform/services/immich + runtime pct list | CT 101 running |
| INV-003 | code | terraform/services/jellyfin | Jellyfin LXC definition | in-use | terraform/services/jellyfin + runtime pct list | CT 100 running |
| INV-004 | code | terraform/services/monitoring | Monitoring LXC definition | in-use | terraform/services/monitoring + runtime pct list | CT 103 running |
| INV-005 | code | terraform/services/homeassistant | Home Assistant LXC definition | in-use | terraform/services/homeassistant + runtime pct list | CT 104 running |
| INV-006 | code | terraform/services/reverse_proxy | Reverse proxy LXC definition | in-use | terraform/services/reverse_proxy + runtime pct list | CT 102 running |
| INV-007 | config | ansible/playbooks/host_proxmox.yml | PVE host configuration | in-use | ansible/playbooks/host_proxmox.yml | Roles: proxmox_host, tailscale_host |
| INV-008 | code | ansible/roles/proxmox_mounts | PVE host NFS mount role | requires-review | ansible/roles/proxmox_mounts + host_proxmox.yml | Role exists but not wired in host playbook |
| INV-009 | code | ansible/roles/proxmox_host | PVE baseline + Immich bind mount | in-use | ansible/roles/proxmox_host/tasks/main.yml + runtime inventory | Adds mp0 bind mount |
| INV-010 | code | ansible/roles/shared_nfs_mount | In-guest shared media NFS | in-use | ansible/playbooks/jellyfin.yml + role defaults | Used for Jellyfin shared media |
| INV-011 | script | scripts/lab/pve-service-deploy | LXC lifecycle orchestration + mountpoints | in-use | scripts/lab/pve-service-deploy + workflows | Sets mp0/mp1 for Immich |
| INV-012 | doc | docs/operations/backups-proxmox-config-restore.md | Rebuild baseline runbook | in-use | docs/operations/backups-proxmox-config-restore.md | Canonical rebuild baseline |

## Scope Summary

- Environments: lab + prod (as represented in repo)
- Nodes: PVE host (`pve`), LXCs (immich, jellyfin, proxy, monitoring, homeassistant), NAS (Synology)
- Runtime evidence: specs/032-audit-rebuild-readiness/runtime-inventory.md

