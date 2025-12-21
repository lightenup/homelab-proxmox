# Implementation Tasks: Disaster Recovery Drill

**Feature**: `012-disaster-recovery-drill`  
**Created**: December 21, 2025  
**Updated**: December 21, 2025  
**Total Estimated Tasks**: 48

## Implementation Approach

**Key Clarifications**:
- Manual-first approach: Scripts automate repeatable steps, but drill is human-executed
- Stop points are mandatory: Do NOT proceed to next phase if previous phase fails
- No credentials committed: All secrets retrieved from Bitwarden during drill execution
- Decision checkpoint required: Confirm backup format before investing in decrypt tooling
- Drill report is deliverable: Document timing, costs, success/failure, lessons learned

---

## Phase A: Hetzner Access Verification (8 tasks)

**Goal**: Confirm Hetzner Object Storage credentials work and backups are accessible from independent machine

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
  - **Details**: Template with placeholders for access key, secret key, endpoint URL
  - **Validation**: File contains all required rclone S3 configuration parameters with placeholder values

- [ ] **T004**: Create environment variables template
  - **Files**: `scripts/dr/.env.example`
  - **Details**: Template with placeholders for Hetzner credentials, encryption key, paths
  - **Validation**: File documents all environment variables used by scripts

- [ ] **T005**: Write hetzner_list.sh script
  - **Files**: `scripts/dr/hetzner_list.sh`
  - **Details**: 
    - Accept optional path argument (default: bucket root)
    - Load env vars from .env if present
    - Validate required variables (RCLONE_REMOTE_NAME, HETZNER_S3_BUCKET)
    - Execute `rclone ls` with max-depth limit
    - Provide clear error messages if authentication fails
  - **Validation**: Script runs with --help or dry-run mode without credentials

- [ ] **T006**: Document Bitwarden credential retrieval in runbook (placeholder)
  - **Files**: `docs/runbooks/disaster-recovery-drill.md` (create initial version)
  - **Details**: Section describing Bitwarden item names/paths for Hetzner S3 credentials (actual paths NOT committed, use placeholders like "[BITWARDEN_ITEM_NAME]")
  - **Validation**: Runbook has clear instructions for retrieving each credential from Bitwarden

- [ ] **T007**: Install rclone on test machine (documented in runbook)
  - **Files**: `docs/runbooks/disaster-recovery-drill.md`
  - **Details**: Add installation instructions for Linux (apt/dnf), macOS (brew), Windows (choco/scoop)
  - **Validation**: Installation commands are copy-pasteable

- [ ] **T008**: Execute bucket listing to confirm access
  - **Manual Task**: Human execution during drill
  - **Details**:
    1. Retrieve Hetzner S3 credentials from Bitwarden
    2. Create `scripts/dr/.env` with actual values (gitignored)
    3. Run `./scripts/dr/hetzner_list.sh`
    4. Confirm backup objects are visible in output
  - **Validation**: Script outputs list of backup files/directories without authentication errors
  - **⚠️ STOP POINT**: If bucket listing fails, STOP and troubleshoot credentials before proceeding to Phase B. Verify:
    - Credentials are correct (check Bitwarden)
    - Endpoint URL is correct for Hetzner region
    - Bucket name matches actual bucket
    - S3 API access is enabled in Hetzner console

---

## Phase B: Download Drill Payload (12 tasks)

**Goal**: Download backup data to local machine, starting with small test file

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
  - **Manual Task**: Human inspection during drill
  - **Details**: Review output from T008, identify file <100MB for connectivity test (e.g., config file, small backup, metadata file)
  - **Validation**: Test file identified and path documented in drill notes

- [ ] **T013**: Execute download script in dry-run mode for small file
  - **Manual Task**: Human execution during drill
  - **Command**: `DOWNLOAD_DRY_RUN=true ./scripts/dr/hetzner_download.sh "<small-file-path>" ~/dr-restore/test`
  - **Validation**: Script shows what would be downloaded without actually downloading

- [ ] **T014**: Execute download script for small test file (actual download)
  - **Manual Task**: Human execution during drill
  - **Command**: `DOWNLOAD_DRY_RUN=false ./scripts/dr/hetzner_download.sh "<small-file-path>" ~/dr-restore/test`
  - **Validation**: File downloaded to target directory, script reports success

- [ ] **T015**: Verify small file integrity
  - **Manual Task**: Human verification during drill
  - **Details**:
    - Check file size matches expected (compare with bucket listing or rclone output)
    - If checksum available, calculate `sha256sum` and compare
    - Attempt to open file (if format is readable, e.g., text, image)
  - **Validation**: File size matches, checksum passes (if available), file is readable
  - **⚠️ STOP POINT**: If small file download fails or integrity check fails, STOP and troubleshoot network/credentials before attempting full backup download. Verify:
    - Network connection is stable
    - Sufficient disk space for download
    - File permissions allow writing to target directory
    - rclone transfer completed without errors

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

