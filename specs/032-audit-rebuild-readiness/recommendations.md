# Recommendations

**Feature**: 032-audit-rebuild-readiness
**Date**: 2026-02-05

| ID | Finding | Priority | Criticality | Effort | Action | Acceptance Criteria |
| --- | --- | --- | --- | --- | --- | --- |
| REC-001 | FND-002 | p1 | rebuild-dr | medium | Add managed PVE host mount for `/mnt/nas/photo` (role/playbook or documented rebuild step) | Rebuild checklist includes mount; runtime inventory confirms mount after rebuild |
| REC-002 | FND-001 | p2 | operational | low | Wire `proxmox_mounts` into host playbook or document explicit reason for exclusion | Host playbook includes mount role or documented exception in audit report |
| REC-003 | FND-003 | p2 | operational | low | Document policy exception or migrate shared media mounts to in-guest NFS for non-Immich services | Mount taxonomy and findings reflect approved approach |
