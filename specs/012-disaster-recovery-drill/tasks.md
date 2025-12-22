# Implementation Tasks: Disaster Recovery Drill

**Feature**: `012-disaster-recovery-drill`  
**Created**: December 21, 2025  
**Updated**: December 21, 2025 (clarified)  
**Total Estimated Tasks**: 44

## Implementation Approach

**Key Clarifications** (Session 2025-12-21):
- **Data Scope**: Focus on Immich photos only (1.73 TB, 73,650 files)
- **Hetzner Config**: Bucket `synbackup`, path `DiskStation413j_1.hbk`, endpoint `nbg1.your-objectstorage.com`
- **Format Confirmed**: Synology Hyper Backup (Config, Control, Guard, Pool folders)
- **Test File**: `_Syno_TaskConfig` (1.63 KB) for connectivity validation
- **Download Strategy**: Metadata + one Pool chunk (~10-50 GB sample) using selective restore
- **Break-Glass**: Documented procedures, but Bitwarden-only for initial drill
- **Manual-first approach**: Scripts automate repeatable steps, drill is human-executed
- **Stop points mandatory**: Do NOT proceed to next phase if previous phase fails
- **Drill report is deliverable**: Document timing, costs, success/failure, lessons learned

---

## Phase A: Hetzner Access Verification (7 tasks)

**Goal**: Confirm Hetzner S3 credentials work and Hyper Backup at synbackup/DiskStation413j_1.hbk is accessible

- [ ] **T001**: Add .gitignore entries for DR scripts directory
  - **Files**: `.gitignore`
  - **Details**: 
    ```
    # Disaster Recovery drill files (local only)
    scripts/dr/rclone.conf
    scripts/dr/*.env
    scripts/dr/drill-reports/
    ```
  - **Validation**: Git status should not show sensitive files even if created

- [ ] **T002**: Create scripts/dr/ directory structure
  - **Files**: `scripts/dr/`
  - **Command**: `mkdir -p scripts/dr`
  - **Validation**: Directory exists and is empty

- [ ] **T003**: Create rclone configuration template
  - **Files**: `scripts/dr/rclone.conf.example`
  - **Details**: Template with placeholders for Hetzner S3 credentials, endpoint `nbg1.your-objectstorage.com`, bucket `synbackup`
  - **Validation**: File contains [hetzner-backup] remote configuration with type=s3, provider=Other

- [ ] **T004**: Create environment variables template
  - **Files**: `scripts/dr/.env.example`
  - **Details**: Template with placeholders: HETZNER_S3_ENDPOINT=nbg1.your-objectstorage.com, HETZNER_S3_BUCKET=synbackup, BACKUP_PATH=DiskStation413j_1.hbk
  - **Validation**: File documents all environment variables with correct bucket/path values

- [ ] **T005**: Write hetzner_list.sh script
  - **Files**: `scripts/dr/hetzner_list.sh`
  - **Details**: 
    - Accept optional path argument (default: bucket root)
    - Load env vars from .env if present
    - Validate required variables (RCLONE_REMOTE_NAME, HETZNER_S3_BUCKET)
    - Execute `rclone ls` with max-depth limit
    - Provide clear error messages if authentication fails
  - **Validation**: Script runs with --help or dry-run mode without credentials

- [ ] **T006**: Create initial runbook with prerequisites and Bitwarden instructions
  - **Files**: `docs/runbooks/disaster-recovery-drill.md` (create initial version)
  - **Details**: 
    - Overview section explaining drill purpose (prove Immich photo recovery from Hetzner)
    - Prerequisites: rclone installation (Linux: apt/dnf, macOS: brew, Windows: choco/scoop)
    - Bitwarden credentials section with placeholder "[BITWARDEN_ITEM_NAME]" for Hetzner S3 access
    - Disk space requirement: ~100-150 GB for metadata + sample chunk + extraction
  - **Validation**: Runbook has clear structure, installation commands copy-pasteable, Bitwarden retrieval documented