- [ ] **T018**: Execute download script for full backup (actual download)
  - **Manual Task**: Human execution during drill (longest task)
  - **Command**: `DOWNLOAD_DRY_RUN=false ./scripts/dr/hetzner_download.sh "<backup-path>" ~/dr-restore/full`
  - **Details**: Monitor progress, note start time, track bandwidth usage
  - **Validation**: All files downloaded, rclone reports success, no transfer errors

- [ ] **T019**: Document download metrics
  - **Manual Task**: Human documentation during drill
  - **Details**: Record in drill notes:
    - Total data downloaded (GB)
    - Download start time and end time (duration)
    - Average bandwidth (MB/s)
    - Any Hetzner egress costs incurred
  - **Validation**: Metrics documented with timestamps

- [ ] **T020**: Verify full download integrity
  - **Manual Task**: Human verification during drill
  - **Details**:
    - Verify all expected files present (compare with dry-run output)
    - Check disk usage matches expected
    - No incomplete or corrupted files (check for .rclone-tmp files indicating interrupted transfers)
  - **Validation**: File count matches expected, no transfer errors logged

---

## Phase C: Backup Format Confirmation & Decrypt (14 tasks)

**Goal**: Confirm backup format and decrypt/extract files using appropriate tooling

- [ ] **T021**: Examine backup file structure and naming
  - **Manual Task**: Human inspection during drill (DECISION CHECKPOINT)
  - **Details**: Navigate downloaded backup directory and identify format characteristics:
    - Hyper Backup: `.hbk` files, timestamp directories, `metadata`, `version` files
    - restic: `config`, `data/`, `index/`, `keys/`, `snapshots/`, `locks/` directories
    - borg: repository directory with `config`, `data/`, `hints.N`, `integrity.N`, `README`
    - tar.gz.gpg: Files with `.tar.gz.gpg`, `.tgz.gpg`, `.tar.bz2.gpg` extensions
    - Custom: Other patterns (document structure)
  - **Validation**: Format positively identified and documented in drill notes
  - **⚠️ DECISION CHECKPOINT**: Do NOT proceed until format is confirmed. If format is unknown, STOP and research before attempting decrypt. Document format in drill report as this may affect future drill procedures.

- [ ] **T022**: Update runbook with format confirmation instructions
  - **Files**: `docs/runbooks/disaster-recovery-drill.md`
  - **Details**: Add decision checkpoint section documenting how to identify each format, with examples
  - **Validation**: Runbook contains clear format identification guidance

- [ ] **T023**: Document required decrypt tooling for confirmed format
  - **Files**: `docs/runbooks/disaster-recovery-drill.md`
  - **Details**: Add installation instructions for identified format's decrypt tool (conditional based on format)
  - **Validation**: Installation instructions are platform-specific (Linux, macOS, Windows)

- [ ] **T024**: Install decrypt tooling (Hyper Backup path)
  - **Manual Task**: Human execution during drill (if format = Hyper Backup)
  - **Details**:
    - Linux: Download Hyper Backup Explorer from Synology (or use Wine for Windows version)
    - macOS: Download Hyper Backup Explorer for Mac
    - Windows: Download Hyper Backup Explorer installer
  - **Validation**: Tool installed and launches successfully
  - **Note**: Skip if format is not Hyper Backup

- [ ] **T025**: Install decrypt tooling (restic path)
  - **Manual Task**: Human execution during drill (if format = restic)
  - **Command**: 
    - Linux: `apt install restic` or `dnf install restic`
    - macOS: `brew install restic`
    - Windows: `choco install restic`
  - **Validation**: `restic version` command works
  - **Note**: Skip if format is not restic

- [ ] **T026**: Install decrypt tooling (borg path)
  - **Manual Task**: Human execution during drill (if format = borg)
  - **Command**:
    - Linux: `apt install borgbackup` or `dnf install borgbackup`
    - macOS: `brew install borgbackup`
    - Windows: WSL required, then `apt install borgbackup`
  - **Validation**: `borg --version` command works
  - **Note**: Skip if format is not borg

- [ ] **T027**: Document encryption key retrieval from Bitwarden
  - **Files**: `docs/runbooks/disaster-recovery-drill.md`
  - **Details**: Add section describing Bitwarden item name/path for backup encryption key (use placeholder, not actual path)
  - **Validation**: Instructions are clear and step-by-step

