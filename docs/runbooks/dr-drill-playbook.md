# DR Drill Playbook (PVE → NAS → DSM)

**Purpose**: Prove end-to-end recovery by downloading the full encrypted Synology Hyper Backup from Hetzner S3 to the dedicated NAS DR share mounted on PVE, then validating decryption and browsing via DSM Hyper Backup Explorer.

**Scope**: This playbook targets the DR test share and verifies the full Pool structure. It does not modify production data.

**Estimated Duration**: 4–8 hours (depends on backup size and bandwidth).

---

## Assumptions

- The DR test share exists at `/volume1/homelab_dr_test` and is mounted on PVE at `/mnt/nas/homelab_dr_test`.
- Hetzner S3 credentials and the backup encryption key are stored in a secure vault (no secrets in repo).
- The drill runs on the PVE host (or a machine with access to the mounted share).
- DSM Hyper Backup Explorer is available on the Synology NAS for validation.

---

## Prerequisites

- **rclone** installed on the PVE host.
- **NFS mount** for `/mnt/nas/homelab_dr_test` is present and writable.
- **Free space** on the NAS share is **>= 2×** the rclone size estimate for the backup set.
- **Credentials** for Hetzner S3 and the backup encryption key available from secure storage.

### macOS: Mount the NAS share via automounter (optional)

If running the validation steps on macOS, mount the NAS share with `autofs`:

1) Add an automounter map in `/etc/auto_nfs`:

```bash
/Volumes/nas/homelab_ci  -fstype=nfs,rw,nfsvers=3,resvport  192.168.1.109:/volume1/homelab_ci
/Volumes/nas/homelab_dr_test  -fstype=nfs,rw,nfsvers=3,resvport  192.168.1.109:/volume1/homelab_dr_test
```

2) Ensure `/etc/auto_master` includes the map:

```bash
/-    auto_nfs          -nobrowse
```

3) Reload automount and verify mounts:

```bash
sudo automount -vc
ls -la /Volumes/nas
```

4) Create the DR target folder if needed:

```bash
mkdir -p /Volumes/nas/homelab_dr_test
chmod -R 777 /Volumes/nas/homelab_dr_test
```

### Required configuration files (gitignored)

In scripts/dr:

- `rclone.conf` (copy from `rclone.conf.example`)
- `.env` (copy from `.env.example`)

Populate `.env` with values from secure storage. Do not commit secrets.

---

## Readiness Checks (Required)

> Stop if any check fails.

### 1) Confirm mount and write access

```bash
mount | grep /mnt/nas/homelab_dr_test

touch /mnt/nas/homelab_dr_test/.dr-write-test && rm /mnt/nas/homelab_dr_test/.dr-write-test
```

### 2) Estimate backup size via rclone

```bash
cd /path/to/homelab-proxmox/scripts/dr
source .env

# Size estimate for the backup root
rclone size "${RCLONE_REMOTE_NAME}:${HETZNER_S3_BUCKET}/${BACKUP_PATH}"
```

Record the total size in bytes and/or GiB.

### 3) Verify free space >= 2× estimate

```bash
# Free space on target share (bytes)
df -B1 /mnt/nas/homelab_dr_test | tail -1 | awk '{print $4}'
```

If free space is < 2× size estimate, **STOP** and provision more space.

### 4) (Recommended) Prepare a portable working copy

To avoid rsync/CI overwriting the scripts during a long download, stage a local copy on the PVE host:

```bash
mkdir -p ~/dr-drill-sources
cp -a /path/to/homelab-proxmox/scripts/dr ~/dr-drill-sources/
```

Use `~/dr-drill-sources/dr` for the drill steps below.

---

## Drill Steps

### Step 1: Initialize configuration

```bash
cd /path/to/homelab-proxmox/scripts/dr

cp rclone.conf.example rclone.conf
cp .env.example .env

# Edit .env and rclone.conf with credentials from secure storage
```

> If you staged a portable copy, run the rest of the steps from `~/dr-drill-sources/dr` instead.

### Step 2: Confirm Hetzner access

```bash
cd /path/to/homelab-proxmox
source scripts/dr/.env

task dr:hetzner:list -- "${BACKUP_PATH}"
```

**Expected**: `Config/`, `Control/`, `Guard/`, `Pool/`, `_Syno_TaskConfig`, and other backup metadata entries.

### Step 3: Define a drill target directory

Use a dated drill directory under the dedicated share:

```bash
export DRILL_ROOT="/mnt/nas/homelab_dr_test/drill-$(date +%Y%m%d)"
mkdir -p "${DRILL_ROOT}"
```

### Step 4: Download the full backup set

> The download script preserves Pool subdirectory structure when `SOURCE_PATH` contains `Pool/`.