- [ ] **T007**: Execute bucket listing to confirm access
  - **Manual Task**: Human execution during drill
  - **Details**:
    1. Retrieve Hetzner S3 credentials from Bitwarden (item: "[BITWARDEN_ITEM_NAME]")
    2. Create `scripts/dr/.env` with actual values (gitignored)
    3. Run `./scripts/dr/hetzner_list.sh DiskStation413j_1.hbk`
    4. Confirm Hyper Backup structure visible: Config/, Control/, Guard/, Pool/, _Syno_TaskConfig, etc.
  - **Validation**: Script outputs show DiskStation413j_1.hbk folder with Hyper Backup structure, no auth errors
  - **⚠️ STOP POINT**: If bucket listing fails, STOP and troubleshoot before Phase B. Verify:
    - Credentials from Bitwarden are current
    - Endpoint nbg1.your-objectstorage.com is reachable
    - Bucket "synbackup" exists and is accessible
    - Path DiskStation413j_1.hbk contains expected folders

---

## Phase B: Download Drill Payload (10 tasks)

**Goal**: Download _Syno_TaskConfig (1.63 KB) for connectivity test, then metadata + one Pool chunk (~10-50 GB sample for selective restore)
- [ ] **T009**: Write hetzner_download.sh script
  - **Files**: `scripts/dr/hetzner_download.sh`
  - **Details**:
    - Accept source path and optional target directory arguments
    - Support dry-run mode (default: true for safety)
    - Load env vars from .env if present
    - Validate required variables
    - Create target directory if not exists
    - Execute `rclone copy` with progress, stats, and resume support
    - Provide clear output indicating dry-run vs actual download
  - **Validation**: Script runs in dry-run mode without modifying filesystem

- [ ] **T010**: Add download script usage documentation
  - **Files**: `scripts/dr/README.md`
  - **Details**: Document usage, arguments, environment variables, examples for all three scripts
  - **Validation**: README is clear and includes copy-pasteable examples

- [ ] **T011**: Update runbook with download instructions
  - **Files**: `docs/runbooks/disaster-recovery-drill.md`
  - **Details**: Add Phase B section with step-by-step download instructions, including dry-run first, then actual download
  - **Validation**: Runbook section is complete and matches script capabilities

- [ ] **T012**: Identify small test file from bucket listing
  - **Manual TasExecute download script in dry-run mode for _Syno_TaskConfig
  - **Manual Task**: Human execution during drill
  - **Command**: `DOWNLOAD_DRY_RUN=true ./scripts/dr/hetzner_download.sh "DiskStation413j_1.hbk/_Syno_TaskConfig" ~/dr-restore/test`
  - **Validation**: Script shows _Syno_TaskConfig (1.63 KB) would be downloaded

- [ ] **T013**: Execute download for _Syno_TaskConfig (actual 1.63 KB download)
  - **Manual Task**: Human execution during drill
  - **Command**: `DOWNLOAD_DRY_RUN=false ./scripts/dr/hetzner_download.sh "DiskStation413j_1.hbk/_Syno_TaskConfig" ~/dr-restore/test`
  - **Details**: Record start time, download duration, confirm file size is 1.63 KB
  - **Validation**: File downloaded successfully, size matches 1.63 KB
  - **⚠️ STOP POINT**: If _Syno_TaskConfig download fails, STOP before metadata download. Verify:
    - Network connection stable
    - Disk space available (~100-150 GB needed)
    - rclone transfer completed without errors
    - File permissions allow writing to ~/dr-restore/
- [ ] **T016**: Estimate full backup size and download time
  - **Manual Task**: Human calculation during drill
  - **Details**:
    - Review bucket listing (T008) and sum file sizes
    - Calculate estimated download time: (total bytes / small file bytes) * small file download time
    - Estimate Hetzner egress costs (if applicable, check Hetzner pricing for region)
  - **Validation**: Estimates documented in drill notes

