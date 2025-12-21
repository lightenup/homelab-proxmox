# Feature Specification: Disaster Recovery Drill

**Feature Branch**: `012-disaster-recovery-drill`  
**Created**: December 21, 2025  
**Status**: Draft  
**Input**: "Prove we can recover encrypted backups stored in Hetzner Object Storage (S3-compatible) without relying on the existing Synology NAS, and document a repeatable drill. The encryption key must be stored in Bitwarden and the procedure must be tested and documented."

## Clarifications

### Initial Requirements (2025-12-21)

- **Backup Location**: Hetzner Object Storage at `nbg1.your-objectstorage.com`, bucket `synbackup`, path `DiskStation413j_1.hbk`
- **Backup Format**: Synology Hyper Backup format confirmed (Config, Control, Guard, Pool folders visible, 1.73 TB total, 73,650 files)
- **Backup Scope**: Immich photos only (primary critical data for validation)
- **Encryption Key Storage**: Bitwarden vault (break-glass procedures documented but not implemented in initial drill)
- **Independence Requirement**: Drill must be executable without access to Proxmox or Synology NAS (laptop or fresh VM only)
- **Secret Handling**: NO credentials, encryption keys, or rclone configs committed to git - use environment variables and local .gitignored files
- **Automation Philosophy**: Manual-first approach with scripts for repeatable steps (list, download, verify), but avoid over-automation of one-time drill activities

### Session 2025-12-21

- **Q: Which service data should be validated during the drill?** → A: Focus on Immich data only (photos are most critical, 1.73 TB dataset)
- **Q: What is the Hetzner S3 bucket name and path structure?** → A: Bucket `synbackup`, path `DiskStation413j_1.hbk`, endpoint `nbg1.your-objectstorage.com`
- **Q: Which small file should be used for Phase B connectivity test?** → A: `_Syno_TaskConfig` (1.63 KB) - smallest file, quick validation
- **Q: What does "full backup download" mean for 1.73 TB backup?** → A: Download metadata + Config + one Pool data chunk (~10-50 GB sample subset) to prove decrypt/extract workflow using Hyper Backup Explorer's selective restore feature (not full 1.73 TB)
- **Q: Which break-glass method should be implemented for initial drill?** → A: Bitwarden only for now; break-glass procedures documented but not implemented in initial drill (future enhancement)

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Catastrophic Infrastructure Loss (Priority: P1)

As a homelab administrator, when both my Proxmox host and Synology NAS are destroyed (fire, flood, theft, ransomware), I need to be able to access and decrypt my encrypted Immich photo backups from Hetzner Object Storage using only a laptop and credentials from Bitwarden, so I can recover critical data without depending on my original infrastructure.

**Why this priority**: This is the fundamental disaster recovery scenario. All other capabilities are meaningless if we cannot recover data when primary infrastructure is lost. This drill validates that our backup strategy actually works in a worst-case scenario.

**Independent Test**: Can be fully tested by (1) using a fresh Linux VM or laptop (not Proxmox/NAS), (2) retrieving credentials from Bitwarden, (3) connecting to Hetzner S3, (4) downloading encrypted backup, (5) decrypting with key from Bitwarden, and (6) verifying file count and sample content integrity.

**Acceptance Scenarios**:

1. **Given** I have lost all homelab infrastructure, **When** I retrieve Hetzner S3 credentials and encryption key from Bitwarden on a new machine, **Then** I can successfully authenticate to Hetzner Object Storage and list available backups
2. **Given** I have listed available backups, **When** I download an encrypted backup archive to local storage, **Then** the download completes successfully with file integrity verified (checksums match)
3. **Given** I have downloaded encrypted backup, **When** I decrypt using the encryption key from Bitwarden, **Then** the decryption succeeds and I can access individual files within the backup
4. **Given** I have decrypted backup contents, **When** I verify file count and sample file hashes, **Then** the restored data matches expected integrity checks (proof of successful recovery)

---

### User Story 2 - Repeatable Drill Process (Priority: P1)

As a homelab administrator, when I need to validate my disaster recovery capability (quarterly drill or after backup changes), I need a documented runbook with supporting scripts, so I can execute the drill consistently and measure recovery time/cost without manually remembering each step.

**Why this priority**: A disaster recovery plan that isn't tested regularly is worthless. This scenario ensures the drill can be repeated by anyone (including future me) with consistent results, building confidence in the recovery process and identifying drift in backup tooling or processes.

**Independent Test**: Can be tested by (1) following the written runbook from start to finish, (2) using provided scripts (hetzner_list.sh, hetzner_download.sh, verify_restore.sh), (3) completing drill without consulting external documentation, and (4) generating a drill report with timings and outcomes.

**Acceptance Scenarios**:

