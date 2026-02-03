# Implementation Plan: Disaster Recovery Drill

**Feature**: `012-disaster-recovery-drill`
**Created**: December 21, 2025
**Status**: Draft
**Updated**: December 21, 2025

## Overview

This implementation plan establishes a validated disaster recovery capability for encrypted backups stored in Hetzner Object Storage. The approach prioritizes manual execution with scripted automation for repeatable steps, validating that backups can be successfully accessed, downloaded, decrypted, and verified from any machine without dependency on existing Proxmox or Synology infrastructure. The plan structures the drill into five phases (access verification, small file test, full download, decrypt/extract, integrity validation) with explicit stop points to prevent wasted effort if earlier phases fail. All credentials and encryption keys remain outside of git, retrieved from Bitwarden during drill execution with documented break-glass alternatives. The primary deliverables are a human-readable runbook, three shell scripts for automation, and a completed drill report demonstrating end-to-end recovery capability.

## Technical Approach

### Architecture Decision: S3 Access Tooling

**Choice**: Use `rclone` with S3-compatible backend for Hetzner Object Storage access

**Rationale**:
- Industry-standard tool for cloud storage access with extensive S3 compatibility
- Supports resume on interrupted transfers (critical for large backup downloads)
- Configuration file-based credential management (can be .gitignored)
- Native support for Hetzner-specific S3 endpoint URLs
- Cross-platform (Linux, macOS, Windows) ensures drill portability
- Active development and strong community support
- Scriptable CLI with progress output and dry-run modes

**Alternatives considered**:
- **AWS CLI (`aws s3`)**: Rejected - AWS-specific defaults and configuration patterns; less intuitive for non-AWS S3 services
- **s3cmd**: Rejected - older tool with less active development; rclone has better performance and feature set
- **MinIO Client (`mc`)**: Considered - excellent S3 tool but less widely known; rclone is more standard
- **Cyberduck/Transmit**: Rejected - GUI tools not suitable for scripted automation
- **Python boto3 library**: Rejected - requires Python environment setup; shell scripts with rclone are simpler

**Decision**: Adopt rclone as primary S3 access tool; document installation in runbook prerequisites

---

### Architecture Decision: Backup Format Validation

**Choice**: Confirm backup format empirically during Phase A (bucket listing) before selecting decrypt tooling

**Rationale**:
- Initial assumption is Synology Hyper Backup format, but this must be validated
- Different backup formats require different decrypt/extract tooling:
  - Hyper Backup: Synology Hyper Backup Explorer (proprietary)
  - restic: `restic restore` command
  - borg: `borg extract` command
  - tar.gz.gpg: `gpg` + `tar` commands
- Premature tooling installation wastes time if format assumption is wrong
- Decision checkpoint in tasks prevents over-investment before confirmation

**Alternatives considered**:
- **Assume Hyper Backup and install tools upfront**: Rejected - wastes effort if assumption wrong
- **Support all formats simultaneously**: Rejected - over-engineering for first drill; add support as needed
- **Contact person who configured backups**: Considered but rejected - drill should be self-sufficient with documentation

**Decision**: Include explicit decision checkpoint task (T004) to examine backup object names/structure and confirm format before proceeding to decrypt phase

---

### Architecture Decision: Credential Management

**Choice**: Environment variables + .gitignored local config files for all credentials

**Rationale**:
- Prevents accidental credential commits (most critical requirement)
- Environment variables are standard for CLI tools (rclone, aws-cli)
- Local config files (e.g., `~/.config/rclone/rclone.conf`) are tool-native
- .gitignore entries protect local files from being added to repository
- Supports both manual drill execution and future automation
- Credentials are ephemeral during drill (pulled from Bitwarden at start)

**Alternatives considered**:
- **Ansible Vault for credentials**: Rejected - requires Ansible environment setup; drill must be simpler
- **Hardcoded credentials in scripts**: Rejected - security anti-pattern and FR-005 violation
- **Secrets stored in repository (encrypted)**: Rejected - increases attack surface and complexity
- **Pass through CLI arguments**: Considered - less secure (visible in process list) than env vars