- [ ] **T017**: Execute download script in dry-run mode for full backup
  - **Manual Task**: Human execution during drill
  - **Command**: `DOWNLOAD_DRY_RUN=true ./scripts/dr/hetzner_download.sh "<backup-path>" ~/dr-restore/full`
  - **Validation**: Script shows full list of files to be downloaded

- [ ] **T014**: Execute download for metadata folders (Config, Control, Guard)
  - **Manual Task**: Human execution during drill
  - **Command**: `DOWNLOAD_DRY_RUN=false ./scripts/dr/hetzner_download.sh "DiskStation413j_1.hbk/Config" ~/dr-restore/metadata/`
  - **Details**: Repeat for Control/ and Guard/ folders, record download time for each
  - **Validation**: Three metadata folders downloaded successfully

- [ ] **T015**: Identify one Pool chunk file for sample download
  - **Manual Task**: Human inspection during drill
  - **Details**: 
    - List Pool/ folder contents: `./scripts/dr/hetzner_list.sh DiskStation413j_1.hbk/Pool`
    - Select one chunk file (typical size 100 MB - 50 GB depending on Hyper Backup chunking)
    - Document selected chunk name in drill notes
  - **Validation**: One Pool chunk identified for download

- [ ] **T016**: Execute download for one Pool chunk (sample data)
  - **Manual Task**: Human execution during drill
  - **Command**: `DOWNLOAD_DRY_RUN=false ./scripts/dr/hetzner_download.sh "DiskStation413j_1.hbk/Pool/[CHUNK_NAME]" ~/dr-restore/sample-data/`
  - **Details**: Monitor progress, record start/end time, bandwidth usage
  - **Validation**: Pool chunk downloaded successfully