1. **Given** the disaster recovery runbook exists, **When** I execute the drill following only the documented steps, **Then** I can complete all phases (access, download, decrypt, verify) without needing additional resources or documentation
2. **Given** I am running the drill, **When** I use the provided automation scripts (list, download, verify), **Then** the scripts execute successfully with clear output and no hardcoded credentials
3. **Given** I complete the drill, **When** I generate a drill report, **Then** the report captures date, duration, data volume downloaded, success/failure outcomes, and any issues encountered

---

### User Story 3 - Break-Glass Access (Priority: P2)

As a homelab administrator, when I need to recover backups but cannot access Bitwarden (Bitwarden service outage, forgotten master password, credential manager compromise), I need documented procedures for accessing encryption keys through alternative secure channels, so I am not permanently locked out of my own backups.

**Why this priority**: While less likely than infrastructure loss, being unable to access the credential manager creates a single point of failure. Break-glass procedures ensure that encryption keys have a documented fallback retrieval path, even if it requires more manual effort.

**Independent Test**: Can be tested by (1) reading break-glass documentation, (2) confirming encryption key is documented in an alternative secure location (encrypted USB drive, physical paper in safe, secondary credential manager), (3) attempting key retrieval without Bitwarden access, and (4) verifying the retrieved key successfully decrypts a test backup.

**Acceptance Scenarios**:

1. **Given** Bitwarden is inaccessible, **When** I follow the break-glass procedure, **Then** I can retrieve the encryption key from the documented alternative source
2. **Given** I have retrieved the encryption key via break-glass, **When** I attempt decryption, **Then** the key successfully decrypts backup archives (proving the alternative key source is valid and current)
3. **Given** encryption keys change, **When** the keys are updated, **Then** the break-glass documentation is updated to reflect new key storage locations and access procedures

---

### Edge Cases

- **What happens if Hetzner S3 credentials expire?** (Drill fails at Phase A; runbook must document credential renewal process and expected expiration timeline)
- **What happens if backup format changes?** (Drill includes decision checkpoint to confirm format before investing time in wrong tooling; runbook documents multiple format possibilities)
- **What happens if download bandwidth is insufficient?** (Drill starts with small file download first; documents expected download times for full backups; suggests alternatives like colocation download or higher-bandwidth connection)
- **What happens if encryption key in Bitwarden is incorrect?** (Decrypt phase fails with clear error; break-glass procedure must be invoked; highlights importance of testing drill regularly)
- **What happens if restore verification discovers corruption?** (Drill report documents failure; triggers investigation of backup integrity and potentially backup rotation policy review)
- **How do we handle partial backups or incremental backup chains?** (Drill must document dependency order if restoring incrementals; start with full backup verification first)

## Requirements *(mandatory)*

### Functional Requirements

#### Access Requirements

- **FR-001**: Drill MUST be executable on a machine independent of Proxmox or Synology infrastructure (laptop, cloud VM, or bare Linux install)
- **FR-002**: Hetzner Object Storage S3 credentials (access key ID, secret access key, endpoint URL) MUST be retrievable from Bitwarden vault
- **FR-003**: Backup encryption key MUST be retrievable from Bitwarden vault with documented entry name/location
- **FR-004**: Break-glass documentation MUST specify alternative encryption key retrieval method if Bitwarden is unavailable
- **FR-005**: Scripts MUST read credentials from environment variables or local .gitignored config files (NO hardcoded secrets)
- **FR-006**: Drill MUST successfully authenticate to Hetzner S3 endpoint and list available backup objects

#### Download Requirements

- **FR-007**: Drill MUST download `_Syno_TaskConfig` file (1.63 KB) first as connectivity test before downloading larger metadata and Pool chunks
- **FR-008**: Download script MUST support dry-run mode (list what would be downloaded without actually downloading)
- **FR-009**: Download script MUST log download progress (files, bytes transferred, estimated time remaining)
- **FR-010**: Downloaded files MUST be verified for integrity (checksum validation where available)
- **FR-011**: Drill MUST document actual download time, bandwidth usage, and any Hetzner egress costs incurred

#### Decrypt/Extract Requirements

- **FR-012**: Drill MUST validate Hyper Backup format structure (Config, Control, Guard, Pool folders present) before attempting decrypt
- **FR-013**: If Hyper Backup format, decrypt/extract MUST use Synology Hyper Backup Explorer tool
- **FR-014**: Decryption process MUST succeed using encryption key from Bitwarden
- **FR-015**: Extracted files MUST be accessible on local filesystem for verification
- **FR-016**: Drill MUST document tooling required for decrypt/extract (including installation instructions)

#### Verification Requirements

