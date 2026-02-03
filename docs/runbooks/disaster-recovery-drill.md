# Disaster Recovery Drill Runbook

> **Current playbook**: For the PVE → NAS → DSM drill, use the dedicated runbook at [docs/runbooks/dr-drill-playbook.md](docs/runbooks/dr-drill-playbook.md) and report template at [docs/runbooks/dr-drill-report-template.md](docs/runbooks/dr-drill-report-template.md).

**Purpose**: Prove Immich photo backup recovery from Hetzner Object Storage without Synology NAS or Proxmox infrastructure.

**Last Updated**: December 21, 2025  
**Status**: Phase D Partial Completion - Critical structure findings documented  
**Next Attempt**: January 2026 with external storage

**Estimated Duration**: 4-6 hours (depends on download bandwidth and disk space)  
**Data Scope**: Immich photos (1.73 TB original, ~355 GB Pool buckets + 9 GB metadata = **~365 GB total** required for complete extraction)

⚠️ **IMPORTANT DRILL FINDINGS (December 2025)**:
- Backup size significantly larger than initial estimate (355 GB vs 15 GB)
- Pool structure has nested subdirectories: `Pool/0/0/`, `Pool/0/1/`, ... `Pool/0/17/`
- Download script flattened directory structure - **requires fix before next attempt**
- Hyper Backup Explorer validates complete bucket integrity before allowing extraction
- Partial data downloads result in "data corrupted" error
- **Minimum disk space**: 400 GB free (365 GB download + working space)
- **Recommended**: External drive or VM with 500+ GB available

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
   - **Disk space: 400-500 GB free** (365 GB backup + extracted photos + working space)
   - **Recommendation**: Use external drive or dedicated VM for drill

   ### macOS: Mount the NAS share via automounter (optional)

   If validating from a Mac, mount the NAS share with `autofs`:

   1) Add the map in `/etc/auto_nfs`:

   ```bash
   /Volumes/nas/homelab_ci  -fstype=nfs,rw,nfsvers=3,resvport  192.168.1.109:/volume1/homelab_ci
   /Volumes/nas/homelab_dr_test  -fstype=nfs,rw,nfsvers=3,resvport  192.168.1.109:/volume1/homelab_dr_test
   ```

   2) Ensure `/etc/auto_master` includes:

   ```bash
   /-    auto_nfs          -nobrowse
   ```

   3) Reload automount and verify:

   ```bash
   sudo automount -vc
   ls -la /Volumes/nas
   ```

   4) Create the DR target folder if needed:

   ```bash
   mkdir -p /Volumes/nas/homelab_dr_test
   chmod -R 777 /Volumes/nas/homelab_dr_test
   ```

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
cd /path/to/homelab-proxmox
task dr:hetzner:list -- DiskStation413j_1.hbk
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

**Goal**: Download _Syno_TaskConfig (1.63 KB) for connectivity test, then metadata + Pool indexes (~6 GB).

### B1. Download tooling

The repository provides `task` entrypoints that invoke the DR download scripts.

### B2. Download small test file (_Syno_TaskConfig)

```bash
# Dry-run first (safe, shows what would be downloaded)
DOWNLOAD_DRY_RUN=true task dr:hetzner:download -- "DiskStation413j_1.hbk/_Syno_TaskConfig" ~/dr-restore/test

# Actual download (1.63 KB)
DOWNLOAD_DRY_RUN=false task dr:hetzner:download -- "DiskStation413j_1.hbk/_Syno_TaskConfig" ~/dr-restore/test

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
   DOWNLOAD_DRY_RUN=false task dr:hetzner:download -- "DiskStation413j_1.hbk/${folder}" ~/dr-restore/metadata/
done
```

### B4. Download Pool indexes (photo data indexes)

```bash
# List Pool folder to verify structure
task dr:hetzner:list -- DiskStation413j_1.hbk/Pool | head -30

# Pool structure:
# - file_pool/: Small metadata files (~0.01 GB, 229 files)
# - chunk_index/: Deduped photo data indexes (~6 GB, 767 files at 8 MB each)
# - 0/0/, 0/1/, ... bucket subdirectories: Actual photo data chunks (100+ GB EACH)
# - Total Pool: ~271 GB across 11,891 files

# Download file_pool and chunk_index for testing (6 GB total)
mkdir -p ~/dr-restore/sample-data

# file_pool (~0.01 GB, metadata)
DOWNLOAD_DRY_RUN=false task dr:hetzner:download -- "DiskStation413j_1.hbk/Pool/file_pool" ~/dr-restore/sample-data/

# chunk_index (~6 GB, indexes)
DOWNLOAD_DRY_RUN=false task dr:hetzner:download -- "DiskStation413j_1.hbk/Pool/chunk_index" ~/dr-restore/sample-data/
```

