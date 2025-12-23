# Feature Specification: Proxmox Config Backup Automation

**Feature Branch**: `013-proxmox-config-backup`  
**Created**: December 22, 2025  
**Status**: Draft (Architecture Corrected: Choice 3, Option A)  
**Input**: "Automate backups of Proxmox configuration and homelab IaC artifacts with encryption and rotation"

**Architecture Decision**: Systemd timer runs local bash script on PVE host. Ansible deploys/configures the script, packages, and systemd units but is NOT the runtime.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Recover from Complete Host Failure (Priority: P1)

As a homelab operator, when my Proxmox host fails catastrophically, I need to restore the exact configuration (LXC definitions, network settings, storage mounts) onto replacement hardware so all services can resume with minimal downtime.

**Why this priority**: This is the primary disaster recovery scenario. Without automated, verifiable backups of Proxmox configuration, a host failure means manual reconstruction of LXC definitions, network settings, and storage mounts - potentially days of work and high risk of configuration drift.

**Independent Test**: Install fresh Proxmox on test hardware, restore latest backup archive, verify LXC configs match production. Success means all container definitions, network interfaces, NFS mounts, and Tailscale configuration are present and correct.

**Acceptance Scenarios**:

1. **Given** Proxmox host has 3 LXCs configured with various mounts and networks, **When** backup runs and I restore to fresh Proxmox install, **Then** /etc/pve/lxc/*.conf files are identical and containers can be started
2. **Given** host has custom network bridge configuration (vmbr1 with VLAN), **When** backup is restored, **Then** /etc/network/interfaces is restored and network topology is intact
3. **Given** NFS mounts defined in /etc/fstab, **When** backup is restored, **Then** fstab is restored and mounts can be re-established

---

### User Story 2 - Deterministic Infrastructure Rebuild (Priority: P1)

As a homelab operator, I need backups of Terraform state and Ansible inventory so I can rebuild the entire infrastructure deterministically from code, ensuring no configuration drift between disasters.

**Why this priority**: Infrastructure-as-code only works if the state is preserved. Terraform state contains resource mappings and metadata required for updates. Ansible inventory contains host-specific variables. Without these, IaC becomes documentation rather than executable automation.

**Independent Test**: Delete Terraform state locally, restore from backup, run `terraform plan` - should show zero changes. Delete Ansible inventory, restore from backup, run playbook in check mode - should show no configuration drift.

**Acceptance Scenarios**:

1. **Given** Terraform has provisioned 3 LXCs with specific IDs, **When** terraform.tfstate is restored from backup, **Then** `terraform plan` shows no changes and state matches reality
2. **Given** Ansible inventory has custom host_vars for each LXC, **When** inventory is restored from backup, **Then** running playbook in check mode shows no configuration changes needed
3. **Given** git repo has uncommitted local changes to playbooks, **When** backup includes current repo state, **Then** restore provides exact working tree for immediate re-execution

---

### User Story 3 - Scheduled Automated Backups (Priority: P1)

As a homelab operator, I need backups to run automatically on schedule so I don't have to remember to run them manually, ensuring recent configuration is always protected.

**Why this priority**: Manual backups fail due to human error. Automation ensures backups happen reliably and consistently. This is critical infrastructure protection that cannot depend on manual intervention.

**Independent Test**: Configure backup to run daily at 2 AM, wait 48 hours, verify two dated backup archives exist on NAS with correct permissions and non-zero size. Both archives should decrypt successfully.

**Acceptance Scenarios**:

1. **Given** backup schedule set to daily 2 AM, **When** 24 hours pass, **Then** new backup archive exists on NAS with today's date in filename
2. **Given** backup has run for 30 days, **When** checking NAS storage, **Then** exactly 30 daily backups exist (rotation working correctly)
3. **Given** systemd timer is enabled, **When** Proxmox host reboots, **Then** timer remains active and next scheduled backup runs

---

### User Story 4 - Verify Backup Integrity Without Restore (Priority: P2)

As a homelab operator, I need to verify backup archives are not corrupted without performing a full restore, so I can catch backup failures early.

**Why this priority**: Backups are worthless if corrupted. Regular verification (separate from production restore testing) ensures backup process is working correctly and archives are usable before disaster strikes.

**Independent Test**: Run verification command against latest backup, command should decrypt archive, list contents, verify checksums, and report success/failure. No files should be extracted. Process should complete in under 60 seconds.

**Acceptance Scenarios**:

1. **Given** latest backup archive on NAS, **When** running verify command with encryption key from Bitwarden, **Then** command decrypts archive, lists all expected files (*.conf, tfstate, inventory files), and reports success
2. **Given** corrupted backup file (manually truncate), **When** running verify command, **Then** command detects corruption and reports specific error (checksum mismatch)
3. **Given** multiple backup archives, **When** verify runs against each, **Then** command reports which backups are valid and which are corrupted with timestamps

---

### User Story 5 - Email Notification on Failure (Priority: P3)

As a homelab operator, I need email notifications when backups fail so I can investigate and fix issues promptly rather than discovering backup failure during disaster recovery.

**Why this priority**: Silent backup failures are dangerous. Email notifications provide early warning system. Lower priority than core backup functionality but important for operational monitoring.

**Independent Test**: Simulate backup failure (remove NAS mount), trigger backup, verify email received within 5 minutes with error details. Fix issue, trigger backup, verify success email includes backup filename and size.

**Acceptance Scenarios**:

1. **Given** backup process fails to mount NAS, **When** backup runs, **Then** email sent within 5 minutes with subject "Proxmox Backup Failed" and error details (mount failure)
2. **Given** encryption fails due to missing key, **When** backup runs, **Then** email contains specific error message and remediation steps
3. **Given** backup succeeds, **When** backup completes, **Then** optional success email sent with archive name, size, and verification checksum

---

### Edge Cases

- **What happens when NFS mount to NAS is unavailable during backup?** Backup should fail gracefully, log error, send notification, and preserve previous successful backup. Do not create partial/corrupted archives.
- **What happens when disk space is full on NAS?** Backup should detect before writing, attempt to rotate old backups to make space, then retry. If still insufficient, fail with clear error.
- **What happens when /etc/pve is temporarily unavailable (clustered FS)?** Retry with exponential backoff (max 3 attempts), log warning if succeeded on retry, fail with error if all attempts exhausted.
- **What happens when backup runs while LXC configuration is being modified?** Use consistent snapshot approach or lock mechanism to ensure configuration consistency. Document race condition risk if locks unavailable.
- **What happens when encryption key is rotated?** Old backups encrypted with old key must remain decryptable. Document key rotation procedure: test new key, keep both keys in Bitwarden, label backups by key version.
- **What happens when backup script is run manually while automated backup is running?** Implement lock file to prevent concurrent execution, second invocation exits immediately with "backup already running" message.

## Requirements *(mandatory)*

### Functional Requirements

#### Backup Content

- **FR-001**: System MUST back up all LXC container configuration files from /etc/pve/lxc/*.conf
- **FR-002**: System MUST back up Proxmox storage configuration (/etc/pve/storage.cfg)
- **FR-003**: System MUST back up network configuration (/etc/network/interfaces and /etc/network/interfaces.d/*)
- **FR-004**: System MUST back up system fstab (/etc/fstab) containing NFS mount definitions
- **FR-005**: System MAY back up Tailscale state and configuration (/var/lib/tailscale/*, /etc/default/tailscaled) if proxmox_backup_include_tailscale_state=true (default: false, opt-in for security)
- **FR-006**: System MUST back up Terraform state files (terraform.tfstate, terraform.tfstate.backup) from IaC repository location if proxmox_backup_repo_path is defined
- **FR-007**: System MUST back up Ansible inventory files (inventories/generated/hosts.yml, group_vars/*, host_vars/*) from IaC repository location if proxmox_backup_repo_path is defined
- **FR-008**: System MUST back up Ansible playbook files (playbooks/*.yml, roles/*/tasks/*.yml) from IaC repository location if proxmox_backup_repo_path is defined
- **FR-009**: System MUST back up key documentation files (README.md, docs/operations/*.md, docs/runbooks/*.md) from IaC repository location if proxmox_backup_repo_path is defined
- **FR-010**: System MAY back up rclone configuration if present (/root/.config/rclone/rclone.conf or /etc/rclone/rclone.conf) if proxmox_backup_include_rclone_conf=true (default: false, opt-in for security)

#### Exclusions

- **FR-011**: System MUST NOT back up LXC root filesystems or data volumes (config only)
- **FR-012**: System MUST NOT back up git history (.git/ directory) - only current working tree required
- **FR-013**: System MUST NOT back up secrets in plaintext - encryption keys, API tokens, passwords must only exist in encrypted backup
- **FR-014**: System MUST NOT back up temporary files, caches, or build artifacts (node_modules/, .terraform/, __pycache__/)

#### Security & Encryption

- **FR-015**: System MUST encrypt backup archive before transferring to NAS
- **FR-016**: System MUST use age encryption tool (simple, modern, supports Bitwarden key storage)
- **FR-017**: System MUST support encryption key stored in Bitwarden (manual retrieval, injected via environment variable)
- **FR-018**: System MUST generate unique encryption key per homelab (not per backup - same key for all backups in same homelab)
- **FR-019**: System MUST include key fingerprint/identifier in backup metadata to facilitate key management
- **FR-020**: System MUST NOT store encryption key in git repository, Ansible vars files, or any committed code
- **FR-021**: System MUST verify backup can be decrypted immediately after creation (post-backup validation)

#### Storage & Organization

- **FR-022**: System MUST store backups on NAS at dedicated share /volume1/homelab_backups/proxmox/
- **FR-023**: System MUST use NFS mount for backup transfer (simplest for Proxmox-to-Synology, works without Tailscale)
- **FR-024**: System MUST name backup files with timestamp: proxmox-backup-YYYYMMDD-HHMMSS.tar.zst.age
- **FR-025**: System MUST create staging directory on Proxmox host (/var/backups/proxmox-staging/) for temporary files
- **FR-026**: System MUST clean staging directory after successful backup (no sensitive data left on host)
- **FR-027**: System MUST set correct permissions on backup files (640, owner: root, group: backups or similar)

#### Rotation & Retention

- **FR-028**: System MUST implement rotation policy: keep 30 daily backups
- **FR-029**: System MUST implement rotation policy: keep 12 monthly backups (first backup of each month)
- **FR-030**: System MUST rotate old backups BEFORE creating new backup (fail-safe if disk full)
- **FR-031**: System MUST preserve at least 1 successful backup even if rotation policy would delete it
- **FR-032**: System MUST log rotation actions (which files deleted, reason, timestamp) to systemd journal

#### Script Deployment & Configuration

- **FR-032a**: Ansible role MUST deploy bash script template to /usr/local/sbin/proxmox-config-backup (mode 0750, owner root:root)
- **FR-032b**: Bash script MUST use strict mode (set -euo pipefail) and structured error handling
- **FR-032c**: Bash script MUST acquire exclusive lock using flock(1) before any operations
- **FR-032d**: Bash script MUST create timestamped staging directory (/var/backups/proxmox-staging/<timestamp>)
- **FR-032e**: Bash script MUST implement retry logic with exponential backoff for /etc/pve access (max 3 attempts)

#### Execution & Automation

- **FR-033**: System MUST be implemented as local bash script (/usr/local/sbin/proxmox-config-backup) deployed by Ansible role
- **FR-034**: System MUST be idempotent - running twice produces same result (new backup created, old rotated)
- **FR-035**: System MUST support manual execution via direct script invocation or systemd service start
- **FR-036**: System MUST support scheduled execution via systemd timer running the local script (NOT ansible-playbook)
- **FR-037**: System MUST run as root user on Proxmox host (required for /etc/pve access)
- **FR-038**: System MUST log all operations to systemd journal (journalctl) with structured logging
- **FR-039**: System MUST implement flock-based locking to prevent concurrent backup executions (NOT manual lockfile)

#### Verification & Monitoring

- **FR-040**: System MUST provide verification command that decrypts and lists backup contents without extraction
- **FR-041**: System MUST verify backup integrity immediately after creation (checksum verification)
- **FR-042**: System MUST report backup success/failure via exit code (0 = success, non-zero = failure with specific codes)
- **FR-043**: System MUST send email notification on backup failure (optional, integrates with existing SMTP/Kuma setup)
- **FR-044**: System MUST include backup metrics in notification: size, duration, file count, checksum
- **FR-045**: System MUST log backup operations to systemd journal for centralized monitoring

#### Restore Support

- **FR-046**: System MUST provide documentation for restore procedure (step-by-step runbook)
- **FR-047**: Restore documentation MUST include prerequisites: fresh Proxmox install, encryption key from Bitwarden
- **FR-048**: Restore documentation MUST include manual steps for each critical file type (LXC configs, network, fstab)
- **FR-049**: Restore documentation MUST include verification steps to confirm restore success before starting containers

### Key Entities

- **Backup Archive**: Encrypted, compressed tarball containing Proxmox configuration and IaC artifacts. Attributes: filename (timestamp-based), size, creation timestamp, encryption key fingerprint, checksum (SHA256).

- **Backup Manifest**: Metadata file (stored inside archive) listing all backed-up files with checksums. Attributes: file paths (relative), SHA256 hashes, sizes, modification times. Purpose: verification without full extraction.

- **Encryption Key**: Age public/private keypair stored in Bitwarden. Attributes: key ID, fingerprint, creation date, homelab identifier. Private key used for encryption during backup, public key stored in Bitwarden item.

- **NAS Share**: Dedicated NFS export on Synology for backup storage. Attributes: path (/volume1/homelab_backups/proxmox/), permissions (rwx for PVE host), export options (async, no_wdelay for performance).

- **Backup Schedule**: Systemd timer or cron configuration. Attributes: frequency (daily), time (2 AM), enabled/disabled status, randomized delay (optional, to avoid peak hours).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Operators can restore complete Proxmox configuration to fresh install in under 2 hours (including OS install, backup retrieval, decryption, file restoration, and verification)

- **SC-002**: Backup process completes within 10 minutes (typical homelab size: 3-5 LXCs, 10MB Terraform state, 50MB Ansible repo)

- **SC-003**: Backup archives are under 100 MB compressed and encrypted (configuration data is small, dominated by Ansible roles)

- **SC-004**: 100% of backup executions produce verifiable archives (measured over 30 days - zero corrupted or incomplete backups)

- **SC-005**: Operators can verify backup integrity (decrypt, list contents, check checksums) in under 60 seconds without extracting files

- **SC-006**: Backup failure detection occurs within 10 minutes of failure (via email notification or monitoring check)

- **SC-007**: Terraform plan shows zero differences after restoring terraform.tfstate from backup (deterministic state preservation)

- **SC-008**: Ansible playbook run in check mode shows zero changes after restoring inventory from backup (configuration drift eliminated)

- **SC-009**: NAS storage consumption remains stable (rotation maintains 30 daily + 12 monthly backups, approximately 4 GB total for typical homelab)

- **SC-010**: Zero encryption keys or API tokens exposed in backup logs, staging directories, or NAS storage (security validation via grep/scan)

## Scope *(mandatory)*

### In Scope

- Automated backup of Proxmox host configuration files (/etc/pve, network, fstab, Tailscale)
- Automated backup of IaC artifacts (Terraform state, Ansible inventory/playbooks, documentation)
- Encryption using age before transfer to NAS
- Storage on dedicated NAS share via NFS mount
- Automated rotation with 30-day daily + 12-month monthly retention
- Verification command for integrity checking
- Email notifications for failures (optional)
- Ansible role implementation with playbook wrapper
- Systemd timer for scheduling
- Documentation for restore procedures
- Lock mechanism to prevent concurrent execution

### Out of Scope

- Full LXC/VM disk backups (data backups handled separately, e.g., Synology Hyper Backup)
- Automated restore process (manual restore with runbook guidance only)
- Backup of LXC container filesystems or application data
- Offsite backup replication (future enhancement, focus on local NAS first)
- Real-time/continuous backup (scheduled daily only)
- Backup of Proxmox cluster configurations (single-node setup assumed)
- Router configuration backups (separate concern)
- Monitoring beyond email notifications (integration with existing monitoring systems out of scope)
- Backup encryption key rotation automation (manual procedure documented)
- Web UI for backup management (CLI and Ansible only)

## Assumptions *(mandatory)*

### Technical Environment

- **ASM-001**: Proxmox VE 8.x is installed on host `pve` (192.168.1.112)
- **ASM-002**: Synology NAS is available at 192.168.1.109 with NFS enabled
- **ASM-003**: Ansible control machine can reach Proxmox host via SSH (existing setup)
- **ASM-004**: age encryption tool is available or can be installed on Proxmox host
- **ASM-005**: Python 3 is available on Proxmox host for Ansible execution
- **ASM-006**: Proxmox host has sufficient disk space for staging (/var/backups/: 1 GB minimum)
- **ASM-007**: NAS has sufficient space for backup retention (5 GB minimum for 42 backups @ 100 MB each)
- **ASM-008**: Proxmox host can mount NFS shares (nfs-common package installed)

### Operational Context

- **ASM-009**: Operator has Bitwarden account with encryption key stored securely
- **ASM-010**: Operator can manually inject encryption key via environment variable or git-ignored vars file
- **ASM-011**: Backups run during low-activity window (2 AM) when configuration is stable
- **ASM-012**: Operator tests restore procedure at least once per quarter (separate drill)
- **ASM-013**: SMTP is configured and working for email notifications (existing Kuma setup reused)
- **ASM-014**: Operator has root/sudo access to Proxmox host for manual troubleshooting

### Infrastructure Characteristics

- **ASM-015**: Homelab is single-node Proxmox (no cluster, /etc/pve is local filesystem)
- **ASM-016**: LXC count is stable (3-10 containers, not hundreds)
- **ASM-017**: Terraform state is local (not using remote backend like S3 or Terraform Cloud)
- **ASM-018**: For US2 (IaC artifacts), IaC repository MUST be cloned/synced to PVE host at proxmox_backup_repo_path OR US2 is skipped
- **ASM-019**: Network connectivity is reliable between Proxmox and NAS (both on same VLAN/subnet)
- **ASM-020**: Time synchronization is working (backup timestamps are accurate)

### Decision Assumptions

- **ASM-021**: Age encryption chosen over GPG (simpler, better Bitwarden integration, modern alternative)
- **ASM-022**: NFS chosen over rsync/SSH for backup transfer (simpler, already used for other mounts)
- **ASM-023**: Ansible role chosen over standalone script (consistency with existing automation, idempotence)
- **ASM-024**: Systemd timer chosen over cron (modern systemd-based systems, better logging)
- **ASM-025**: Daily backups sufficient (configuration changes are infrequent, hourly unnecessary)

## Dependencies *(if applicable)*

### External Dependencies

- **DEP-001**: Synology NAS must have NFS service enabled and /volume1/homelab_backups/ share created
- **DEP-002**: NAS must export share with read-write permissions for Proxmox host (192.168.1.112)
- **DEP-003**: age encryption tool must be installed on Proxmox host (installable via apt or compiled)
- **DEP-004**: SMTP credentials must be available in Bitwarden for email notifications (existing setup)

### Internal Dependencies

- **DEP-005**: For US2, proxmox_backup_repo_path variable MUST be defined pointing to IaC repo checkout on PVE host (e.g., /root/homelab-proxmox)
- **DEP-006**: If proxmox_backup_repo_path undefined, US2 (IaC artifacts) tasks are skipped and backup contains only US1 Proxmox config
- **DEP-007**: Backup script must NOT depend on Ansible being installed on PVE (Ansible only for deployment)
- **DEP-008**: Proxmox host must have Ansible dependencies installed (python3, python3-apt, etc.)

### Prerequisite Tasks

- **DEP-009**: NAS share creation and NFS export configuration (manual, documented in runbook)
- **DEP-010**: Age encryption key generation and storage in Bitwarden (manual, one-time setup)
- **DEP-011**: Test NFS mount from Proxmox to NAS (manual validation before automation)
- **DEP-012**: Ansible inventory updated with backup-specific variables (encryption key path, backup schedule)

## Risks *(if applicable)*

### Technical Risks

- **RISK-001**: /etc/pve is clustered filesystem (cephfs) - may have race conditions during backup  
  **Mitigation**: Implement retry logic with exponential backoff, test on single-node Proxmox first
  **Severity**: Medium - Could cause backup failures but won't corrupt data

- **RISK-002**: NFS mount could become unavailable during backup  
  **Mitigation**: Pre-backup mount validation, graceful failure with notification, preserve previous backup
  **Severity**: Low - Fails safely, notification ensures awareness

- **RISK-003**: Age encryption key could be lost or Bitwarden unavailable during disaster recovery  
  **Mitigation**: Document break-glass procedure (paper backup of key), quarterly key recovery drill
  **Severity**: High - Complete backup loss if key unavailable, but solvable with proper documentation

- **RISK-004**: Backup size could grow unexpectedly if IaC artifacts balloon  
  **Mitigation**: Monitor backup sizes, alert if >500 MB, investigate and exclude large unnecessary files
  **Severity**: Low - Disk space issue but detectable and fixable

### Operational Risks

- **RISK-005**: Operator forgets to update Bitwarden encryption key after rotation  
  **Mitigation**: Document key rotation procedure, include verification step (decrypt old backup with new key)
  **Severity**: Medium - Old backups become unrecoverable, but new backups work

- **RISK-006**: Backup failures go unnoticed if email notifications are silently dropped  
  **Mitigation**: Integrate with Uptime Kuma for backup status monitoring, test notification delivery
  **Severity**: Medium - Silent failures dangerous, but testable and fixable

- **RISK-007**: Restore procedure not tested regularly, outdated at disaster time  
  **Mitigation**: Quarterly restore drill (Feature 012 style), document in runbook
  **Severity**: High - Critical failure at worst possible time, but preventable with discipline

## Open Questions *(if any)*

### Technical Decisions

- **Q1**: Should backup include /etc/pve/priv/authorized_keys (SSH keys for inter-node communication)?  
  **Options**: (A) Include - ensures SSH setup preserved, (B) Exclude - regenerate keys on restore for security  
  **Recommendation**: Include - fresh install won't have cluster keys, single-node setup means no security risk

- **Q2**: Should Terraform state backup include .terraform/ directory (provider plugins)?  
  **Options**: (A) Include - faster restore but larger backups, (B) Exclude - smaller backups but slower restore (re-download plugins)  
  **Recommendation**: Exclude - plugins are 100+ MB, easily re-downloaded with `terraform init`, backups stay small

- **Q3**: Should backup archive format be tar.gz (compatible) or tar.zst (better compression)?  
  **Options**: (A) tar.gz - universally compatible, (B) tar.zst - 20-30% better compression, requires zstd tool  
  **Recommendation**: tar.zst - modern tool, better compression, worth dependency for smaller backups

- **Q4**: Should systemd timer include randomized delay to avoid peak hours?  
  **Options**: (A) Fixed 2 AM daily, (B) Random delay 0-30 minutes after 2 AM  
  **Recommendation**: Fixed 2 AM - predictable timing useful for troubleshooting, low traffic at 2 AM anyway

### Operational Decisions

- **Q5**: Should success notifications be sent in addition to failure notifications?  
  **Options**: (A) Failures only - less noise, (B) Both - confirmation backup ran, (C) Weekly summary - batch reporting  
  **Recommendation**: Failures only initially, add weekly summary later if desired

- **Q6**: Should backup manifest be stored separately from archive for quick verification?  
  **Options**: (A) Inside archive only - simpler, (B) Separate manifest file - faster listing without decryption  
  **Recommendation**: Inside archive only - one file to manage, decryption is fast enough (<1s for metadata)

- **Q7**: Should lock file be in /var/run (cleared on reboot) or /var/lock (persists)?  
  **Options**: (A) /var/run - automatic cleanup on reboot, (B) /var/lock - survives reboot for troubleshooting  
  **Recommendation**: /var/run - safer, prevents stale locks blocking backups after unexpected reboot

## Follow-up Features *(if applicable)*

- **FUP-001**: Offsite backup replication (sync encrypted backups to cloud storage: B2, Hetzner, etc.) - enhances disaster recovery beyond local NAS
- **FUP-002**: Automated restore testing (quarterly drill that validates restore procedure in isolated environment) - ensures DR plan stays current
- **FUP-003**: Backup metrics dashboard (Prometheus/Grafana integration showing backup success rate, sizes, durations) - operational visibility
- **FUP-004**: Incremental backups (only backup changed files using rsync or similar) - reduces backup time and storage for large configs
- **FUP-005**: Backup integrity monitoring (detect bit rot by periodically re-verifying old backups) - long-term data integrity
- **FUP-006**: Multi-site backup (replicate to second NAS at different physical location) - protection against site-wide disaster
- **FUP-007**: Immutable backups (use NAS snapshots or WORM storage to prevent ransomware deletion) - ransomware protection
- **FUP-008**: Backup encryption key rotation automation (script to re-encrypt all backups with new key) - security hygiene
- **FUP-009**: Backup of router configuration (backup UniFi/pfSense config alongside Proxmox) - complete infrastructure backup
- **FUP-010**: Web UI for backup management (view backup history, trigger manual backup, download for offsite) - user-friendly interface