- [ ] **T017**: Document download metrics
  - **Manual Task**: Human documentation during drill
  - **Details**: Record in drill notes:
    - _Syno_TaskConfig: 1.63 KB, [duration], [bandwidth]
    - Metadata folders: [size], [duration], [bandwidth]
    - Pool chunk: [size], [duration], [bandwidth]
    - Total downloaded: [GB]
    - Estimated Hetzner egress cost: $[amount] (if applicable)
  - **Validation**: All download metrics documented with timestampsrity.N`, `README`
    - tar.gz.gpg: Files with `.tar.gz.gpg`, `.tgz.gpg`, `.tar.bz2.gpg` extensions
    - Custom: Other patterns (document structure)
  - **Validation**: Format positively identified and documented in drill notes
  - **⚠️ DECISION CHECKPOINT**: Do NOT proceed until format is confirmed. If format is unknown, STOP and research before attempting decrypt. Document format in drill report as this may affect future drill procedures.

- [ ] **T022**: Update runbook with format confirmation instructions
  - **Files**: `docs/runbooks/disaster-recovery-drill.md`
  - **Details**: Add decision checkpoint section documenting how to identify each format, with examples
  - **ValidaDecrypt & Extract Immich Photos (11 tasks)

**Goal**: Use Hyper Backup Explorer to decrypt and selectively restore sample Immich photos

- [ ] **T018**: Validate Hyper Backup structure in downloaded files
  - **Manual Task**: Human inspection during drill
  - **Details**: Confirm folders present: Config/, Control/, Guard/, Pool/[chunk], _Syno_TaskConfig, etc.
  - **Validation**: Hyper Backup structure confirmed (format already validated from Phase A bucket listing)
  - **⚠️ CONFIRMATION**: Hyper Backup format confirmed, proceeding with Hyper Backup Explorer installation
  - **Note**: Skip if format is not Hyper Backup

- [ ] **T025**: Install decrypt tooling (restic path)
  - **Manual Task**: Human execution during drill (if format = restic)
  - **Command**: 
    - Linux: `apt install restic` or `dnf install restic`
    - macO19**: Update runbook with Hyper Backup Explorer installation
  - **Files**: `docs/runbooks/disaster-recovery-drill.md`
  - **Details**: Add Phase C section with platform-specific installation:
    - Linux: Download from Synology (or Wine for Windows version)
    - macOS: Download Hyper Backup Explorer for Mac from Synology
    - Windows: Download installer from Synology downloads page
  - **Validation**: Installation instructions with download URLs documented

- [ ] **T020**: Install Hyper Backup Explorer on drill machine
  - **Manual Task**: Human execution during drill
  - **Platform**: Follow runbook instructions for OS (Linux/macOS/Windows)
  - **Validation**: Hyper Backup Explorer launches successfully, version displayed in About dialory (e.g., ~/dr-restore/extracted)
    6. Monitor extraction progress
  - **Validation**: Extraction completes without errors, files accessible in target directory
  - **Note**: Skip if format is not Hyper Backup

- [ ] **T030**: Execute decrypt/extract (restic path)
  - **Manual Task**: Human execution during drill (if format = restic)
  - **Command**: `restic -r ~/dr-restore/full restore latest --target ~/dr-restore/extracted`
  - **Details**: Enter encryption password when prompted (from T028)
  - **Validation**: `restic restore` exits 0, files present in target directory
  - **Note**: Skip if format is not restic

- [ ] **T031**: Execute decrypt/extract (borg path)
  - **Manual Task**: Human execution during drill (if format = borg)
  - **Command**: `borg extract ~/dr-restore/full::<archive-name> --target ~/dr-restore/extracted`
  - **Details**: 
    - List archives first: `borg list ~/dr-restore/full`
    - Extract latest archive
    - Enter encryption password when prompted (from T028)
  - **Validation**: `borg extract` exits 0, files present in target directory
  - **Note**: Skip if format is not borg

- [ ] **T032**: Execute decrypt/extract (tar.gz.gpg path)
  - **Manual Task**: Human execution during drill (if format = tar.gz.gpg)
  - **Command**: `gpg --decrypt ~/dr-restore/full/backup.tar.gz.gpg | tar -xzf - -C ~/dr-restore/extracted`
  - **Details**: Enter encryption password when prompted (from T028)
  - **Valid1**: Document encryption key retrieval in runbook
  - **Files**: `docs/runbooks/disaster-recovery-drill.md`
  - **Details**: Add Bitwarden encryption key section with placeholder "[BITWARDEN_ENCRYPTION_KEY_ITEM]"
  - **Validation**: Clear step-by-step instructions for key retrieval

- [ ] **T022**: Retrieve encryption key from Bitwarden
  - **Manual Task**: Human execution during drill
  - **Details**: 
    1. Open Bitwarden vault
    2. Navigate to item "[BITWARDEN_ENCRYPTION_KEY_ITEM]"
    3. Copy encryption password to secure clipboard
  - **Validation**: Encryption key retrieved and ready for Hyper Backup Explorer

- [ ] **T023**: Open backup in Hyper Backup Explorer
  - **Manual Task**: Human execution during drill
  - **Details**:
    1. Launch Hyper Backup Explorer
    2. File → Browse for Backup → Select ~/dr-restore/metadata/ (containing Config, Control, Guard folders)
    3. Enter encryption password when prompted (from T022)
    4. Wait for backup to load and display folder tree
  - **Validation**: Hyper Backup Explorer shows Immich backup folder structure, no decrypt errors

- [ ] **T024**: Navigate to Immich photos folder in backup
  - **Manual Task**: Human execution during drill
  - **Details**: In Hyper Backup Explorer, expand folder tree to locate Immich photos directory (likely /immich/library/ or /var/lib/immich/)
  - **Validation**: Immich photos folder visible with photo files listed

- [ ] **T025**: Select sample photos for extraction (10-20 photos)
  - **Manual Task**: Human execution during drill
  - **Details**: Select 10-20 photo files from different date folders to prove extraction works across backup
  - **Validation**: Sample photos selected in Hyper Backup Explorer

- [ ] **T026**: Extract sample photos to local directory
  - **Manual Task**: Human execution during drill
  - **Details**:
    1. Right-click selected photos → Restore
    2. Choose target directory: ~/dr-restore/extracted/
    3. Monitor extraction progress
    4. Record extraction time
  - **Validation**: Sample photos extracted to ~/dr-restore/extracted/, no errors displayed

- [ ] **T027**: Verify extraction completed without errors
  - **Manual Task**: Human verification during drill
  - **Details**:
    - Check Hyper Backup Explorer log for error messages
    - Verify ~/dr-restore/extracted/ contains photo files
    - Confirm file sizes are reasonable (not 0 bytes)
  - **Validation**: 10-20 photo files present in extraction directory, no errors
  - **⚠️ STOP POINT**: If decryption fails ("wrong password") or extraction shows errors, STOP and verify encryption key correctness. Do NOT proceed to verification phase until extraction succeeds.

- [ ] **T028**: Document decrypt/extract process in drill report
  - **Manual Task**: Human documentation during drill
  - **Details**: Record in drill notes:
    - Hyper Backup Explorer version used
    - Extraction time for 10-20 photos
    - Total sample photos extracted
    - Any issues encountered
  - **Validation**: Decrypt/extrac
    - Confirmmmich Photo Integrity Verification (8 tasks)

**Goal**: Validate extracted Immich photos are viewabl
- [ ] **T042**: Manually inspect sample document file
  - **Manu29**: Write verify_restore.sh script for photo validation
  - **Files**: `scripts/dr/verify_restore.sh`
  - **Details**:
    - Accept restore path as argument
    - Count total photo files (*.jpg, *.png, *.heic, *.raw)
    - Calculate SHA256 hashes for all extracted photos
    - Output verification report with file count and hashes
  - **Validation**: Script runs and outputs photo count + hashes

- [ ] **T030**: Update runbook with verification instructions
  - **Files**: `docs/runbooks/disaster-recovery-drill.md`
  - **Details**: Add Phase D section: run verify script, manual photo inspection steps
  - **Validation**: Runbook Phase D section complete

- [ ] **T031**: Execute verification script on extracted photos
  - **Manual Task**: Human execution during drill
  - **Command**: `./scripts/dr/verify_restore.sh ~/dr-restore/extracted`
  - **Validation**: Script outputs photo count and SHA256 hashes

- [ ] **T032**: Document photo count baseline
  - **Manual Task**: Human documentation during drill
  - **Details**: Record extracted photo count (10-20 photos) in drill notes as baseline for this drill
  - **Validation**: Photo count documented

- [ ] **T033**: Document sample photo hashes
  - **Manual Task**: Human documentation during drill
  - **Details**: Copy all photo SHA256 hashes from verification script to drill notes
  - **Validation**: All extracted photo hashes documented

- [ ] **T034**: Manually open and inspect 3-5 photos
  - **Manual Task**: Human verification during drill
  - **Details**:
    - Select 3-5 photos from extraction directory
    - Open each in image viewer (Preview, Photos, Windows Photo Viewer, etc.)
    - Verify images display correctly: no corruption, recognizable content, EXIF data intact
  - **Validation**: All inspected photos are viewable and appear intact

- [ ] **T035**: Check EXIF data for one photo (optional but recommended)
  - **Manual Task**: Human verification during drill
  - **Details**: Use `exiftool` or image viewer to check EXIF metadata (date, camera model, GPS if present)
  - **Validation**: EXIF data is present and appears correct (not stripped or corrupted)
  - **Note**: Skip if exiftool not available

- [ ] **T036**: Generate verification summary
  - **Manual Task**: Human documentation during drill
  - **Details**: Summarize in drill notes:
    - Total photos extracted: [10-20]
    - SHA256 hashes: [ALL DOCUMENTED]
    - Manual inspection: [PASS - 3-5 photos viewable]
    - EXIF data: [PASS/SKIP]
    - Overall assessment: SUCCESS (Immich photos recoverable from Hetzner backup)
  - **Validation**: Verification summary clear and actionable
  - **⚠️ STOP POINT**: If photos are corrupted, unreadable, or hashes suggest issues, STOP and investigate. Potential causes: wrong encryption key, backup corruption, download errors. Do NOT declare drill successful until photos are confirmed viewable.
    
    **Executed By**: [NAME]
    **Execution Date**: [YYYY-MM-DD]
    **Total Duration**: [HH:MM]
    
    ### Phase A: Access Verification
    - Status: SUCCESS / FAILURE
    - Issues: [None or description]
    
    ### Phase B: Download
    - Data volume downloaded: [GB]
    - Download time: [HH:MM]
    - Bandwidth: [MB/s average]
    - Hetzner costs: [$X.XX or N/A]
    - Status: SUCCESS / FAILURE
    - Issues: [None or description]
    37**: Finalize runbook with all phases documented
  - **Files**: `docs/runbooks/disaster-recovery-drill.md`
  - **Details**: Ensure complete structure:
    1. Overview: Prove Immich photo recovery from Hetzner (1.73 TB, selective restore of sample subset)
    2. Prerequisites: rclone, Hyper Backup Explorer, ~100-150 GB disk space
    3. Phase A: Access synbackup/DiskStation413j_1.hbk
    4. Phase B: Download _Syno_TaskConfig + metadata + one Pool chunk
    5. Phase C: Hyper Backup Explorer selective restore of 10-20 photos
    6. Phase D: Verify photos viewable
    7. Break-glass procedures (documented, not implemented in initial drill)
    8. Troubleshooting common issues
    9. Drill report template
  - **Validation**: All sections complete, runbook is self-sufficient for execution, break-glass section includes all three methods (USB drive, paper backup, trusted contact) with retrieval steps

- [ ] **T038**: Add troubleshooting section to runbook
  - **Files**: `docs/runbooks/disaster-recovery-drill.md`
  - **Details**: Document failure scenarios:
    - "S3 auth failed" → Check Bitwarden credentials, verify endpoint nbg1.your-objectstorage.com
    - "Hyper Backup won't open" → Verify all metadata folders (Config/Control/Guard) downloaded
    - "Decryption failed" → Verify encryption key from Bitwarden, test break-glass if needed
    - "Photos corrupted" → Check Pool chunk downloaded completely, re-download if needed
    - "rclone slow" → Check bandwidth, consider --transfers flag adjustment
  - **Validation**: 5+ troubleshooting scenarios with resolutionsdata) to demonstrate format
  - **_Syno_TaskConfig: [1.63 KB, duration, bandwidth]
    - Metadata folders (Config/Control/Guard): [size, duration]
    - Pool chunk: [size, duration]
    - Total downloaded: [GB]
    - Bandwidth average: [MB/s]
    - Hetzner egress cost: [$X.XX or N/A]
    - Status: SUCCESS / FAILURE
    - Issues: [None or description]
    
    ### Phase C: Decrypt & Extract
    - Backup format: Hyper Backup (confirmed)
    - Hyper Backup Explorer version: [version]
    - Photos extracted: [10-20]
    - Extraction time: [HH:MM]
    - Proof achieved: Immich photos recoverable from Hetzner without Synology/Proxmox
    - Lessons learned: [List]
    - Runbook improvements needed: [List]
    - Break-glass procedure: Documented (not tested in initial drill)
    
    ### Next Steps
    - [ ] Rotate credentials (if exposed)
    - [ ] Implement break-glass storage (future enhancement)
    - [ ] Schedule next drill (target: [YYYY-MM-DD], quarterly recommended)
    ```
  - **Validation**: Template matches clarified drill scope (Immich photos, sample restore)