- **FR-017**: Verification script MUST count total files extracted and compare to expected baseline (if known)
- **FR-018**: Verification script MUST support selective file hash checking (sample N random files or specific critical files)
- **FR-019**: Drill MUST validate that at least one sample Immich photo can be opened and displays correctly (image viewable, EXIF data intact)
- **FR-020**: Verification phase MUST clearly indicate SUCCESS or FAILURE based on file count and hash checks

#### Documentation Requirements

- **FR-021**: Disaster recovery runbook MUST be written in plain language for non-expert execution
- **FR-022**: Runbook MUST include step-by-step instructions for all phases (access, download, decrypt, verify)
- **FR-023**: Runbook MUST document prerequisites (required tools, credentials needed from Bitwarden)
- **FR-024**: Runbook MUST include troubleshooting section for common failure scenarios
- **FR-025**: Drill report template MUST capture: execution date, duration, data volume, success/failure, issues encountered, cost incurred
- **FR-026**: Break-glass section MUST document alternative encryption key retrieval if Bitwarden unavailable

#### Script Requirements

- **FR-027**: All scripts MUST be stored in `scripts/dr/` directory
- **FR-028**: Scripts MUST NOT contain hardcoded credentials, API keys, or encryption keys
- **FR-029**: Scripts MUST have clear usage documentation (help text or README)
- **FR-030**: Scripts MUST provide clear success/failure exit codes and error messages
- **FR-031**: Scripts MUST log actions to facilitate drill report generation

### Non-Functional Requirements

- **NFR-001**: Drill execution MUST complete in a reasonable timeframe (target: <4 hours for sample restore including 10-50 GB download, <5 minutes for 1.63 KB connectivity test)
- **NFR-002**: Download script SHOULD support resumable downloads if connection interrupted
- **NFR-003**: Scripts SHOULD be POSIX-compliant shell (bash/zsh) for maximum portability
- **NFR-004**: Runbook SHOULD be accessible offline (no external dependencies for documentation)
- **NFR-005**: Drill report SHOULD track historical drill results for trend analysis (quarterly drill success rate)

## Success Definition *(mandatory)*

The disaster recovery drill is considered successful when all of the following criteria are met:

### Phase A: Hetzner Access Verification
- [ ] Successfully authenticate to Hetzner Object Storage using credentials from Bitwarden
- [ ] List all backup objects in S3 bucket (confirm backup exists and is accessible)
- [ ] Identify backup format and document findings

### Phase B: Sm`_Syno_TaskConfig` file (1.63 KB) to verify connectivity and credentials
- [ ] Verify downloaded file integrity (file size matches expected 1.63 KB)
- [ ] Document download speed and time taken

### Phase C: Decrypt/Extract Proof
- [ ] Download metadata folders (Config, Control, Guard) and one Pool data chunk (~10-50 GB sample subset from 1.73 TB total)
- [ ] Decrypt using encryption key from Bitwarden
- [ ] Use Hyper Backup Explorer's selective restore feature to extract sample Immich photos (10-20 photos as proof of concept)
- [ ] Successfully extract files to local filesystem
- [ ] Confirm file extraction completed without errors

### Phase D: Integrity Verification
- [ ] Count total files extracted
- [ ] Perform hash checks on sample files (minimum 5 files, or 1% of total files, whichever is greater)
- [ ] Manually verify at least one critical file is viewable/readable (photo, document, database dump)
- [ ] All verification checks PASS

### Phase E: Drill Report & Documentation
- [ ] Complete drill report template with actual results
- [ ] Document total time taken (start to finish)
- [ ] Document data volume downloaded
- [ ] Document any costs incurred (Hetzner egress fees)
- [ ] Document issues encountered and resolutions
- [ ] Document lessons learned and runbook improvements needed
Future Enhancement)
- [ ] Break-glass procedures documented in runbook for reference
- [ ] Alternative encryption key storage method identified (encrypted USB, paper backup, or trusted contact)
- [ ] Break-glass implementation and testing deferred to post-initial-drill (not blocking initial success)accessible
- [ ] Key retrieval method tested without Bitwarden access

## Assumptions *(mandatory)*

1. **Backup Existence**: At least one encrypted backup already exists in Hetzner Object Storage (this drill does NOT create backups, only validates recovery)
2. **Credential Availability**: Hetzner S3 credentials and encryption key are stored in Bitwarden and accessible during drill (no break-glass implementation required for initial drill)
3. **Backup Format**: Synology Hyper Backup format confirmed (1.73 TB, 73,650 files in bucket `synbackup/DiskStation413j_1.hbk`)
4. **Network Access**: Machine executing drill has internet access with sufficient bandwidth for multi-GB downloads
5. **Disk Space**: Local machine has sufficient free disk space for sample download and extraction (estimate: 100-150 GB for metadata + one Pool chunk + extracted files)
6. **Tool Availability**: Standard Linux tools are available (bash, curl/wget, rclone or aws-cli); specialized tools (Hyper Backup Explorer) documented for installation
7. **Backup Integrity**: Backups created by existing process are valid and not corrupted (this drill tests restore process, not backup creation)
8. **S3 Compatibility**: Hetzner Object Storage adheres to standard S3 API for authentication and object access
9. **Encryption Format**: Encryption is standard (AES-256 or similar) and documented in Bitwarden notes
10. **Stateless Execution**: Drill can be run from any fresh machine without pre-configured state

