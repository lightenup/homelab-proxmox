# Laptop NFS Mount Setup for Rebuild Orchestrator

**Purpose**: Configure macOS for NFS access to NAS shares (backups, DR tests)

**When Needed**: Only to browse those shares from the laptop. **Not needed for Terraform state.** Since spec
067, Terraform state is local to `pve` (`/var/lib/homelab-proxmox/state/{prod,lab}`), and state-touching steps
run on `pve` as `ci` over SSH. There is no `infra_state` share to mount and no `USE_NAS_STATE` switch.

**Related**: [Proxmox API Token Setup](./proxmox-api-token-setup.md)

## Prerequisites

- macOS with sudo access
- Network connectivity to NAS (192.168.1.109)
- NFS client enabled (default on macOS)
- Synology NAS with homelab_ci share exported via NFS

## Configuration Steps

> **Important**: macOS autofs uses a **direct map** (`/-`) approach where each mount
> point is an absolute path in `/etc/auto_nfs`. Do NOT use an indirect map
> (`/Volumes/nas  auto_nfs`) — that pattern does not work reliably on macOS.

### 1. Create autofs direct map

Create or edit `/etc/auto_nfs` with one line per NAS share:

```bash
sudo tee /etc/auto_nfs <<'EOF'
/Volumes/nas/homelab_ci  -fstype=nfs,rw,nfsvers=3,resvport  192.168.1.109:/volume1/homelab_ci
/Volumes/nas/homelab_dr_test  -fstype=nfs,rw,nfsvers=3,resvport  192.168.1.109:/volume1/homelab_dr_test
/Volumes/nas/homelab_backups  -fstype=nfs,rw,nfsvers=3,resvport  192.168.1.109:/volume1/homelab_backups
EOF
```

> **Warning**: Do not leave blank lines in `/etc/auto_nfs` — macOS autofs stops
> parsing at the first blank line, silently dropping all entries after it.

### 2. Register direct map in auto_master

Edit `/etc/auto_master` and add this line (note the `/-` direct map key):

```bash
# Add this line to /etc/auto_master
/-    auto_nfs
```

Manual edit command:
```bash
sudo nano /etc/auto_master
# Add the line above, save with Ctrl+O, exit with Ctrl+X
```

### 3. Reload automount daemon

```bash
sudo automount -vc
```

Expected output (one entry per mount point):
```
automount: /net updated
automount: /home updated
automount: /Volumes/nas/homelab_ci updated
automount: /Volumes/nas/homelab_dr_test updated
automount: /Volumes/nas/homelab_backups updated
automount: no unmounts
```

### 4. Verify mounts

```bash
ls -la /Volumes/nas/homelab_ci
```

Expected: Directory listing showing NAS contents (mutmut-cache/, etc.)

## Troubleshooting

### Mount not appearing

**Symptom**: `ls: /Volumes/nas/homelab_ci: No such file or directory`

**Solutions**:
```bash
# 1. Check automount status
sudo automount -cv

# 2. Force reload
sudo automount -uc
sudo automount -vc

# 3. Check firewall allows NFS
# NAS should allow your laptop IP in NFS export rules
```

### Permission denied

**Symptom**: `ls: /Volumes/nas/homelab_ci: Permission denied`

**Solutions**:
1. Verify NAS export allows your laptop IP
   - Login to Synology DSM
   - Control Panel → Shared Folder → homelab_ci → Edit → NFS Permissions
   - Ensure your IP (or subnet 192.168.1.0/24) is in allowed list
   - Privilege: Read/Write
   - Squash: No mapping

2. Check mount with correct NFS version:
   ```bash
   sudo mount -t nfs -o nfsvers=3,resvport 192.168.1.109:/volume1/homelab_ci /Volumes/nas/homelab_ci
   ```

### Stale mount

**Symptom**: `ls` hangs or returns errors about stale NFS file handle

**Solutions**:
```bash
# Force unmount
sudo umount -f /Volumes/nas/homelab_ci

# Reload automount
sudo automount -vc

# Test access
ls /Volumes/nas/homelab_ci
```

### Testing NFS connectivity

```bash
# Test NFS server is reachable
showmount -e 192.168.1.109

# Expected output:
# Exports list on 192.168.1.109:
# /volume1/homelab_ci    192.168.1.0/24
```

## Validation Tests

```bash
# Test 1: Mount auto-triggers on access
ls /Volumes/nas/homelab_backups/ | head
# Expected: the backup directories

# Test 2: Write access works (create and remove a test file)
touch /Volumes/nas/homelab_dr_test/.laptop-test-$(date +%s) && rm /Volumes/nas/homelab_dr_test/.laptop-test-*
# Expected: No error
```

## Terraform state is not on the NAS

State is read and written on `pve`, not through this mount:

```bash
ssh pve 'ls /var/lib/homelab-proxmox/state/prod/'
```

See [docs/operations/rebuild-orchestrator.md](../operations/rebuild-orchestrator.md) (State Architecture) and
[state-drift.md](./state-drift.md).

## Removal

To remove the autofs configuration:

```bash
# 1. Remove auto_master entry
sudo nano /etc/auto_master
# Delete the /Volumes/nas line

# 2. Remove map file
sudo rm /etc/auto_nfs

# 3. Reload
sudo automount -vc
```

## Security Notes

- NFS traffic is unencrypted - only use on trusted networks
- Consider restricting NAS export to specific laptop MAC address
- Mount is read/write - be careful with accidental deletions
- Ensure laptop firewall allows NFS client traffic

## References

- macOS autofs: `man auto_master`, `man automount`
- Synology NFS setup: Control Panel → File Services → NFS
- Originally added by specs/033-idempotent-rebuild; state moved off the NAS in spec 067