**Decision**: Scripts read from environment variables with clear documentation of required vars; rclone config file is .gitignored

---

### Architecture Decision: Break-Glass Key Storage

**Choice**: Multi-layered approach - Primary: encrypted USB drive, Secondary: paper backup, Tertiary: trusted contact with encrypted file

**Rationale**:
- Single point of failure (Bitwarden-only) is unacceptable for disaster recovery
- Encrypted USB drive provides offline, portable backup with good security/convenience tradeoff
- Paper backup survives digital failures but vulnerable to physical destruction (use off-site)
- Trusted contact provides geographic redundancy at cost of trust requirement
- Multiple layers ensure at least one method survives most disaster scenarios
- Each method requires different failure mode (digital failure, physical destruction, trust breakdown)

**Alternatives considered**:
- **Bitwarden-only**: Rejected - single point of failure contradicts disaster recovery principles
- **Plaintext paper in safe**: Rejected - insufficient security for encryption keys
- **Cloud-stored encrypted file**: Considered - but same failure mode as Bitwarden (service outage)
- **Blockchain/distributed storage**: Rejected - over-engineered and unfamiliar recovery process

**Decision**: Implement three-tier break-glass procedure documented in spec.md with annual testing requirement

---

## Implementation Phases

### Phase A: Hetzner Access Verification

**Goal**: Confirm Hetzner Object Storage S3 credentials work and backups are accessible from independent machine

**Steps**:
1. Install rclone on test machine (laptop or fresh Linux VM)
2. Create `.gitignore` entries for `scripts/dr/*.conf`, `scripts/dr/*.env`
3. Create rclone configuration template (`scripts/dr/rclone.conf.example`) with placeholders
4. Document Bitwarden credential retrieval in runbook (specific item names/paths)
5. Configure rclone with actual credentials from Bitwarden (local config file)
6. Write `scripts/dr/hetzner_list.sh` to list bucket contents using rclone
7. Execute list script and confirm backup objects visible

**Validation**: Script outputs list of backup files/directories; no authentication errors

**Stop Point**: If bucket listing fails, STOP and troubleshoot credentials before proceeding to download

---

### Phase B: Download Drill Payload

**Goal**: Download backup data to local machine, starting with small test file to validate connectivity

**Steps**:
1. Write `scripts/dr/hetzner_download.sh` with dry-run support and progress logging
2. Identify small test file from bucket listing (target: <100MB)
3. Execute download script in dry-run mode (verify what would be downloaded)
4. Execute download script for small test file (actual download)
5. Verify small file integrity (checksum if available, file size match at minimum)
6. STOP POINT: Review small download success before proceeding to full backup
7. Execute download script for full backup (or representative subset if full backup is extremely large)
8. Document download timing, bandwidth usage, file sizes

**Validation**: Downloaded files exist locally, sizes match expected, no corruption errors

**Stop Point**: If small file download fails, STOP and troubleshoot network/credentials; do NOT attempt full backup download

---

### Phase C: Backup Format Confirmation & Decrypt

**Goal**: Confirm backup format and decrypt/extract files using appropriate tooling

**Steps**:
1. **DECISION CHECKPOINT**: Examine backup file structure and naming
   - Hyper Backup: `.hbk` files, timestamp directories, metadata files
   - restic: `config`, `data/`, `index/`, `keys/`, `snapshots/` directories
   - borg: single repository directory with `config`, `data/`, `hints/` structure
   - tar.gz.gpg: `.tar.gz.gpg` or `.tgz.gpg` file extensions
2. Document confirmed format in drill report
3. Install appropriate decrypt/extract tooling:
   - Hyper Backup: Synology Hyper Backup Explorer (Linux version or Windows/Wine)
   - restic: `restic` binary (available in most package managers)
   - borg: `borgbackup` package
   - tar.gz.gpg: `gpg` (already installed on most systems)