## Out of Scope *(mandatory)*

### Explicitly NOT Included

- **Backup creation automation**: This drill validates restore only; creating/scheduling backups is separate effort
- **Synology-specific restore workflows**: If backups can only be restored to Synology hardware, drill will document this limitation but not solve it
- **Full service restoration**: Drill proves data recovery; rebuilding running services (Immich, Proxmox) is separate effort
- **Automated drill scheduling**: Drill is manually triggered; future enhancement could automate quarterly execution
- **Cost optimization**: Drill documents costs but does not implement egress optimization (e.g., chunked downloads, local caching)
- **Multi-region redundancy**: Drill assumes single Hetzner region; geographic redundancy is separate architecture decision
- **Point-in-time restore selection**: Drill tests restore of latest backup; selecting specific backup date is enhancement
- **Incremental restore logic**: If backups are incremental, drill documents chain dependencies but may only restore full backups
- **Backup rotation management**: Managing backup retention is separate from restore validation

### Future Enhancements (Not This Iteration)

- Automated quarterly drill execution via cron/systemd timer
- Integration with monitoring to alert if drill not executed within SLA
- Comparison of multiple backup restore strategies (restic vs Hyper Backup)
- Restore time benchmarking across different download locations (home ISP vs colocation)
- Break-glass key escrow service (encrypted key file stored with trusted third party)

## Break-Glass Recovery Procedures *(mandatory)*

**IMPORTANT - Constitution Compliance**: All break-glass storage methods described below are PHYSICAL/OFFLINE ONLY. No encryption keys, encrypted files, or credential references are stored in this git repository per Constitution Principle II (Secrets Policy: "Never commit secrets"). Break-glass materials exist outside version control.

### Scenario: Bitwarden Unavailable

If Bitwarden is inaccessible (service outage, forgotten master password, credential manager compromise), use this procedure to retrieve encryption keys:

#### Primary Break-Glass Method: Encrypted USB Drive

1. **Location**: Physical USB drive labeled "DR Keys" stored in fireproof safe at [LOCATION - not committed to git]
2. **Contents**: Encrypted text file containing:
   - Hetzner S3 access key ID
   - Hetzner S3 secret access key
   - Hetzner S3 endpoint URL
   - Backup encryption key (or KeePass database with master password separately secured)
3. **Decryption Key**: USB drive is encrypted with LUKS or VeraCrypt; decryption password is [METHOD - not committed to git]
4. **Validation**: Test USB drive accessibility during drill Phase A checkpoint

#### Secondary Break-Glass Method: Paper Backup

1. **Location**: Sealed envelope stored in [LOCATION - not committed to git]
2. **Contents**: Printed QR codes or handwritten credentials:
   - Hetzner S3 credentials
   - Backup encryption key (split into multiple parts if key is long)
3. **Access**: Envelope should be tamper-evident; if seal broken, assume credentials compromised and rotate
4. **Limitations**: Paper backup is vulnerable to loss/destruction in same disaster that destroyed infrastructure; coordinate with off-site storage

#### Tertiary Break-Glass Method: Trusted Contact

1. **Procedure**: Share encrypted copy of credentials with trusted family member or friend
2. **Format**: KeePass database file encrypted with strong password that trusted contact knows
3. **Retrieval**: Contact trusted individual and retrieve encrypted file via secure channel (encrypted email, Signal, in-person)
4. **Validation**: Periodically confirm trusted contact still has access to credentials

#### Break-Glass Procedure Steps

1. Attempt primary method (USB drive) first
2. If primary unavailable, attempt secondary (paper backup)
3. If neither available, contact trusted individual (tertiary)
4. Once credentials retrieved, immediately test validity by connecting to Hetzner S3
5. After successful drill using break-glass credentials, rotate all credentials and update primary source (Bitwarden once accessible)
6. Document break-glass usage in drill report and investigate root cause of Bitwarden unavailability

### When to Update Break-Glass Credentials

- Immediately after any credential rotation (Hetzner S3 keys, encryption key)
- After successful drill execution (confirm break-glass credentials still valid)
- Annually at minimum, even if no changes
- After any security incident affecting credential storage

### Break-Glass Testing

- Break-glass procedure should be tested at least annually
- Do NOT rotate production credentials during break-glass test; use test/staging environment if available
- Document break-glass test results separately from full drill report