**Expected**: ~6 GB download, 996 files, 5-10 minutes at 10-20 MiB/s bandwidth.

**Note**: Phase B completed December 2025 with metadata and indexes. Phase D (full download) deferred to next attempt with external storage.

**December 2025 download metrics**:
- _Syno_TaskConfig: 1.63 KB, <1s
- Config: 8.964 GB, 4m58s, 9.679 MiB/s
- Control: ~0 B
- Guard: 5.841 MB
- Pool indexes (file_pool + chunk_index): 5.987 GiB, 6m51s, 17.783 MiB/s
- Pool buckets: 271 GB (partial, folders 0, 10-17)
- **Total**: 271 GB in ~45 minutes (stopped due to disk space)
- Egress cost: €0.00 (within 1 TB free tier)

---

## Phase C: First Extraction Attempt (December 2025)

**Attempted**: Open backup in Hyper Backup Explorer with partial data (metadata + indexes only)

**Result**: ❌ Failed with error "Stored data on the backup destination are corrupted"

**Root Cause Discovery**:
1. Hyper Backup uses block-level deduplication
2. Files stored as chunks in Pool bucket subdirectories (Pool/0/0/, Pool/0/1/, etc.)
3. Metadata + indexes map files to chunks but don't contain actual photo data
4. Hyper Backup Explorer validates chunk integrity before allowing extraction
5. Missing/incomplete chunks → validation failure → corruption error

**Key Learning**: **Indexes alone cannot support file extraction** - complete bucket data required

---

## Phase C (Revised): Recovery Options Analysis

### Option 1: Download Full Backup Data (RECOMMENDED for production disaster)
- Download all Pool bucket subdirectories (~265 GB additional)
- Total download: 280 GB, ~3-4 hours at 20 MiB/s, €0.00 within 1 TB free tier
- Use Hyper Backup Explorer to browse and selectively restore
- **Pros**: Official Synology tool, full backup access
- **Cons**: Large download, time-consuming

### Option 2: Community Tool - hyperbackup_decrypt (EXPERIMENTAL)
- Python script: https://github.com/mistersandman/hyperbackup_decrypt (9 years old, may need updates)
- Directly decrypts Pool chunks without Hyper Backup Explorer
- Still requires downloading Pool bucket data
- **Pros**: Command-line access, no NAS needed
- **Cons**: Unmaintained, requires Python setup, still needs full data download

### Option 3: Synology C2 Storage Connection (EASIEST for testing)
- Configure Hyper Backup to also backup to Synology C2 Storage
- Use Hyper Backup Explorer "Browse backup in Synology C2 Storage"
- Browse and restore directly from C2 without downloads
- **Pros**: No downloads, official support, instant access
- **Cons**: Additional subscription cost (~$5/TB/month)

### Option 4: Mount Backup on Replacement NAS (REALISTIC DR scenario)
- Obtain replacement Synology NAS (same or newer model)
- Connect to Hetzner S3 via Hyper Backup
- Use "Data Relink" feature to reconnect to existing backup
- Restore files directly to new NAS
- **Pros**: Official DR workflow, full backup access
- **Cons**: Requires purchasing/borrowing replacement NAS

**DRILL DECISION POINT**: For this drill validation, choose Option 1 to prove end-to-end recovery capability.

**DRILL DECISION POINT**: For this drill validation, choose Option 1 to prove end-to-end recovery capability.

---

## Phase D: Download Pool Bucket Data (December 2025 Partial Attempt)

**Status**: Partial completion with critical findings

### D1. December 2025 Drill Results

**Downloaded**:
- Config: 9 GB ✅
- Control: ~0 B ✅
- Guard: 5.8 MB ✅
- Pool indexes: 6 GB (file_pool + chunk_index) ✅
- Pool buckets: 271 GB partial (folders 0, 10-17 only) ⚠️