- [ ] **T028**: Retrieve encryption key from Bitwarden
  - **Manual Task**: Human execution during drill
  - **Details**: 
    1. Open Bitwarden web vault or CLI
    2. Navigate to documented item (from T027)
    3. Copy encryption key to secure clipboard or temporary file
    4. Store in environment variable for decrypt process
  - **Validation**: Encryption key retrieved and ready for use

- [ ] **T029**: Execute decrypt/extract (Hyper Backup path)
  - **Manual Task**: Human execution during drill (if format = Hyper Backup)
  - **Details**:
    1. Launch Hyper Backup Explorer
    2. Open downloaded backup location
    3. Enter encryption password when prompted (from T028)
    4. Select files/folders to extract
    5. Choose target extraction directory (e.g., ~/dr-restore/extracted)
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
  - **Validation**: `tar` exits 0, files present in target directory
  - **Note**: Skip if format is not tar.gz.gpg

- [ ] **T033**: Verify extraction completed without errors
  - **Manual Task**: Human verification during drill
  - **Details**:
    - Check decrypt tool output for error messages
    - Verify target directory is not empty
    - Check that directory structure looks reasonable (folders, files, not just metadata)
  - **Validation**: No error messages, files extracted successfully
  - **⚠️ STOP POINT**: If decryption fails with "wrong password" or similar error, STOP and verify encryption key. Test break-glass procedure if Bitwarden key is incorrect. Do NOT proceed to verification phase until decrypt succeeds.

- [ ] **T034**: Document decrypt process and tooling in drill report
  - **Manual Task**: Human documentation during drill
  - **Details**: Record in drill notes:
    - Confirmed backup format
    - Decrypt tooling used (name, version)
    - Extraction time (start to finish)
    - Any issues encountered during decrypt
  - **Validation**: Decrypt process fully documented

---

## Phase D: Integrity Verification (10 tasks)

**Goal**: Validate restored data is complete and uncorrupted

- [ ] **T035**: Write verify_restore.sh script
  - **Files**: `scripts/dr/verify_restore.sh`
  - **Details**:
    - Accept restore path as argument
    - Count total files recursively
    - Sample files for hash verification (1% or minimum 5 files)
    - Calculate SHA256 hashes for sampled files
    - Output clear verification report
  - **Validation**: Script runs with --help, dry-run works

- [ ] **T036**: Update runbook with verification instructions
  - **Files**: `docs/runbooks/disaster-recovery-drill.md`
  - **Details**: Add Phase D section with verification steps, including manual inspection guidance
  - **Validation**: Runbook section complete

- [ ] **T037**: Execute verification script
  - **Manual Task**: Human execution during drill
  - **Command**: `./scripts/dr/verify_restore.sh ~/dr-restore/extracted`
  - **Validation**: Script outputs file count and sample hashes

- [ ] **T038**: Document file count baseline
  - **Manual Task**: Human documentation during drill
  - **Details**: Record total file count in drill notes (this becomes baseline for future drills if no known-good count exists)
  - **Validation**: File count documented

- [ ] **T039**: Compare file count to baseline (if available)
  - **Manual Task**: Human comparison during drill
  - **Details**: If previous drill exists, compare file counts; significant discrepancy requires investigation
  - **Validation**: Comparison documented in drill notes (or note that this is first baseline)

- [ ] **T040**: Document sample file hashes
  - **Manual Task**: Human documentation during drill
  - **Details**: Copy sample file paths and SHA256 hashes from verification script output to drill notes
  - **Validation**: At least 5 file hashes documented

- [ ] **T041**: Manually inspect sample photo file
  - **Manual Task**: Human verification during drill
  - **Details**:
    - Select one .jpg, .png, .heic, or .raw file from extracted backup
    - Open in image viewer
    - Confirm image displays correctly (not corrupted, recognizable content)
  - **Validation**: Photo is viewable and appears intact

- [ ] **T042**: Manually inspect sample document file
  - **Manual Task**: Human verification during drill
  - **Details**:
    - Select one .pdf, .docx, .txt, or .md file from extracted backup
    - Open in appropriate viewer/editor
    - Confirm document is readable (text is not garbled, formatting reasonable)
  - **Validation**: Document is readable and appears intact

- [ ] **T043**: Manually inspect database dump (if applicable)
  - **Manual Task**: Human verification during drill
  - **Details**:
    - Locate .sql, .db, or .dump file if present
    - For SQL dump: `head -n 50` to check structure
    - For SQLite: `sqlite3 <file> ".schema"` to verify schema
  - **Validation**: Database structure appears valid (SQL statements are syntactically correct)
  - **Note**: Skip if no database backups present