4. Retrieve encryption key from Bitwarden (document exact item name/field)
5. Execute decrypt/extract process:
   - Hyper Backup Explorer: GUI workflow (document with screenshots)
   - restic: `restic -r <repo> restore latest --target <path>`
   - borg: `borg extract <repo>::<archive>`
   - tar.gz.gpg: `gpg -d backup.tar.gz.gpg | tar -xzf -`
6. Verify extraction completed without errors
7. Confirm files are accessible on local filesystem

**Validation**: Extracted files exist in expected directory structure, no decrypt errors, sample file can be opened

**Stop Point**: If decryption fails, STOP and verify encryption key correctness (test break-glass procedure if needed)

---

### Phase D: Integrity Verification

**Goal**: Validate restored data is complete and uncorrupted

**Steps**:
1. Write `scripts/dr/verify_restore.sh` to count files and perform hash checks
2. Count total files in restored directory tree
3. Compare file count to baseline (if known) or document count for future drills
4. Select sample files for hash verification:
   - Random selection: 1% of total files (minimum 5 files)
   - Critical files: Known important files (e.g., database dumps, specific photos)
5. Calculate SHA256 hashes of sample files
6. Compare hashes to known-good values (if available) or document for future comparison
7. Manually open and inspect at least one file per category:
   - Photo: Open in image viewer, confirm viewable
   - Document: Open in text editor/PDF viewer, confirm readable
   - Database: Inspect file structure (SQLite: `.schema`, PostgreSQL dump: `head -n 50`)
8. Generate verification report with file counts, hash results, manual inspection outcomes

**Validation**: File counts are reasonable, hash checks pass (or baseline established), manual inspection confirms data usability

**Stop Point**: If verification reveals corruption or significant data loss, STOP and investigate backup integrity issues

---

### Phase E: Drill Report & Documentation

**Goal**: Document drill execution results, timing, costs, and lessons learned for future reference

**Steps**:
1. Create `docs/runbooks/disaster-recovery-drill.md` with comprehensive instructions
2. Include runbook sections:
   - Overview and purpose
   - Prerequisites (tools, credentials from Bitwarden)
   - Break-glass procedures (detailed multi-tier approach)
   - Phase-by-phase execution steps
   - Troubleshooting common issues
   - Drill report template
3. Complete drill report capturing:
   - Execution date and duration (start to finish)
   - Data volume downloaded (GB)
   - Download bandwidth and timing
   - Hetzner egress costs (if any)
   - Success/failure outcomes by phase
   - Issues encountered and resolutions
   - Lessons learned and runbook improvements needed
4. Create sample drill report in `docs/runbooks/sample-drill-report.md`
5. Update repository README.md to reference disaster recovery documentation
6. Optional: Add Taskfile entries for common drill commands

**Validation**: Runbook is complete and readable, drill report captures all required metrics, documentation is accessible to non-experts

**Completion Criteria**: Drill report shows successful completion of all phases A-D, or documents specific failure point with troubleshooting path

---

## Infrastructure Design

### Directory Structure

```
homelab-proxmox/
├── scripts/
│   └── dr/                          # Disaster recovery scripts
│       ├── hetzner_list.sh          # List Hetzner S3 bucket contents
│       ├── hetzner_download.sh      # Download backup from Hetzner
│       ├── verify_restore.sh        # Verify restored backup integrity
│       ├── rclone.conf.example      # Template rclone config (placeholders)
│       ├── .env.example             # Template environment variables
│       └── README.md                # Script usage documentation
├── docs/
│   └── runbooks/
│       ├── disaster-recovery-drill.md       # Human-readable drill runbook
│       └── sample-drill-report.md           # Example completed drill report
└── specs/
    └── 012-disaster-recovery-drill/
        ├── spec.md                   # This specification
        ├── plan.md                   # This implementation plan
        └── tasks.md                  # Detailed task breakdown
```

