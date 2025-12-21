# Disaster Recovery Drill Runbook

**Purpose**: Prove Immich photo backup recovery from Hetzner Object Storage without Synology NAS or Proxmox infrastructure.

**Last Updated**: December 21, 2025  
**Estimated Duration**: 2-4 hours (depends on download bandwidth)  
**Data Scope**: Immich photos (1.73 TB total, ~10-50 GB sample for selective restore)

---

## Overview

This runbook validates that encrypted Immich photo backups stored in Hetzner Object Storage can be successfully accessed, downloaded, decrypted, and verified from any independent machine (laptop or fresh VM). The drill uses Synology Hyper Backup Explorer's selective restore feature to extract a sample of 10-20 photos as proof of recovery capability.

**Success Criteria**: Extract and verify 10-20 Immich photos are viewable, proving end-to-end recovery without original infrastructure.

---

## Prerequisites

### Tools Required

1. **rclone** - S3-compatible object storage client
   - Linux: `sudo apt install rclone` or `sudo dnf install rclone`
   - macOS: `brew install rclone`
   - Windows: `choco install rclone` or download from [rclone.org](https://rclone.org/downloads/)

2. **Synology Hyper Backup Explorer** - Backup decryption and extraction
   - Linux: Download from [Synology Download Center](https://www.synology.com/en-us/support/download/) (may require Wine)
   - macOS: Download Mac version from Synology Download Center
   - Windows: Download Windows installer from Synology Download Center

3. **Standard utilities** (usually pre-installed):
   - bash/zsh shell
   - sha256sum (or shasum on macOS)
   - Disk space: ~100-150 GB free

### Credentials Required (from Bitwarden)

Retrieve the following from Bitwarden before starting:

1. **Hetzner S3 Credentials** (Bitwarden item: `[BITWARDEN_ITEM_NAME]`)
   - Access Key ID
   - Secret Access Key
   - Endpoint: `nbg1.your-objectstorage.com`
   - Bucket: `synbackup`

2. **Backup Encryption Key** (Bitwarden item: `[BITWARDEN_ENCRYPTION_KEY_ITEM]`)
   - Used by Hyper Backup Explorer to decrypt backup

---

## Phase A: Hetzner Access Verification

**Goal**: Confirm Hetzner S3 credentials work and Hyper Backup backup is accessible.

### A1. Install rclone

```bash
# macOS
brew install rclone

# Linux (Debian/Ubuntu)
sudo apt update && sudo apt install rclone

# Linux (RHEL/Fedora)
sudo dnf install rclone

# Verify installation
rclone version
```

### A2. Configure rclone

```bash
cd /path/to/homelab-proxmox/scripts/dr/

# Copy configuration template
cp rclone.conf.example rclone.conf
cp .env.example .env

# Edit .env with credentials from Bitwarden
nano .env  # or vim, code, etc.
```

**Required .env values:**
```bash
HETZNER_S3_ENDPOINT="https://nbg1.your-objectstorage.com"
HETZNER_S3_BUCKET="synbackup"
HETZNER_S3_ACCESS_KEY="<from-bitwarden>"
HETZNER_S3_SECRET_KEY="<from-bitwarden>"
BACKUP_PATH="DiskStation413j_1.hbk"
RCLONE_REMOTE_NAME="hetzner-backup"
```

**Edit rclone.conf:**
```bash
nano rclone.conf
```

Replace `YOUR_ACCESS_KEY_ID_FROM_BITWARDEN` and `YOUR_SECRET_KEY_FROM_BITWARDEN` with actual values.

### A3. Test bucket access

```bash
# Source environment variables
source .env

# List bucket contents
./hetzner_list.sh DiskStation413j_1.hbk
```

**Expected output:**
```
Config/
Control/
Guard/
Pool/
_Syno_TaskConfig
...
```

**⚠️ STOP POINT**: If bucket listing fails, STOP and troubleshoot:
- Verify credentials in Bitwarden are current
- Test network: `curl -I https://nbg1.your-objectstorage.com`
- Check bucket name: `synbackup`
- Verify endpoint is reachable

---

## Phase B: Download Sample Data

**Goal**: Download _Syno_TaskConfig (1.63 KB) for connectivity test, then metadata + one Pool chunk.

### B1. Write download script

The `hetzner_download.sh` script is already created in the repository. Make it executable:

```bash
chmod +x hetzner_download.sh
```

### B2. Download small test file (_Syno_TaskConfig)

```bash
# Dry-run first (safe, shows what would be downloaded)
DOWNLOAD_DRY_RUN=true ./hetzner_download.sh "DiskStation413j_1.hbk/_Syno_TaskConfig" ~/dr-restore/test

# Actual download (1.63 KB)
DOWNLOAD_DRY_RUN=false ./hetzner_download.sh "DiskStation413j_1.hbk/_Syno_TaskConfig" ~/dr-restore/test

# Verify file size
ls -lh ~/dr-restore/test/_Syno_TaskConfig
```

**Expected**: File is 1.63 KB (~1600 bytes).

**⚠️ STOP POINT**: If small file download fails, STOP and troubleshoot before downloading larger files.

### B3. Download metadata folders

```bash
# Create metadata directory
mkdir -p ~/dr-restore/metadata

# Download Config, Control, Guard folders
for folder in Config Control Guard; do
  echo "Downloading ${folder}..."
  DOWNLOAD_DRY_RUN=false ./hetzner_download.sh "DiskStation413j_1.hbk/${folder}" ~/dr-restore/metadata/
done
```

### B4. Download one Pool chunk (sample data)

```bash
# List Pool folder to identify chunks
./hetzner_list.sh DiskStation413j_1.hbk/Pool

# Select one chunk file (typically 100 MB - 50 GB)
# Example chunk name: Pool/0/0/0000000000000001
CHUNK_FILE="<chunk-file-from-listing>"

# Download selected chunk
DOWNLOAD_DRY_RUN=false ./hetzner_download.sh "DiskStation413j_1.hbk/Pool/${CHUNK_FILE}" ~/dr-restore/sample-data/
```

**Document download metrics** (for drill report):
- _Syno_TaskConfig: 1.63 KB, [duration], [bandwidth]
- Metadata folders: [size], [duration]
- Pool chunk: [size], [duration]
- Total downloaded: [GB]

---

## Phase C: Decrypt & Extract Photos

**Goal**: Use Hyper Backup Explorer's selective restore to extract 10-20 Immich photos.

### C1. Install Hyper Backup Explorer

**macOS:**
```bash
# Download from https://www.synology.com/en-us/support/download/
# Search for "Hyper Backup Explorer"
# Install .dmg package
open ~/Downloads/HyperBackupExplorer-*.dmg
```

**Linux:**
```bash
# Download Windows version and use Wine, or
# Check if Linux native version is available
# See Synology Download Center for latest options
```

**Windows:**
```bash
# Download installer from Synology Download Center
# Run HyperBackupExplorer-setup.exe
```

### C2. Retrieve encryption key from Bitwarden

Open Bitwarden and navigate to item `[BITWARDEN_ENCRYPTION_KEY_ITEM]`. Copy the encryption password.

### C3. Open backup in Hyper Backup Explorer

1. Launch Hyper Backup Explorer
2. **File → Browse for Backup**
3. Navigate to `~/dr-restore/metadata/`
4. Select the folder containing Config, Control, Guard
5. Enter encryption password when prompted (from Bitwarden)
6. Wait for backup to load

**Expected**: Folder tree displays with Immich backup structure visible (e.g., `/immich/library/` or `/var/lib/immich/`).

### C4. Navigate to Immich photos folder

In Hyper Backup Explorer:
1. Expand folder tree
2. Locate Immich photos directory (typically `/immich/library/photos/` or similar)
3. Browse date folders to find photo files

### C5. Select sample photos for extraction

1. Select 10-20 photo files from different date folders
2. Choose variety: different dates, file types (jpg, png, heic, raw)

### C6. Extract selected photos

1. Right-click selected photos → **Restore**
2. Choose target directory: `~/dr-restore/extracted/`
3. Monitor extraction progress
4. Record extraction time

**⚠️ STOP POINT**: If decryption fails or extraction errors occur:
- Verify encryption key from Bitwarden is correct
- Check metadata folders are complete (Config, Control, Guard)
- Re-download metadata if corrupted
- Consider break-glass procedure if Bitwarden key is incorrect

---

## Phase D: Verify Photo Integrity

**Goal**: Confirm extracted photos are viewable and uncorrupted.

### D1. Count extracted photos

```bash
cd ~/dr-restore/extracted
find . -type f -iname "*.jpg" -o -iname "*.png" -o -iname "*.heic" -o -iname "*.raw" | wc -l
```

**Expected**: 10-20 photo files.

### D2. Generate SHA256 hashes

```bash
find ~/dr-restore/extracted -type f | while read file; do
  sha256sum "$file"
done > ~/dr-restore/verification-hashes.txt

# View hashes
cat ~/dr-restore/verification-hashes.txt
```

### D3. Manually inspect photos

1. Open 3-5 photos in image viewer (Preview, Photos, Windows Photo Viewer)
2. Verify images display correctly:
   - No corruption artifacts
   - Recognizable content
   - Colors appear natural

### D4. Check EXIF data (optional)

```bash
# macOS/Linux
exiftool ~/dr-restore/extracted/<photo>.jpg

# Or use image viewer properties
```

Verify EXIF metadata is present (date, camera model, etc.).

### D5. Generate verification summary

**Document in drill notes:**
- Total photos extracted: [10-20]
- SHA256 hashes: [DOCUMENTED in verification-hashes.txt]
- Manual inspection: [PASS - 3-5 photos viewable]
- EXIF data: [PASS/SKIP]
- **Overall assessment**: SUCCESS (Immich photos recoverable from Hetzner backup)

**⚠️ STOP POINT**: If photos are corrupted or unreadable:
- Re-download Pool chunk (may be corrupted)
- Verify encryption key is correct
- Check Hyper Backup Explorer version compatibility
- Investigate backup integrity at source

---

## Phase E: Documentation

### E1. Complete drill report

Use template in `specs/012-disaster-recovery-drill/tasks.md` (T039) to document:
- Execution date and duration
- Download metrics (data volume, bandwidth, costs)
- Success/failure by phase
- Issues encountered and resolutions
- Lessons learned

Save as: `scripts/dr/drill-reports/YYYY-MM-DD-drill-report.md`

### E2. Update this runbook

Add any lessons learned:
- Clarify ambiguous steps
- Add troubleshooting for new issues encountered
- Update timing estimates based on actual execution

---

## Break-Glass Procedures

**IMPORTANT**: All break-glass storage is PHYSICAL/OFFLINE ONLY. No encryption keys stored in git repository.

### When to Use Break-Glass

If Bitwarden is inaccessible (service outage, forgotten master password), use these alternative methods to retrieve the encryption key.

### Method 1: Encrypted USB Drive (Primary)

1. **Location**: Physical USB drive labeled "DR Keys" in fireproof safe at `[LOCATION]`
2. **Contents**: Encrypted file with Hetzner S3 credentials and backup encryption key
3. **Decryption**: USB is encrypted with LUKS/VeraCrypt, password at `[LOCATION]`
4. **Validation**: Test USB accessibility during annual break-glass drill

### Method 2: Paper Backup (Secondary)

1. **Location**: Sealed envelope at `[LOCATION]`
2. **Contents**: Printed QR codes or handwritten credentials
3. **Access**: Envelope is tamper-evident; if seal broken, rotate credentials
4. **Limitations**: Vulnerable to same disaster that destroyed infrastructure; store off-site

### Method 3: Trusted Contact (Tertiary)

1. **Procedure**: Contact `[TRUSTED_PERSON]` to retrieve encrypted KeePass file
2. **Retrieval**: Secure channel (encrypted email, Signal, in-person)
3. **Decryption**: KeePass password known to trusted contact
4. **Validation**: Periodically confirm contact has current copy

### After Break-Glass Use

1. Immediately test retrieved credentials by connecting to Hetzner S3
2. Complete drill using break-glass credentials
3. After drill, rotate all credentials and update primary source (Bitwarden)
4. Document break-glass usage in drill report

---

## Troubleshooting

### "S3 auth failed" / Access Denied

**Symptoms**: rclone returns 403 Forbidden or authentication errors

**Resolution**:
1. Verify credentials in Bitwarden are current (not expired)
2. Check endpoint URL: `nbg1.your-objectstorage.com` (no typos)
3. Confirm bucket name: `synbackup`
4. Regenerate S3 credentials in Hetzner console if expired
5. Update Bitwarden and re-run configuration

### "Hyper Backup won't open" / Backup not recognized

**Symptoms**: Hyper Backup Explorer can't load backup or shows errors

**Resolution**:
1. Verify all metadata folders downloaded: Config/, Control/, Guard/
2. Check folder structure is preserved (not flattened)
3. Re-download metadata if any files missing
4. Try older/newer version of Hyper Backup Explorer
5. Check Synology forums for compatibility issues

### "Decryption failed" / Wrong password

**Symptoms**: Hyper Backup Explorer rejects encryption password

**Resolution**:
1. Verify encryption key copied correctly from Bitwarden (no extra spaces)
2. Check if key field vs notes section in Bitwarden
3. Try break-glass procedure (USB drive, paper backup)
4. Contact Synology support if format has changed
5. Investigate if encryption key was rotated without updating Bitwarden

### "Photos corrupted" / Images won't open

**Symptoms**: Extracted files exist but won't display or have 0 bytes

**Resolution**:
1. Verify Pool chunk downloaded completely (check file size)
2. Re-download Pool chunk if network interrupted
3. Try different photos from different date folders
4. Check disk space wasn't exhausted during extraction
5. Investigate backup integrity at source (Synology backup logs)

### "rclone slow" / Downloads taking too long

**Symptoms**: Download speed is much slower than expected

**Resolution**:
1. Check local network speed: `speedtest-cli`
2. Adjust rclone `--transfers` flag (default 4, try 8-16)
3. Use `--multi-thread-streams` for large files
4. Consider downloading from colocation or cloud VM with better bandwidth
5. Schedule download during off-peak hours if Hetzner throttles

---

## Next Drill

**Recommended Frequency**: Quarterly (every 3 months)

**Improvements to Test**:
- Break-glass procedure (annual test required)
- Restore from different backup date
- Test on different OS platform
- Measure RTO improvement
- Validate any backup format changes

---

## References

- **Specification**: [specs/012-disaster-recovery-drill/spec.md](../../specs/012-disaster-recovery-drill/spec.md)
- **Implementation Plan**: [specs/012-disaster-recovery-drill/plan.md](../../specs/012-disaster-recovery-drill/plan.md)
- **Tasks Breakdown**: [specs/012-disaster-recovery-drill/tasks.md](../../specs/012-disaster-recovery-drill/tasks.md)
- **Scripts**: [scripts/dr/](../../scripts/dr/)
- **rclone Documentation**: [https://rclone.org/docs/](https://rclone.org/docs/)
- **Synology Hyper Backup**: [https://www.synology.com/en-us/dsm/feature/hyper_backup](https://www.synology.com/en-us/dsm/feature/hyper_backup)