- [ ] **T044**: Generate verification summary
  - **Manual Task**: Human documentation during drill
  - **Details**: Summarize verification results:
    - Total file count: [NUMBER]
    - Sample hash checks: [PASS/FAIL]
    - Manual inspection: [PASS/FAIL] (photo, document, database)
    - Overall assessment: SUCCESS or FAILURE with details
  - **Validation**: Verification summary is clear and actionable
  - **⚠️ STOP POINT**: If verification reveals significant issues (many files corrupted, hash mismatches, data unreadable), STOP and investigate backup integrity. Do NOT declare drill successful. Investigate:
    - Backup creation process on Synology
    - Storage integrity in Hetzner Object Storage
    - Encryption/decryption process
    - File transfer integrity

---

## Phase E: Drill Report & Documentation (14 tasks)

**Goal**: Document drill execution results and finalize runbook

- [ ] **T045**: Create comprehensive runbook structure
  - **Files**: `docs/runbooks/disaster-recovery-drill.md`
  - **Details**: Expand runbook with complete structure:
    1. Overview and purpose
    2. Prerequisites (tools, credentials)
    3. Phase A: Access Verification
    4. Phase B: Download
    5. Phase C: Decrypt
    6. Phase D: Verification
    7. Break-glass procedures
    8. Troubleshooting
    9. Drill report template
  - **Validation**: All sections have meaningful content (not just headers)

- [ ] **T046**: Document break-glass procedures in runbook
  - **Files**: `docs/runbooks/disaster-recovery-drill.md`
  - **Details**: Add detailed break-glass section from spec.md:
    - Primary: Encrypted USB drive (location placeholder, access method)
    - Secondary: Paper backup (location placeholder, access method)
    - Tertiary: Trusted contact (procedure for retrieval)
    - When to update break-glass credentials
  - **Validation**: Break-glass section is complete and actionable

- [ ] **T047**: Add troubleshooting section to runbook
  - **Files**: `docs/runbooks/disaster-recovery-drill.md`
  - **Details**: Document common failure scenarios and resolutions:
    - "S3 authentication failed" → Check credentials in Bitwarden, verify endpoint URL
    - "Decryption failed (wrong password)" → Test break-glass procedure
    - "Download interrupted" → Re-run with rclone resume support
    - "Verification found corruption" → Investigate backup integrity at source
  - **Validation**: At least 5 troubleshooting scenarios documented

- [ ] **T048**: Create drill report template in runbook
  - **Files**: `docs/runbooks/disaster-recovery-drill.md`
  - **Details**: Add drill report template with sections:
    ```
    ## Drill Report: [DATE]
    
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
    
    ### Phase C: Decrypt
    - Backup format confirmed: [Hyper Backup / restic / borg / tar.gz.gpg / other]
    - Decrypt tooling: [Name and version]
    - Extraction time: [HH:MM]
    - Status: SUCCESS / FAILURE
    - Issues: [None or description]
    
    ### Phase D: Verification
    - Total files: [NUMBER]
    - Sample hash checks: [X/Y passed]
    - Manual inspection: [Photo: PASS/FAIL, Document: PASS/FAIL, Database: PASS/FAIL/N/A]
    - Status: SUCCESS / FAILURE
    - Issues: [None or description]
    
    ### Overall Assessment
    - Drill outcome: SUCCESS / FAILURE
    - Lessons learned: [List]
    - Runbook improvements needed: [List]
    - Break-glass procedure tested: YES / NO
    
    ### Next Steps
    - [ ] Rotate credentials (if exposed)
    - [ ] Update break-glass storage
    - [ ] Schedule next drill (target date: [YYYY-MM-DD])
    ```
  - **Validation**: Template is comprehensive and easy to fill out

- [ ] **T049**: Create sample drill report
  - **Files**: `docs/runbooks/sample-drill-report.md`
  - **Details**: Create example filled-out drill report (fictional data) to demonstrate format
  - **Validation**: Sample report is realistic and helps understanding

- [ ] **T050**: Add prerequisites section to runbook
  - **Files**: `docs/runbooks/disaster-recovery-drill.md`
  - **Details**: Document all prerequisites:
    - Machine requirements: Linux/macOS/Windows with bash
    - Tool requirements: rclone (with version), gpg, tar, etc.
    - Credential requirements: Bitwarden access, list of items needed
    - Disk space requirements: 2-3x backup size
    - Network requirements: Stable connection, bandwidth estimate
  - **Validation**: Prerequisites are clear and complete

