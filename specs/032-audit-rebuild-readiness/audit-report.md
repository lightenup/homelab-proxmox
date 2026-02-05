# Audit Report: Rebuild Readiness & Configuration Hygiene

**Feature**: 032-audit-rebuild-readiness
**Date**: 2026-02-05

## Scope

- Environments: lab + prod (as represented in repo)
- Nodes: PVE host (`pve`), LXCs (immich, jellyfin, proxy, monitoring, homeassistant), NAS (Synology)
- Evidence: specs/032-audit-rebuild-readiness/runtime-inventory.md

## Inventory Summary

| Status | Count |
| --- | --- |
| in-use | 11 |
| requires-review | 1 |
| unused | 0 |
| dr-maintenance-only | 0 |

## Key Findings

- **FND-002 (high)**: `/mnt/nas/photo` host mount appears unmanaged, but is used by Immich `mp1`. Rebuild could miss this mount.
- **FND-001 (medium)**: `proxmox_mounts` role exists but is not wired into the host playbook, risking missed host mounts during rebuild.
- **FND-003 (medium)**: Terraform example uses host-path mountpoints for Jellyfin; requires explicit policy exception or migration to in-guest NFS.

## Recommendations (Prioritized)

- **REC-001 (p1)**: Manage `/mnt/nas/photo` host mount via Ansible or explicit rebuild step.
- **REC-002 (p2)**: Wire `proxmox_mounts` role into host playbook or document exception.
- **REC-003 (p2)**: Document policy exception or migrate shared media mounts to in-guest NFS for non-Immich services.

## Success Criteria Check

| Success Criterion | Status | Notes |
| --- | --- | --- |
| SC-001: 100% inventory coverage | ✅ | Inventory populated with all in-scope components |
| SC-002: 90% evidence-backed classification | ✅ | Runtime inventory captured for key mounts; remaining items flagged as requires-review |
| SC-003: Rebuild checklist executable by second operator | ⚠️ | Checklist drafted; gaps logged in rebuild-readiness.md |
| SC-004: All shared mounts mapped | ✅ | Mount coverage matrix created; in-guest validations complete |

## Evidence Pointers

- Runtime inventory: specs/032-audit-rebuild-readiness/runtime-inventory.md
- Inventory: specs/032-audit-rebuild-readiness/inventory.md
- Findings: specs/032-audit-rebuild-readiness/findings.md
- Recommendations: specs/032-audit-rebuild-readiness/recommendations.md