### rclone Configuration Template

File: `scripts/dr/rclone.conf.example`

```ini
[hetzner-backup]
type = s3
provider = Other
env_auth = false
access_key_id = YOUR_ACCESS_KEY_ID_FROM_BITWARDEN
secret_access_key = YOUR_SECRET_KEY_FROM_BITWARDEN
endpoint = https://fsn1.your-objectstorage.com
acl = private
```

**Usage**:
1. Copy `rclone.conf.example` to `~/.config/rclone/rclone.conf` (or `scripts/dr/rclone.conf`)
2. Replace placeholder values with credentials from Bitwarden
3. Ensure file is .gitignored (covered by `scripts/dr/*.conf` pattern)

---

### Environment Variables Template

File: `scripts/dr/.env.example`

```bash
# Hetzner Object Storage Configuration
# Copy this file to .env and populate with actual values from Bitwarden

HETZNER_S3_ENDPOINT="https://fsn1.your-objectstorage.com"
HETZNER_S3_BUCKET="homelab-backup"
HETZNER_S3_ACCESS_KEY="YOUR_ACCESS_KEY_FROM_BITWARDEN"
HETZNER_S3_SECRET_KEY="YOUR_SECRET_KEY_FROM_BITWARDEN"

# Backup Encryption
BACKUP_ENCRYPTION_KEY="YOUR_ENCRYPTION_KEY_FROM_BITWARDEN"

# rclone Configuration
RCLONE_CONFIG_PATH="${HOME}/.config/rclone/rclone.conf"
RCLONE_REMOTE_NAME="hetzner-backup"

# Download Configuration
DOWNLOAD_TARGET_DIR="${HOME}/dr-restore"
DOWNLOAD_DRY_RUN="true"  # Set to false for actual downloads
```

**Usage**:
```bash
# Source environment variables before running scripts
source scripts/dr/.env

# Or export inline
export HETZNER_S3_ENDPOINT="..." && ./scripts/dr/hetzner_list.sh
```

---

### Script: hetzner_list.sh

```bash
#!/usr/bin/env bash
set -euo pipefail

# List Hetzner Object Storage bucket contents
# Usage: ./hetzner_list.sh [path]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Load environment variables if .env exists
if [ -f "${SCRIPT_DIR}/.env" ]; then
  source "${SCRIPT_DIR}/.env"
fi

# Validate required variables
: "${RCLONE_REMOTE_NAME:?Environment variable RCLONE_REMOTE_NAME is required}"
: "${HETZNER_S3_BUCKET:?Environment variable HETZNER_S3_BUCKET is required}"

# Path within bucket (optional, defaults to root)
BUCKET_PATH="${1:-}"

echo "Listing contents of ${RCLONE_REMOTE_NAME}:${HETZNER_S3_BUCKET}/${BUCKET_PATH}"

# Execute rclone list
rclone ls "${RCLONE_REMOTE_NAME}:${HETZNER_S3_BUCKET}/${BUCKET_PATH}" --max-depth 2

echo ""
echo "List complete. If authentication failed, check credentials in Bitwarden."
```

---

### Script: hetzner_download.sh

