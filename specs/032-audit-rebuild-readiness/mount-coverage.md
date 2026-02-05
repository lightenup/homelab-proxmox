# Mount Coverage Matrix

**Feature**: 032-audit-rebuild-readiness
**Date**: 2026-02-05

| Mount ID | Host | Export | Mount Point | Consumer | Management Source | Status | Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| MNT-001 | PVE | 192.168.1.109:/volume1/homelab_immich | /mnt/nas/homelab_immich | Immich LXC (mp0) | ansible-proxmox-mounts (intended) | managed (runtime) / requires-review (automation) | runtime-inventory.md; proxmox_mounts role exists but not wired |
| MNT-002 | PVE | 192.168.1.109:/volume1/photo | /mnt/nas/photo | Immich LXC (mp1) | manual/unknown | requires-review | runtime-inventory.md |
| MNT-003 | LXC (jellyfin) | 192.168.1.109:/volume1/video | /media/video | Jellyfin service | ansible-shared-nfs | managed (runtime) | runtime-inventory.md |
| MNT-004 | LXC (immich) | 192.168.1.109:/volume1/homelab_immich | /mnt/immich | Immich service | bind mount (PVE mp0) | managed (runtime) | runtime-inventory.md |
| MNT-005 | LXC (immich) | 192.168.1.109:/volume1/photo | /mnt/immich-external/photo | Immich service | bind mount (PVE mp1) | managed (runtime) / requires-review (host mount) | runtime-inventory.md |