- [ ] **T040**: Update repository README with DR documentation link
  - **Files**: `README.md`
  - **Details**: Add Disaster Recovery section:
    ```markdown
    ## Disaster Recovery
    
    Disaster recovery procedures for Immich photo backups stored in Hetzner Object Storage.
    
    - **Runbook**: [docs/runbooks/disaster-recovery-drill.md](docs/runbooks/disaster-recovery-drill.md)
    - **Scripts**: [scripts/dr/](scripts/dr/) (list, download, verify)
    - **Specification**: [specs/012-disaster-recovery-drill/](specs/012-disaster-recovery-drill/)
    - **Last Drill**: [View latest drill report](scripts/dr/drill-reports/)
    ```
  - **Validation**: README updated, links functional

- [ ] **T041**: Add Taskfile entries (if Taskfile.yml exists)
  - **Files**: `Taskfile.yml`
  - **Details**: Add DR tasks: `dr:list`, `dr:download`, `dr:verify`
  - **Validation**: `task --list` shows DR tasks (or skip if no Taskfile)
  - **Note**: Check if Taskfile exists first: `test -f Taskfile.yml`

- [ ] **T042**: Execute complete drill end-to-end
  - **Manual Task**: Human execution of Phases A-E
  - **Details**: Follow runbook start to finish, capture all metrics
  - **Expected Duration**: 2-4 hours (depends on download bandwidth)
  - **Validation**: All phases complete or failure point clearly documented