**Recommended**: run the download inside a tmux session so you can detach and reattach later.

```bash
cd /path/to/homelab-proxmox/scripts/dr
source .env

# Root metadata files (required by DSM Hyper Backup Explorer)
DOWNLOAD_DRY_RUN=false ./hetzner_download.sh "${BACKUP_PATH}/SynologyHyperBackup.bkpi" "${DRILL_ROOT}"
DOWNLOAD_DRY_RUN=false ./hetzner_download.sh "${BACKUP_PATH}/synobkpinfo.db" "${DRILL_ROOT}"
DOWNLOAD_DRY_RUN=false ./hetzner_download.sh "${BACKUP_PATH}/storage_statistics.db.61" "${DRILL_ROOT}"

# Small metadata file (sanity check)
DOWNLOAD_DRY_RUN=false ./hetzner_download.sh "${BACKUP_PATH}/_Syno_TaskConfig" "${DRILL_ROOT}"

# Full metadata directories
DOWNLOAD_DRY_RUN=false ./hetzner_download.sh "${BACKUP_PATH}/Config" "${DRILL_ROOT}"
DOWNLOAD_DRY_RUN=false ./hetzner_download.sh "${BACKUP_PATH}/Control" "${DRILL_ROOT}"
DOWNLOAD_DRY_RUN=false ./hetzner_download.sh "${BACKUP_PATH}/Guard" "${DRILL_ROOT}"

# Full Pool data (preserves nested structure)
DOWNLOAD_DRY_RUN=false ./hetzner_download.sh "${BACKUP_PATH}/Pool" "${DRILL_ROOT}"
```

**Note**: This step can take hours. Monitor disk space during the download.

**Evidence**: Capture the `rclone.log` file (stored alongside the scripts) in the drill report.

### Step 5: Verify Pool structure integrity

```bash
# Example expected structure
ls -la "${DRILL_ROOT}/${BACKUP_PATH}/Pool/0/0" | head -20
```

**Expected**: Nested `Pool/0/0`, `Pool/0/1`, etc. with `.bucket.*` and `.index.*` files present.

Also confirm root metadata files exist:

```bash
ls -la "${DRILL_ROOT}/${BACKUP_PATH}/SynologyHyperBackup.bkpi" \
  "${DRILL_ROOT}/${BACKUP_PATH}/synobkpinfo.db" \
  "${DRILL_ROOT}/${BACKUP_PATH}/storage_statistics.db.61"
```

### Step 6: Validate decryption in DSM Hyper Backup Explorer

On the Synology NAS:

1. Open **Hyper Backup Explorer**.
2. Choose **Browse Local Backup**.
3. Point to the backup root on NAS: `/volume1/homelab_dr_test/drill-YYYYMMDD/${BACKUP_PATH}/`.
4. Select `SynologyHyperBackup.bkpi` when prompted.
5. Enter the encryption key from secure storage.
6. Verify the backup loads and that file browsing works.

### Step 7: Extract a sample set and verify

Extract 10–20 photos to a subfolder under the drill root, then run verification from PVE:

```bash
export EXTRACT_PATH="${DRILL_ROOT}/extracted"
mkdir -p "${EXTRACT_PATH}"

# After extraction via DSM, verify integrity
/path/to/homelab-proxmox/scripts/dr/verify_restore.sh "${EXTRACT_PATH}"
```

**macOS example (NFS mount):**

```bash
/path/to/homelab-proxmox/scripts/dr/verify_restore.sh "/Volumes/nas/homelab_dr_test/drill-YYYYMMDD/extracted"
```

---

## Reporting

1. Copy the drill report template:
   - `docs/runbooks/dr-drill-report-template.md`
2. Save the report under `scripts/dr/drill-reports/` (gitignored):

```bash
mkdir -p /path/to/homelab-proxmox/scripts/dr/drill-reports
cp /path/to/homelab-proxmox/docs/runbooks/dr-drill-report-template.md \
  /path/to/homelab-proxmox/scripts/dr/drill-reports/drill-$(date +%Y%m%d).md
```

3. Fill in outcomes, issues, and evidence links or paths.

---

## Failure Handling

- **Insufficient space**: Stop and expand storage. Re-run readiness checks.
- **Missing Pool structure**: Do not proceed to DSM. Re-run download for full `Pool/`.
- **Access denied**: Validate credentials and endpoint; re-run list operation.
- **DSM reports corruption**: Confirm full dataset downloaded and directory structure intact.

---

## References

- [scripts/dr/README.md](../../scripts/dr/README.md)
- [docs/runbooks/disaster-recovery-drill.md](disaster-recovery-drill.md)
- [specs/030-dr-drill-playbook/spec.md](../../specs/030-dr-drill-playbook/spec.md)