- [ ] **T051**: Document Bitwarden item locations in runbook
  - **Files**: `docs/runbooks/disaster-recovery-drill.md`
  - **Details**: List Bitwarden items needed (use placeholders, not actual item names):
    - Hetzner S3 Access Key ID: [BITWARDEN_ITEM: "Hetzner Object Storage"]
    - Hetzner S3 Secret Key: [BITWARDEN_ITEM: "Hetzner Object Storage"]
    - Hetzner S3 Endpoint: [BITWARDEN_ITEM: "Hetzner Object Storage" / Field: "endpoint"]
    - Backup Encryption Key: [BITWARDEN_ITEM: "Backup Encryption Key"]
  - **Validation**: All credential sources documented

- [ ] **T052**: Update repository README with DR documentation link
  - **Files**: `README.md`
  - **Details**: Add section:
    ```markdown
    ## Disaster Recovery
    
    This repository includes disaster recovery procedures for recovering encrypted backups from Hetzner Object Storage.
    
    - **Runbook**: [docs/runbooks/disaster-recovery-drill.md](docs/runbooks/disaster-recovery-drill.md)
    - **Scripts**: [scripts/dr/](scripts/dr/)
    - **Specification**: [specs/012-disaster-recovery-drill/](specs/012-disaster-recovery-drill/)
    ```
  - **Validation**: Link is present and functional

- [ ] **T053**: Add Taskfile entries (if Taskfile exists)
  - **Files**: `Taskfile.yml`
  - **Details**: Add DR tasks as specified in plan.md (dr:list, dr:download, dr:download:small, dr:verify, dr:report)
  - **Validation**: `task --list` shows new DR tasks
  - **Note**: Skip if Taskfile does not exist in repository

- [ ] **T054**: Execute complete drill end-to-end
  - **Manual Task**: Human execution of full drill
  - **Details**: Execute all phases A-E following runbook, capturing metrics at each step
  - **Validation**: Drill completes successfully or failure is documented

- [ ] **T055**: Complete drill report with actual results
  - **Manual Task**: Human documentation
  - **Details**: Fill out drill report template with actual execution data from T054
  - **Validation**: Drill report is complete and saved (e.g., `scripts/dr/drill-reports/2025-12-21-drill-report.md`)

- [ ] **T056**: Identify runbook improvements from drill execution
  - **Manual Task**: Human analysis after drill
  - **Details**: Review drill report, identify pain points, unclear instructions, missing troubleshooting scenarios
  - **Validation**: At least 3 improvement items documented

- [ ] **T057**: Update runbook with lessons learned
  - **Files**: `docs/runbooks/disaster-recovery-drill.md`
  - **Details**: Incorporate improvements from T056 (clarify ambiguous steps, add troubleshooting scenarios, update estimates)
  - **Validation**: Runbook is improved based on real execution experience

- [ ] **T058**: Schedule next quarterly drill
  - **Manual Task**: Human planning
  - **Details**: Add calendar reminder for next drill (3 months from T054 execution date)
  - **Validation**: Next drill date documented in drill report and calendar

---

## Post-Implementation Tasks

- [ ] **T059**: Commit specification documents
  - **Files**: `specs/012-disaster-recovery-drill/*.md`
  - **Command**: `git add specs/012-disaster-recovery-drill/ && git commit -m "spec: disaster recovery drill specification"`
  - **Validation**: 3 files committed (spec.md, plan.md, tasks.md)

- [ ] **T060**: Commit runbook and scripts (first version)
  - **Files**: `docs/runbooks/disaster-recovery-drill.md`, `scripts/dr/*`
  - **Command**: `git add docs/runbooks/ scripts/dr/ && git commit -m "feat(dr): add disaster recovery runbook and scripts"`
  - **Validation**: Runbook and scripts committed (sensitive files still .gitignored)

- [ ] **T061**: Commit drill report (after execution)
  - **Files**: Drill report markdown file
  - **Command**: `git add scripts/dr/drill-reports/<date>-drill-report.md && git commit -m "docs(dr): drill report for <date>"`
  - **Validation**: Drill report committed for historical reference

- [ ] **T062**: Create PR for feature branch
  - **Command**: Push branch and create pull request on GitHub
  - **Validation**: PR created with link to drill report demonstrating successful execution

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
- **Manual tasks are majority**: This is expected for a drill. Automation supports repeatability, but human judgment is required.
- **Drill report is key deliverable**: The completed drill report proves recovery capability and documents baselines for future drills.
- **Break-glass testing**: Recommended to test break-glass procedure at least once, but can be separate from primary drill if time-constrained.
- **Quarterly execution**: After initial drill, schedule recurring execution (quarterly) to maintain confidence in recovery capability.