- [ ] **T043**: Complete drill report with actual execution data
  - **Manual Task**: Fill out drill report template
  - **Details**: Document actual results from T042 execution
  - **Files**: Save as `scripts/dr/drill-reports/YYYY-MM-DD-drill-report.md`
  - **Validation**: Report captures all metrics, success/failure outcome clear

- [ ] **T044**: Update runbook based on lessons learned
  - **Files**: `docs/runbooks/disaster-recovery-drill.md`
  - **Details**: Review T043 report, identify and incorporate improvements (clearer instructions, missing troubleshooting, updated timing estimates)
  - **Validation**: At least 2 improvements applied to runbook from actual drill experienceessful execution

- [ ] **T063**: Merge to main after PR review
  - **Validation**: Branch merged, disaster recovery capability is now documented in main branch

---

## Task Dependencies

```
T001 (gitignore) → T002 (create dir) → T003-T007 (templates/scripts)
T008 (list bucket) [STOP POINT]
  ↓
T009-T015 (small download test) [STOP POINT]
  ↓
T016-T020 (full download)
  ↓
T021 (format confirmation) [DECISION CHECKPOINT]
  ↓
T022-T034 (decrypt/extract) [STOP POINT]
  ↓
T035-T044 (verification) [STOP POINT]
  ↓
T045-T058 (documentation/drill execution)
  ↓
T059-T063 (commit/merge)
```

