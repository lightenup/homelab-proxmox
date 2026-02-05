# Data Model: Audit Rebuild Readiness & Configuration Hygiene

**Feature**: 032-audit-rebuild-readiness
**Date**: 2026-02-05

## Entities

### Inventory Item

Represents any repository component or operational process under review.

| Field | Type | Description |
| --- | --- | --- |
| id | string | Stable identifier (path or logical name) |
| type | enum | code, config, doc, script, process |
| path | string | Repository path (if applicable) |
| purpose | string | Intended purpose or responsibility |
| status | enum | in-use, unused, requires-review, dr-maintenance-only |
| evidence | list | Evidence references (runtime checks, docs, commands) |
| owner | string | Primary owner or domain (optional) |
| dependencies | list | Related items or prerequisites |

### Finding

Documented issue, gap, or anti-pattern discovered during the audit.

| Field | Type | Description |
| --- | --- | --- |
| id | string | Stable identifier |
| category | enum | unused, incomplete, anti-pattern, documentation, rebuild-gap |
| severity | enum | low, medium, high, critical |
| description | string | Summary of the issue |
| evidence | list | Evidence references |
| related_items | list | Inventory items impacted |
| remediation_priority | enum | p1, p2, p3 |

### Recommendation

Prioritized action to resolve a finding or reduce risk.

| Field | Type | Description |
| --- | --- | --- |
| id | string | Stable identifier |
| finding_id | string | Associated finding |
| priority | enum | p1, p2, p3 |
| criticality | enum | rebuild-dr, operational, security |
| effort | enum | low, medium, high |
| action | string | Recommended action |
| acceptance_criteria | string | Outcome to validate completion |

### Rebuild Step

Discrete step required to rebuild from fresh PVE + NAS backups.

| Field | Type | Description |
| --- | --- | --- |
| order | number | Sequence index |
| description | string | Step description |
| prerequisites | list | Required inputs or prior steps |
| references | list | Docs/commands supporting the step |
| validation | string | Validation or success signal |

### Storage Mount

Represents a shared mount used by LXCs.

| Field | Type | Description |
| --- | --- | --- |
| id | string | Stable identifier |
| host | string | Hostname or scope (PVE or LXC) |
| export | string | NFS export path |
| mount_point | string | Local mount point |
| consumer | string | LXC service or host usage |
| management_source | enum | ansible-proxmox-mounts, ansible-shared-nfs, terraform-mountpoint, manual |
| status | enum | managed, unmanaged, legacy |

### Environment Scope

Represents the nodes/environments included in the audit.

| Field | Type | Description |
| --- | --- | --- |
| nodes | list | Hostnames or nodes |
| environments | list | lab, prod, other |
| notes | string | Scope clarifications |