**Missing**:
- Pool/0/1/ through Pool/0/9/ (~110 GB)
- Other Pool bucket subdirectories

**Total Downloaded**: 271 GB  
**Total Required**: ~365 GB  
**Completion**: ~74%

### D2. Critical Findings

**1. Backup Structure Discovery**:
```
DiskStation413j_1.hbk/
├── Config/ (9 GB metadata)
├── Control/ (version control)
├── Guard/ (integrity DBs)
├── Pool/
│   ├── file_pool/ (file metadata, 229 files)
│   ├── chunk_index/ (chunk mappings, 767 files @ 8MB each)
│   └── 0/ ← NESTED STRUCTURE!
│       ├── 0/ (bucket subdirectory with .bucket.2 and .index.2 files)
│       ├── 1/ (bucket subdirectory)
│       ├── 2/ ... 17/ (18 subdirectories total)
│       └── Each ~20-30 GB
├── SynologyHyperBackup.bkpi (0 bytes marker file)
└── synobkpinfo.db (3 KB)
```

**2. Download Script Issue**:
- Current script (via Taskfile): `task dr:hetzner:download -- "DiskStation413j_1.hbk/Pool/0" <target_dir>`
- rclone flattened structure, downloaded Pool/0/X/ to backup root as X/
- **Fix required**: Download must preserve nested paths

**3. Hyper Backup Explorer Validation**:
- Tool validates bucket integrity before allowing file browsing
- Missing or incorrectly structured buckets → "data corrupted" error
- Cannot extract files without complete bucket data in correct structure

**4. Disk Space Requirements**:
- Initial estimate: 20 GB (wrong)
- Actual requirement: 365 GB minimum
- Drill machine: 460 GB total, insufficient for complete download + OS + apps

### D3. Lessons Learned for Next Attempt

**✅ What Worked**:
- Hetzner S3 credentials and access ✅
- rclone configuration and downloads ✅
- Backup structure discovery and documentation ✅
- Egress costs: €0.00 (within 1 TB free tier) ✅

**❌ What Failed**:
- Insufficient disk space (need 500 GB+)
- Download script path handling
- Initial size estimate off by ~350 GB
- Assumption that indexes alone sufficient for extraction

**🔧 Required Fixes**:
1. Update download script to preserve directory structure
2. Use external drive or VM with 500+ GB space
3. Download complete Pool bucket structure
4. Verify structure before attempting extraction

**📋 Next Attempt Checklist**:
- [ ] External drive with 500+ GB available
- [ ] Fixed download script (preserve paths)
- [ ] Download all Pool/0/0/ through Pool/0/17/
- [ ] Verify structure: `ls ~/dr-restore/backup/.../Pool/0/0/*.bucket.2`
- [ ] Open in Hyper Backup Explorer
- [ ] Extract sample photos
- [ ] Document complete success or blockers

---

## Phase E: Extract Photos with Hyper Backup Explorer (For Next Attempt)

### E1. Open Complete Backup

1. Launch Hyper Backup Explorer
2. Click **"Browse Local Backup"**
3. Navigate to `~/dr-restore/backup/DiskStation413j_1.hbk/`
4. **Select the `SynologyHyperBackup.bkpi` file**
5. Enter encryption password when prompted (from Bitwarden)
6. Wait for backup to load (may take 2-5 minutes for full validation)

**Expected**: Folder tree displays with backup structure visible

### E2. Navigate to Immich Photos

1. Expand folder tree: **@Share → homelab_immich**
2. Locate photo storage directory (likely `upload/` or `library/` subfolder)
3. Browse date folders to find photos

### E3. Extract Sample Photos

1. Select 10-20 photos from different dates/users
2. Right-click → **Restore**
3. Target directory: `~/dr-restore/extracted/`
4. Monitor extraction progress

### E4. Verify Extraction

```bash
# Count extracted files
find ~/dr-restore/extracted -type f -name "*.jpg" -o -name "*.png" -o -name "*.heic" | wc -l

# Generate SHA256 hashes
find ~/dr-restore/extracted -type f | while read file; do
  sha256sum "$file"
done > ~/dr-restore/verification-hashes.txt
```

### E5. Manual Photo Inspection

1. Open 3-5 photos in image viewer (Preview.app on macOS)
2. Verify:
   - Images display correctly (no corruption)
   - Recognizable content
   - Natural colors
   - EXIF data present

