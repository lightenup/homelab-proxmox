# Disaster Recovery Scripts

Scripts for disaster recovery drill execution - proving Immich photo backup recovery from Hetzner Object Storage.

## Prerequisites

- **rclone** installed ([installation guide](https://rclone.org/install/))
- **Bitwarden CLI** (optional, for automated credential retrieval)
- Disk space: free space >= 2× rclone size estimate for the full backup set
- Dedicated DR share mounted on PVE: `/mnt/nas/homelab_dr_test`

## Setup

1. **Copy configuration templates:**
   ```bash
   cp rclone.conf.example rclone.conf
   cp .env.example .env
   ```

2. **Retrieve credentials from Bitwarden:**
   - Hetzner S3 access key ID
   - Hetzner S3 secret access key
   - Backup encryption key

3. **Populate configuration files** with actual credentials (both files are gitignored)

4. **Source environment variables:**
   ```bash
   source .env
   ```

## Scripts

### hetzner_list.sh

List contents of Hetzner Object Storage bucket.

**Usage:**
```bash
./hetzner_list.sh [path]
```

**Examples:**
```bash
# List bucket root
./hetzner_list.sh

# List specific backup path
./hetzner_list.sh DiskStation413j_1.hbk

# Verify Hyper Backup structure
./hetzner_list.sh DiskStation413j_1.hbk | grep -E "(Config|Control|Guard|Pool)"
```

### hetzner_download.sh

Download backup files from Hetzner Object Storage.

**Usage:**
```bash
./hetzner_download.sh <source_path> [target_dir]
```

**Examples:**
```bash
# Dry-run download (default, safe)
DOWNLOAD_DRY_RUN=true ./hetzner_download.sh "DiskStation413j_1.hbk/_Syno_TaskConfig" ~/dr-restore/test

# Actual download
DOWNLOAD_DRY_RUN=false ./hetzner_download.sh "DiskStation413j_1.hbk/_Syno_TaskConfig" ~/dr-restore/test

# Download metadata folders
./hetzner_download.sh "DiskStation413j_1.hbk/Config" ~/dr-restore/metadata/

# Download Pool data (preserves nested structure under Pool/)
DOWNLOAD_DRY_RUN=false ./hetzner_download.sh "DiskStation413j_1.hbk/Pool" /mnt/nas/homelab_dr_test/drill-YYYYMMDD
```

### verify_restore.sh

Verify integrity of restored backup files.

**Usage:**
```bash
./verify_restore.sh <restore_path>
```

**Examples:**
```bash
# Verify extracted photos
./verify_restore.sh ~/dr-restore/extracted

# Generate hash report
./verify_restore.sh ~/dr-restore/extracted > verification-report.txt
```

## Configuration Files

### rclone.conf (gitignored)

rclone configuration for S3 access. Populated from `rclone.conf.example`.

### .env (gitignored)

Environment variables for scripts. Populated from `.env.example`.

**Required variables:**
- `HETZNER_S3_ENDPOINT` - Hetzner endpoint URL
- `HETZNER_S3_BUCKET` - Bucket name
- `HETZNER_S3_ACCESS_KEY` - Access key ID
- `HETZNER_S3_SECRET_KEY` - Secret access key
- `BACKUP_PATH` - Path within bucket
- `BACKUP_ENCRYPTION_KEY` - Encryption key for decryption
- `RCLONE_REMOTE_NAME` - Remote name in rclone.conf
- `DOWNLOAD_TARGET_DIR` - Local download directory

## Drill Reports

Completed drill reports are stored in `drill-reports/` (gitignored). Use the template in the runbook to document each drill execution.

## Troubleshooting

**"Environment variable RCLONE_REMOTE_NAME is required"**
- Ensure `.env` file exists and is sourced: `source .env`

**"rclone: command not found"**
- Install rclone: [https://rclone.org/install/](https://rclone.org/install/)

**"Failed to ls: NoSuchBucket"**
- Verify bucket name in `.env` matches Hetzner console
- Check endpoint URL is correct for your region

**"Access Denied"**
- Verify credentials in Bitwarden are current
- Check S3 access key has read permissions
- Regenerate credentials if expired

## Security Notes

- **Never commit** `rclone.conf` or `.env` files (covered by .gitignore)
- Rotate credentials after drill if exposed via screen recording or logs
- Use Bitwarden for credential storage (primary)
- Follow break-glass procedures if Bitwarden unavailable (see runbook)

## Related Documentation

- **Primary Runbook**: [docs/runbooks/dr-drill-playbook.md](../../docs/runbooks/dr-drill-playbook.md)
- **Legacy Runbook**: [docs/runbooks/disaster-recovery-drill.md](../../docs/runbooks/disaster-recovery-drill.md)
- **Specification**: [specs/030-dr-drill-playbook/spec.md](../../specs/030-dr-drill-playbook/spec.md)