```bash
#!/usr/bin/env bash
set -euo pipefail

# Download backup from Hetzner Object Storage
# Usage: ./hetzner_download.sh <source_path> [target_dir]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Load environment variables if .env exists
if [ -f "${SCRIPT_DIR}/.env" ]; then
  source "${SCRIPT_DIR}/.env"
fi

# Validate required variables
: "${RCLONE_REMOTE_NAME:?Environment variable RCLONE_REMOTE_NAME is required}"
: "${HETZNER_S3_BUCKET:?Environment variable HETZNER_S3_BUCKET is required}"
: "${DOWNLOAD_TARGET_DIR:?Environment variable DOWNLOAD_TARGET_DIR is required}"

# Arguments
SOURCE_PATH="${1:?Usage: $0 <source_path> [target_dir]}"
TARGET_DIR="${2:-${DOWNLOAD_TARGET_DIR}}"

# Dry-run mode (default true for safety)
DRY_RUN="${DOWNLOAD_DRY_RUN:-true}"

# Create target directory
mkdir -p "${TARGET_DIR}"

echo "Downloading from ${RCLONE_REMOTE_NAME}:${HETZNER_S3_BUCKET}/${SOURCE_PATH}"
echo "Target directory: ${TARGET_DIR}"
echo "Dry-run mode: ${DRY_RUN}"

# Build rclone command
RCLONE_CMD="rclone copy"
RCLONE_CMD+=" ${RCLONE_REMOTE_NAME}:${HETZNER_S3_BUCKET}/${SOURCE_PATH}"
RCLONE_CMD+=" ${TARGET_DIR}"
RCLONE_CMD+=" --progress"
RCLONE_CMD+=" --stats 10s"
RCLONE_CMD+=" --transfers 4"

# Add dry-run flag if enabled
if [ "${DRY_RUN}" = "true" ]; then
  RCLONE_CMD+=" --dry-run"
  echo ""
  echo "DRY RUN MODE: No files will be downloaded. Set DOWNLOAD_DRY_RUN=false to execute."
fi

# Execute download
echo ""
echo "Executing: ${RCLONE_CMD}"
echo ""
eval "${RCLONE_CMD}"

echo ""
echo "Download complete. Check ${TARGET_DIR} for files."
```

---

### Script: verify_restore.sh

```bash
#!/usr/bin/env bash
set -euo pipefail

# Verify restored backup integrity
# Usage: ./verify_restore.sh <restore_path>

RESTORE_PATH="${1:?Usage: $0 <restore_path>}"

if [ ! -d "${RESTORE_PATH}" ]; then
  echo "Error: Restore path does not exist: ${RESTORE_PATH}"
  exit 1
fi

echo "Verifying restore integrity at ${RESTORE_PATH}"
echo ""

# Count total files
echo "Counting files..."
FILE_COUNT=$(find "${RESTORE_PATH}" -type f | wc -l)
echo "Total files: ${FILE_COUNT}"
echo ""

# Sample hash verification (5 random files or 1% of total, whichever is greater)
SAMPLE_SIZE=$(( FILE_COUNT / 100 > 5 ? FILE_COUNT / 100 : 5 ))
echo "Sampling ${SAMPLE_SIZE} files for hash verification..."
echo ""

# Generate random sample
find "${RESTORE_PATH}" -type f | shuf -n "${SAMPLE_SIZE}" | while read -r file; do
  HASH=$(sha256sum "${file}" | awk '{print $1}')
  echo "${file}: ${HASH}"
done

echo ""
echo "Verification complete."
echo "Manual inspection: Open sample files to confirm data is readable."
echo ""
echo "NEXT STEPS:"
echo "1. Open a photo file in image viewer"
echo "2. Open a document in text editor"
echo "3. Inspect database dump structure (if applicable)"
echo "4. Document results in drill report"
```

---

## Taskfile Integration (Optional)

If `Taskfile.yml` exists in repository, add these tasks:

```yaml
version: '3'

tasks:
  dr:list:
    desc: List Hetzner backup bucket contents
    cmds:
      - ./scripts/dr/hetzner_list.sh

  dr:download:
    desc: Download backup from Hetzner (dry-run by default)
    cmds:
      - ./scripts/dr/hetzner_download.sh {{.CLI_ARGS}}

  dr:download:small:
    desc: Download small test file for connectivity validation
    cmds:
      - DOWNLOAD_DRY_RUN=false ./scripts/dr/hetzner_download.sh "test-file.txt" ~/dr-restore/test

  dr:verify:
    desc: Verify restored backup integrity
    cmds:
      - ./scripts/dr/verify_restore.sh {{.PATH | default "~/dr-restore"}}

  dr:report:
    desc: Display drill report template
    cmds:
      - cat docs/runbooks/sample-drill-report.md
```