**SUCCESS CRITERIA**: 10-20 photos extracted, viewable, and uncorrupted.

---

## Phase F: Drill Report and Documentation

## Phase F: Drill Report and Documentation

## Phase G: Drill Report and Cleanup (After Successful Extraction)

### G1. Complete drill report

Use template in `specs/012-disaster-recovery-drill/tasks.md` (T039) to document:
- Execution date and duration
- Download metrics (data volume, bandwidth, costs)
- Success/failure by phase
- Issues encountered and resolutions
- Lessons learned

Save as: `scripts/dr/drill-reports/YYYY-MM-DD-drill-report.md`

### G2. Update this runbook

Add any lessons learned:
- Clarify ambiguous steps
- Add troubleshooting for new issues encountered
- Update timing estimates based on actual execution

---

## Phase F: Next Attempt Instructions (January 2026)

### F1. Preparation

**Required Resources**:
- [ ] External drive with **500+ GB free space** (or VM with dedicated storage)
- [ ] Updated download script (fixes applied December 2025)
- [ ] Hetzner credentials from Bitwarden
- [ ] Backup encryption key from Bitwarden
- [ ] 4-6 hours available for download

**Environment Setup**:
```bash
# If using external drive
export DR_RESTORE_PATH="/Volumes/ExternalDrive/dr-restore"
mkdir -p "$DR_RESTORE_PATH/backup"

# If using VM
# Ensure VM has 500GB disk, mount at /mnt/dr-restore
export DR_RESTORE_PATH="/mnt/dr-restore"
```

### F2. Complete Pool Download (CORRECTED)

The December 2025 script has been fixed to preserve directory structure.

```bash
cd /Users/Andreas.Jacobsen/Development/private/homelab-proxmox

# Download all Pool/0 subdirectories (0/ through 17/)
# Script now preserves nested structure: Pool/0/0/, Pool/0/1/, etc.
for i in {0..17}; do
  echo "Downloading Pool/0/$i..."
   DOWNLOAD_DRY_RUN=false task dr:hetzner:download -- \
    "DiskStation413j_1.hbk/Pool/0/$i" \
    "$DR_RESTORE_PATH/backup"
done
```

**Expected Result**:
```
$DR_RESTORE_PATH/backup/DiskStation413j_1.hbk/
├── Config/
├── Control/
├── Guard/
├── Pool/
│   ├── file_pool/
│   ├── chunk_index/
│   └── 0/
│       ├── 0/ (*.bucket.2, *.index.2 files)
│       ├── 1/
│       ├── 2/
│       └── ... 17/
├── SynologyHyperBackup.bkpi
└── synobkpinfo.db
```

**Verification**:
```bash
# Check structure
ls -la "$DR_RESTORE_PATH/backup/DiskStation413j_1.hbk/Pool/0/"
# Should show: 0/ 1/ 2/ ... 17/ (18 subdirectories)

# Check bucket files exist
ls "$DR_RESTORE_PATH/backup/DiskStation413j_1.hbk/Pool/0/0/" | head
# Should show: 0.bucket.2, 0.index.2, 1.bucket.2, 1.index.2, etc.

# Check total size
du -sh "$DR_RESTORE_PATH/backup/DiskStation413j_1.hbk/"
# Should show: ~365 GB
```

### F3. Extract Photos with Hyper Backup Explorer

1. Launch Hyper Backup Explorer
2. Browse Local Backup → Select `$DR_RESTORE_PATH/backup/DiskStation413j_1.hbk/SynologyHyperBackup.bkpi`
3. Enter encryption password (from Bitwarden)
4. Wait for validation (may take 5-10 minutes with complete data)
5. Navigate to @Share → homelab_immich
6. Extract 10-20 sample photos to verify
7. Check photo metadata, viewability, EXIF data

### F4. Document Completion

If successful:
- [ ] Create drill report: `scripts/dr/drill-reports/2026-01-XX-drill-report.md`
- [ ] Update runbook with actual timings
- [ ] Note any issues encountered
- [ ] Commit and push findings

If failed:
- [ ] Document error messages and symptoms
- [ ] Check structure: `tree -L 3 $DR_RESTORE_PATH/backup/`
- [ ] Compare with expected structure above
- [ ] Open issue for further investigation

---

## Phase G: Drill Report and Cleanup (After Successful Extraction)

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
