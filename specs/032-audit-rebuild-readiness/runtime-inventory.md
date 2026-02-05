# Runtime Inventory (PVE/LXC/NAS)

**Feature**: 032-audit-rebuild-readiness
**Date**: 2026-02-05
**Operator**: ci (via `ssh pve`)

## Checklist

- [x] PVE host NFS mounts captured
- [x] PVE LXC list captured
- [x] PVE LXC mountpoints (mpX) captured
- [x] LXC in-guest mount visibility validated (Immich)
- [x] LXC in-guest mount visibility validated (Jellyfin)
- [x] LXC in-guest mount visibility validated (Monitoring)
- [x] LXC in-guest mount visibility validated (Home Assistant)
- [x] LXC in-guest mount visibility validated (Reverse Proxy)

## Evidence: PVE Host Mounts

Command:
```
findmnt -n --target /mnt/nas/homelab_immich
```
Result:
```
/mnt/nas/homelab_immich 192.168.1.109:/volume1/homelab_immich nfs rw,relatime,vers=3,rsize=131072,wsize=131072,namlen=255,hard,fatal_neterrors=none,proto=tcp,timeo=600,retrans=2,sec=sys,mountaddr=192.168.1.109,mountvers=3,mountport=892,mountproto=udp,local_lock=none,addr=192.168.1.109
```

Command:
```
findmnt -n --target /mnt/nas/photo
```
Result:
```
/mnt/nas/photo 192.168.1.109:/volume1/photo nfs ro,relatime,vers=3,rsize=131072,wsize=131072,namlen=255,hard,fatal_neterrors=none,proto=tcp,timeo=600,retrans=2,sec=sys,mountaddr=192.168.1.109,mountvers=3,mountport=892,mountproto=udp,local_lock=none,addr=192.168.1.109
```

## Evidence: PVE LXC List

Command:
```
pct list
```
Result:
```
VMID       Status     Lock         Name
100        running                 jellyfin
101        running                 immich
102        running                 proxy
103        running                 monitoring
104        running                 homeassistant
```

## Evidence: Immich LXC Mountpoints

Command:
```
pct config 101 | awk '/^mp[0-9]+:/ {print}'
```
Result:
```
mp0: /mnt/nas/homelab_immich,mp=/mnt/immich
mp1: /mnt/nas/photo,mp=/mnt/immich-external/photo,ro=1
```

## Evidence: Immich In-Guest Mount Visibility

Command:
```
pct exec 101 -- bash -lc "mount | grep -E '/mnt/immich|/mnt/immich-external/photo'"
```
Result:
```
192.168.1.109:/volume1/homelab_immich on /mnt/immich type nfs (rw,relatime,vers=3,rsize=131072,wsize=131072,namlen=255,hard,fatal_neterrors=none,proto=tcp,timeo=600,retrans=2,sec=sys,mountaddr=192.168.1.109,mountvers=3,mountport=892,mountproto=udp,local_lock=none,addr=192.168.1.109)
192.168.1.109:/volume1/photo on /mnt/immich-external/photo type nfs (ro,relatime,vers=3,rsize=131072,wsize=131072,namlen=255,hard,fatal_neterrors=none,proto=tcp,timeo=600,retrans=2,sec=sys,mountaddr=192.168.1.109,mountvers=3,mountport=892,mountproto=udp,local_lock=none,addr=192.168.1.109)
```

Write test (Immich):
```
pct exec 101 -- bash -lc "touch /mnt/immich/.bind_mount_write_test && rm /mnt/immich/.bind_mount_write_test"
```
Result: succeeded (no output, exit 0)

## Evidence: Jellyfin In-Guest Mount Visibility

Command:
```
pct exec 100 -- bash -lc "mount | grep -F /media/video"
```
Result:
```
192.168.1.109:/volume1/video on /media/video type nfs (ro,relatime,vers=3,rsize=131072,wsize=131072,namlen=255,hard,fatal_neterrors=none,proto=tcp,timeo=600,retrans=2,sec=sys,mountaddr=192.168.1.109,mountvers=3,mountport=892,mountproto=udp,local_lock=none,addr=192.168.1.109)
```

## Evidence: Monitoring In-Guest Mount Visibility

Command:
```
pct exec 103 -- bash -lc "mount | grep -E /mnt\\|/media || true"
```
Result:
```
(no output)
```

## Evidence: Reverse Proxy In-Guest Mount Visibility

Command:
```
pct exec 102 -- bash -lc "mount | grep -E /mnt\\|/media || true"
```
Result:
```
(no output)
```

## Evidence: Home Assistant In-Guest Mount Visibility

Command:
```
pct exec 104 -- bash -lc "mount | grep -E /mnt\\|/media || true"
```
Result:
```
(no output)
```

## Outstanding Runtime Checks

- Monitoring, Home Assistant, Reverse Proxy mounts validated (no /mnt or /media mounts detected).