**Usage**:
```bash
task dr:list                              # List bucket contents
task dr:download -- "backup/2025-12"      # Dry-run download
task dr:download:small                    # Download small test file
task dr:verify PATH=~/dr-restore          # Verify restored files
task dr:report                            # Show drill report template
```

---

## Drill Execution Timeline

**Estimated Total Time**: 2-4 hours (depends on backup size and download bandwidth)

| Phase | Tasks | Estimated Time |
|-------|-------|----------------|
| **Phase A: Access Verification** | Install rclone, configure credentials, list bucket | 20-30 minutes |
| **Phase B: Small File Test** | Download small file, verify integrity | 10-15 minutes |
| **STOP POINT** | Review small download success | 5 minutes |
| **Phase B: Full Download** | Download full backup (varies by size/bandwidth) | 30 minutes - 2 hours |
| **Phase C: Format Confirmation** | Examine backup structure, determine format | 10-15 minutes |
| **Phase C: Decrypt/Extract** | Install tooling, decrypt, extract files | 30-60 minutes |
| **STOP POINT** | Review extraction success | 5 minutes |
| **Phase D: Verification** | Count files, hash checks, manual inspection | 15-30 minutes |
| **Phase E: Documentation** | Complete drill report, update runbook | 20-30 minutes |

**Critical Path**: Download bandwidth is primary bottleneck; ensure sufficient time allocated for full backup download.

---

## Risk Mitigation

### Risk: Hetzner S3 credentials expired or invalid
- **Mitigation**: Phase A stop point catches this early; runbook documents credential renewal process
- **Recovery**: Regenerate credentials in Hetzner console, update Bitwarden, re-run Phase A

### Risk: Backup format is not Hyper Backup (assumption incorrect)
- **Mitigation**: Decision checkpoint in Phase C confirms format before tooling investment
- **Recovery**: Document actual format in drill report, research appropriate tooling, update runbook

### Risk: Encryption key in Bitwarden is incorrect/outdated
- **Mitigation**: Break-glass procedure provides alternative key sources
- **Recovery**: Test break-glass procedure, rotate encryption keys if compromised, update all storage locations

### Risk: Download interrupted due to network issues
- **Mitigation**: Use rclone with resume support (built-in)
- **Recovery**: Re-run download script; rclone will resume from last checkpoint

### Risk: Restored data is corrupted or incomplete
- **Mitigation**: Phase D verification catches corruption before declaring drill success
- **Recovery**: Investigate backup integrity at source, test backup creation process, review Synology backup logs

### Risk: Insufficient local disk space for full restore
- **Mitigation**: Check available disk space before Phase B full download
- **Recovery**: Download to external drive, use larger VM instance, or restore subset of backup

---

## Success Metrics

- **Drill Completion**: All phases A-E complete without critical failures
- **Documentation Quality**: Runbook is clear enough for non-expert to execute drill independently
- **Recovery Time Objective (RTO)**: Full drill completes in <4 hours (target baseline)
- **Credential Validity**: Hetzner S3 credentials and encryption key successfully retrieved from Bitwarden
- **Data Integrity**: Sample file hash checks pass, manual inspection confirms data usability
- **Break-Glass Validation**: Alternative key retrieval documented and tested (at least one method)
- **Repeatability**: Drill can be re-executed quarterly with consistent results

---

## Next Steps After Drill

1. **Rotate credentials**: If drill exposed credentials (e.g., screen recording), rotate immediately
2. **Update break-glass storage**: Ensure all three break-glass methods are current
3. **Schedule next drill**: Quarterly execution (March, June, September, December)
4. **Improve runbook**: Incorporate lessons learned from this drill
5. **Automate reporting**: Consider scripted drill report generation for future drills
6. **Test alternative scenarios**: Restore from different backup date, restore to different machine type
7. **Expand scope**: Validate restoration of additional services beyond data recovery