---

## Notes

- **Stop points are mandatory**: Do NOT skip stop points. Each stop point protects against wasted effort if previous phase failed.
- **Decision checkpoint**: T021 is critical - do not assume backup format without confirmation.
- **Manual tasks are majorit (Git Workflow)

- [ ] **T045**: Commit runbook and scripts
  - **Files**: `docs/runbooks/disaster-recovery-drill.md`, `scripts/dr/*`
  - **Command**: `git add docs/runbooks/ scripts/dr/ .gitignore README.md && git commit -m "feat(dr): disaster recovery runbook and scripts for Immich backup"`
  - **Validation**: Runbook, scripts, .gitignore, README committed (credentials still gitignored)

- [ ] **T046**: Commit drill report after execution
  - **Files**: `scripts/dr/drill-reports/YYYY-MM-DD-drill-report.md`
  - **Command**: `git add scripts/dr/drill-reports/ && git commit -m "docs(dr): drill report YYYY-MM-DD - Immich photo recovery SUCCESS"`
  - **Validation**: Drill report committed showing successful Immich recovery proof

- [ ] **T047**: Push feature branch and create PR
  - **Command**: `git push origin 012-disaster-recovery-drill`
  - **Details**: Create PR with title "Feature 012: Disaster Recovery Drill" and link to drill report in description
  - **Validation**: PR created, drill report demonstrates end-to-end Immich photo recovery

- [ ] **T048**: Merge to main after review
  - **Validation**: Branch merged, disaster recovery capability documented in main