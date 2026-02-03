# Implementation Plan: Proxmox Config Backup Automation

**Branch**: `013-proxmox-config-backup` | **Date**: 2025-12-22 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/013-proxmox-config-backup/spec.md`

**Architecture Decision**: Choice 3, Option A - Local script runtime. Systemd timer runs bash script on PVE host. Ansible deploys/configures the script, packages, systemd units, and configuration file but is NOT the runtime.

## Summary

Automate backup of Proxmox host configuration files and Infrastructure-as-Code artifacts (Terraform state, Ansible inventory) to enable disaster recovery. Backups will be encrypted using age, stored on Synology NAS via NFS, rotated automatically (30 daily + 12 monthly), and scheduled via systemd timer. Primary goal: restore complete Proxmox configuration to fresh install in under 2 hours.

**Key Requirement**: All Proxmox host configs (/etc/pve, network, fstab, optionally Tailscale/rclone) and IaC state (Terraform, Ansible - if repo path defined) must be backed up daily, encrypted at rest, and verifiable without full restore.

**Technical Approach**: Bash script (/usr/local/sbin/proxmox-config-backup) implements backup pipeline: collect → manifest → compress (tar.zst) → encrypt (age) → transfer (NFS) → verify → rotate. Script uses flock for locking, journald for logging. Ansible role deploys script template, configuration file (/etc/proxmox-backup.conf), systemd units, and required packages. Manual restore with documented runbook.

## Technical Context

**Language/Version**: Bash 5.x (backup script runtime), Ansible 2.15+ (deployment only)
**Primary Dependencies**:
- age 1.1+ (encryption)
- zstd 1.5+ (compression)
- nfs-common (NFS client)
- systemd 252+ (timer/service)
- flock (file locking, included in util-linux)
- mail/sendmail (email notifications, optional)

**Storage**:
- Staging: `/var/backups/proxmox-staging/<timestamp>/` on Proxmox host (ephemeral per-run, ~100 MB)
- Persistent: Synology NAS `/volume1/homelab_backups/proxmox/` via NFS mount (~4 GB for 42 backups)
- Backup format: `proxmox-backup-YYYYMMDD-HHMMSS.tar.zst.age` (compressed then encrypted)
- Configuration: `/etc/proxmox-backup.conf` (NAS mount, age key path, retention policy, repo path)

**Testing**:
- Manual validation: Run /usr/local/sbin/proxmox-config-backup → decrypt → verify file contents
- Verification: /usr/local/sbin/proxmox-config-backup --verify <path> (decrypt + checksum validation)
- Integration test: Ansible playbook `test_backup.yml` (deploy script, run manually, verify archive)
- Restore drill: Quarterly test restore to fresh Proxmox install (separate from automation)

**Target Platform**:
- Proxmox VE 8.x (Debian 12-based) on host `pve` (192.168.1.112)
- Synology DSM 7.x NAS (192.168.1.109) with NFS service

**Project Type**: Infrastructure automation (Ansible for deployment, bash script for runtime)

**Performance Goals**:
- Backup completion: <10 minutes (typical homelab: 3-5 LXCs, 10 MB Terraform state if repo defined, 50 MB Ansible repo if repo defined)
- Archive size: <100 MB compressed+encrypted
- Verification: <60 seconds (decrypt + list + SHA256 checksum validation)
- Rotation scan: <30 seconds (42 files @ ~100 MB each)

**Constraints**:
- Script must run as root (required for /etc/pve access)
- No secrets in plaintext in staging, logs, or script variables
- Encryption key stored in Bitwarden (manual injection into /etc/proxmox-backup.conf, not in git)
- flock prevents concurrent execution
- Tailscale state and rclone config backup opt-in only (default: false for security)
- IaC artifacts require proxmox_backup_repo_path defined, otherwise skipped
- Pre-backup rotation (fail-safe if NAS disk full)
- Staging cleanup after successful backup (no sensitive data persists)

**Scale/Scope**:
- Single Proxmox host (not clustered)
- 3-10 LXC containers
- Terraform state: <20 MB (if repo path defined)
- Ansible repository: <100 MB (including roles, if repo path defined)
- Documentation: ~10 markdown files
- Backup retention: 30 daily + 12 monthly = 42 archives (~4 GB total)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### Compliance Assessment

✅ **I. Spec-Driven Workflow**
- Feature driven from `specs/013-proxmox-config-backup/spec.md`
- Tasks defined in `specs/013-proxmox-config-backup/tasks.md`
- All changes reference approved tasks
- Documentation updated alongside implementation

✅ **II. Secrets Policy**
- Age encryption key stored in Bitwarden (not in git)
- Key path configured in /etc/proxmox-backup.conf (deployed by Ansible from group_vars)
- Backup script scans for plaintext secrets in IaC artifacts (fails if found)
- SMTP credentials for notifications stored in Bitwarden (configured in /etc/proxmox-backup.conf)
- Tailscale state and rclone config backup opt-in only (default: false)
- No Proxmox tokens, passwords, or private keys in committed code

✅ **III. Separation of Concerns**
- **Terraform**: Not modified (manages LXC existence/sizing only)
- **Ansible**: Deploys backup script, config, systemd units (does NOT execute backup at runtime)
- **Bash Script**: Runtime backup execution (independent from Ansible)
- No mixing of responsibilities

✅ **Networking**
- Uses existing static IPs: Proxmox host (192.168.1.112), NAS (192.168.1.109)
- No IP scattering: NAS mount point defined in /etc/proxmox-backup.conf (deployed from group_vars)
- NFS mount uses local network (no Tailscale required for backup transfer)

✅ **Access Control**
- Ansible connects to Proxmox via SSH using existing keys (already configured)
- Backup script runs as root via systemd (required for /etc/pve access, homelab tradeoff)
- No public exposure (backups stay on local NAS)

✅ **State Management**
- Terraform state backed up to NAS (becomes backup content, not modified)
- Local Terraform state preserved (no remote backend introduced)

✅ **Storage**
- Synology NAS used for backup storage (existing infrastructure)
- NFS mount from Proxmox to NAS (consistent with existing pattern)
- No Ceph or unnecessary complexity

✅ **Workflow & Process**
- Non-destructive: Backups add files, rotation deletes old backups (no infrastructure changes)
- Manual restore procedure (no automated destructive actions)
- CI/CD not modified (feature is Proxmox host automation, not pipeline change)

✅ **Repo Layout**
- Documentation: `docs/operations/backups-proxmox-config.md` and `docs/operations/backups-proxmox-config-restore.md`
- Ansible role: `ansible/roles/proxmox_backup/`
- Ansible playbook: `ansible/playbooks/backup_proxmox.yml` (wrapper for role)
- Backup script: Deployed to `/usr/local/sbin/proxmox-config-backup` on PVE host
- Consistent with existing repository structure

### Verdict: ✅ NO VIOLATIONS

All constitution principles satisfied. Architecture follows Choice 3, Option A (local script runtime) for simplicity and independence from Ansible at runtime.

## Project Structure

### Documentation (this feature)

```text
specs/013-proxmox-config-backup/
├── spec.md                      # Feature specification (Architecture: Choice 3, Option A)
├── plan.md                      # This file (implementation plan)
├── tasks.md                     # Concrete implementation tasks (80 tasks)
└── checklists/
    └── requirements.md          # Specification quality validation
```

### Source Code (repository root)

```text
ansible/
├── roles/
│   └── proxmox_backup/          # NEW: Backup script deployment role
│       ├── defaults/
│       │   └── main.yml         # Default variables (NAS mount, retention, repo path, opt-ins)
│       ├── handlers/
│       │   └── main.yml         # Handlers (restart systemd timer if config changes)
│       ├── tasks/
│       │   ├── main.yml         # Main orchestration (prerequisites, deploy script, deploy config, install systemd)
│       │   ├── prerequisites.yml # Install age, zstd, verify nfs-common, verify util-linux (flock)
│       │   ├── deploy_script.yml # Deploy script template to /usr/local/sbin/proxmox-config-backup (mode 0750)
│       │   ├── deploy_config.yml # Deploy /etc/proxmox-backup.conf from template (NAS, keys, retention, repo path)
│       │   └── systemd.yml      # Deploy systemd timer/service units, enable timer
│       └── templates/
│           ├── proxmox-config-backup.sh.j2  # Bash script template (main runtime logic)
│           ├── proxmox-backup.conf.j2       # Configuration file template
│           ├── proxmox-backup.service.j2    # Systemd service unit (ExecStart=/usr/local/sbin/proxmox-config-backup)
│           └── proxmox-backup.timer.j2      # Systemd timer unit (OnCalendar=daily 02:00)
├── playbooks/
│   ├── backup_proxmox.yml       # NEW: Backup playbook wrapper (deploys proxmox_backup role to PVE host)
│   ├── test_backup.yml          # NEW: Integration test playbook (deploy script, run manually, verify)
│   └── site.yml                 # MODIFIED: Include proxmox_backup role for proxmox_hosts
└── group_vars/
    └── proxmox_hosts.yml        # MODIFIED: Add backup variables (NAS mount, age key path, schedule, repo path, opt-ins)

docs/
├── operations/
│   ├── backups-proxmox-config.md         # NEW: Main backup documentation (quickstart, manual execution, monitoring)
│   └── backups-proxmox-config-restore.md # NEW: Restore runbook (step-by-step per file type)

# NOTE: No scripts/ directory needed - backup script deployed to /usr/local/sbin/proxmox-config-backup on PVE host
# Script includes all runtime logic: collection, compression, encryption, transfer, rotation, verification, notification
```
└── operations/
    ├── backups-proxmox-config.md         # NEW: Backup setup, configuration, manual execution
    └── backups-proxmox-config-restore.md # NEW: Restore runbook (step-by-step)

# Synology NAS (target, not in repo)
/volume1/homelab_backups/proxmox/
├── proxmox-backup-20251222-020000.tar.zst.age    # Daily backups (30 retained)
├── proxmox-backup-20251222-020000.tar.zst.age.meta # Metadata (key fingerprint)
└── ...                                            # Monthly backups (12 retained)

# Proxmox host (ephemeral, not in repo)
/var/backups/proxmox-staging/
├── etc/
│   ├── pve/                     # LXC configs, storage.cfg
│   ├── network/                 # Network interfaces
│   ├── fstab                    # NFS mounts
│   └── ...
├── var/
│   └── lib/tailscale/           # Tailscale state
├── terraform/
│   └── terraform.tfstate        # Terraform state
├── ansible/
│   ├── inventories/             # Ansible inventory
│   ├── playbooks/               # Ansible playbooks
│   └── roles/                   # Ansible roles (task files only)
├── docs/                        # Documentation
└── manifest.txt                 # File manifest (paths, sizes, checksums)
```

**Structure Decision**:

This is an **infrastructure automation project** with **local script runtime** (Architecture: Choice 3, Option A). The structure follows these principles:

1. **Script-Based Runtime**: Core backup logic in bash script `/usr/local/sbin/proxmox-config-backup` deployed to PVE host. Script is independent from Ansible at runtime - uses strict mode (`set -euo pipefail`), flock for locking, journald for logging.

2. **Ansible for Deployment Only**: `ansible/roles/proxmox_backup/` deploys script template, configuration file (`/etc/proxmox-backup.conf`), systemd units, and required packages. Ansible does NOT execute backup logic at runtime.

3. **Configuration File Pattern**: `/etc/proxmox-backup.conf` contains runtime configuration (NAS mount point, age key path, retention policy, repo path, opt-in flags). Script sources this file at startup.

4. **Playbook Wrapper**: `ansible/playbooks/backup_proxmox.yml` provides simple entry point for deploying/updating backup infrastructure to Proxmox host.

5. **Documentation-First**: Restore runbook and operational procedures (manual script execution: `/usr/local/sbin/proxmox-config-backup`, verification: `proxmox-config-backup --verify <path>`) documented before implementation.

6. **Staging Pattern**: Script creates timestamped staging directory `/var/backups/proxmox-staging/<timestamp>/`, collects files, compresses+encrypts, transfers to NAS, then cleans up staging on success.

7. **Systemd Integration**: Timer runs script directly (`ExecStart=/usr/local/sbin/proxmox-config-backup`), not ansible-playbook. Native systemd management (`systemctl status proxmox-backup.timer`, `journalctl -u proxmox-backup.service`).

**No application source structure needed** - this is infrastructure automation with bash script runtime and Ansible-based deployment.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

**No violations** - table intentionally empty.

All constitution principles satisfied:
- ✅ Spec-driven workflow followed
- ✅ No secrets committed
- ✅ Terraform/Ansible separation maintained
- ✅ Existing architecture patterns followed
- ✅ No unnecessary complexity introduced

---

## Implementation Phases

### Phase 0: Prerequisites (Manual, Before Implementation)

**Purpose**: One-time setup tasks performed by operator before automation runs

**Tasks** (not automated, documented in `docs/operations/backups-proxmox-config.md`):

1. **NAS Share Creation**:
   - Log into Synology DSM
   - Create shared folder: `/volume1/homelab_backups/`
   - Enable NFS: Control Panel → File Services → NFS → Enable NFS service
   - Create NFS rule: Allow 192.168.1.112 (Proxmox host), Read/Write, Squash: No mapping

2. **Encryption Key Generation**:
   - Install age locally: `brew install age` (macOS) or `apt install age` (Linux)
   - Generate keypair: `age-keygen -o proxmox-backup.key`
   - Store private key in Bitwarden: Create secure note "Proxmox Backup Encryption Key"
   - Store public key in Bitwarden same note (for reference)
   - Test key: `echo "test" | age -r <public-key> | age -d -i proxmox-backup.key`

3. **NFS Mount Test**:
   - SSH to Proxmox host: `ssh root@192.168.1.112`
   - Test mount: `mount -t nfs 192.168.1.109:/volume1/homelab_backups /mnt/test`
   - Verify write: `touch /mnt/test/test.txt && rm /mnt/test/test.txt`
   - Unmount: `umount /mnt/test`

4. **Ansible Inventory Update**:
   - Add backup variables to `ansible/group_vars/proxmox_hosts.yml`:
     ```yaml
     proxmox_backup_enabled: true
     proxmox_backup_nas_host: "192.168.1.109"
     proxmox_backup_nas_path: "/volume1/homelab_backups/proxmox"
     proxmox_backup_age_key_path: "/root/.age/proxmox-backup.key"  # Where private key will be stored
     proxmox_backup_repo_path: "/root/homelab-proxmox"  # Path to IaC repo on PVE (if cloned/synced)
     proxmox_backup_schedule: "daily"
     proxmox_backup_time: "02:00"
     proxmox_backup_retention_daily: 30
     proxmox_backup_retention_monthly: 12
     proxmox_backup_include_tailscale_state: false  # Opt-in (default: false)
     proxmox_backup_include_rclone_conf: false      # Opt-in (default: false)
     proxmox_backup_notify_on_success: false        # Opt-in (default: false)
     proxmox_backup_smtp_host: ""                   # For email notifications
     proxmox_backup_email_to: ""                    # Notification recipient
     ```
   - Create git-ignored vars file: `ansible/group_vars/proxmox_hosts_secrets.yml`:
     ```yaml
     proxmox_backup_age_public_key: "<public-key-from-bitwarden>"
     proxmox_backup_age_private_key: "<private-key-from-bitwarden>"  # Deployed to PVE, never committed
     ```

**Checkpoint**: Manual prerequisites complete, ready for Phase 1 implementation

---

### Phase 1: Foundation (Tasks T001-T013)

**Purpose**: Ansible role structure, package installation, script deployment, configuration deployment

**Deliverables**:
- Ansible role structure created (`ansible/roles/proxmox_backup/`)
- age, zstd, and nfs-common installed on Proxmox host
- Backup script deployed to `/usr/local/sbin/proxmox-config-backup` (mode 0750, owner root:root)
- Configuration file deployed to `/etc/proxmox-backup.conf` (mode 0600, owner root:root)
- Staging directory structure ready (`/var/backups/proxmox-staging/`)
- Systemd timer and service units deployed

**Success Criteria**:
- Role structure exists with all subdirectories (tasks, templates, defaults)
- `age --version` and `zstd --version` succeed on Proxmox host
- `/usr/local/sbin/proxmox-config-backup` exists and is executable
- `/etc/proxmox-backup.conf` exists with correct permissions (0600)
- Script uses `set -euo pipefail`, flock for locking, journald for logging
- Script includes all required functions: collect_*, compress_*, encrypt_*, transfer_*, rotate_*, cleanup_*

**Validation**:
```bash
# On Proxmox host
age --version  # Should show 1.1.0+
zstd --version # Should show 1.5.0+
ls -l /usr/local/sbin/proxmox-config-backup  # Should show -rwxr-x--- root root
ls -l /etc/proxmox-backup.conf              # Should show -rw------- root root
head -5 /usr/local/sbin/proxmox-config-backup | grep "set -euo pipefail"  # Should match
```

**Timeline**: 1-2 days (role structure + script template development)

---

### Phase 2: User Story 1 - Basic Backup (Tasks T014-T027)

**Purpose**: Core backup functionality - implement script functions for Proxmox configs collection, compression, encryption, transfer

**Deliverables**:
- Script functions implemented: collect_proxmox_configs(), collect_network(), collect_fstab()
- Optional collection functions with guards: collect_tailscale_state(), collect_rclone_conf()
- Manifest generation: generate_manifest() with SHA256 hashes
- Compression: compress_staging() creates tar.zst
- Encryption: encrypt_archive() uses age with public key
- Transfer: mount_nas(), transfer_to_nas(), set_permissions()
- Cleanup: cleanup_staging() removes timestamped staging dir
- Orchestration: main() with flock, trap handlers, journald logging, exit codes

**Success Criteria**:
- All critical Proxmox config files collected to timestamped staging directory
- tar.zst archive created with all staging contents
- age encryption produces .tar.zst.age file with timestamped name
- Encrypted archive transferred to NAS at correct path
- Staging directory removed after successful transfer
- Archive decryptable with private key
- journalctl shows structured log entries for backup run

**Validation**:
```bash
# Run backup manually on Proxmox host
/usr/local/sbin/proxmox-config-backup

# Check NAS
ssh root@192.168.1.109
ls -lh /volume1/homelab_backups/proxmox/
# Should show: proxmox-backup-YYYYMMDD-HHMMSS.tar.zst.age (~50-100 MB)

# Decrypt and verify (on laptop with private key)
age -d -i proxmox-backup.key proxmox-backup-*.tar.zst.age | tar -tzstf - | head
# Should show: etc/pve/lxc/101.conf, etc/network/interfaces, etc/fstab, etc/...
```

**Timeline**: 2-3 days

**Checkpoint**: **MVP COMPLETE** - basic backup proven, manual execution works

---

### Phase 3: User Story 2 - IaC Artifacts (Tasks T029-T038)

**Purpose**: Add Terraform state and Ansible inventory/playbooks to backup

**Deliverables**:
- Terraform state collection (terraform.tfstate, terraform.tfstate.backup)
- Ansible inventory collection (inventories/generated/hosts.yml, group_vars, host_vars)
- Ansible playbook collection (playbooks/*.yml)
- Ansible role tasks collection (roles/*/tasks/*.yml)
- Documentation collection (README.md, docs/operations/, docs/runbooks/)
- Exclusion filters (.git/, .terraform/, node_modules/, __pycache__/)
- IaC verification (state file size > 0, inventory valid YAML)

**Success Criteria**:
- terraform.tfstate exists in archive
- Ansible inventory files exist in archive
- `terraform plan` shows zero diff after restoring state from backup
- `ansible-playbook site.yml --check` shows zero changes after restoring inventory
- No .git/ directory in archive (git history excluded)
- No .terraform/ directory in archive (plugins excluded)

**Validation**:
```bash
# Decrypt and check IaC artifacts
age -d -i proxmox-backup.key proxmox-backup-*.tar.zst.age | tar -tzstf - | grep -E "terraform.tfstate|inventories/generated"

# Restore and validate
mkdir -p /tmp/restore-test
age -d -i proxmox-backup.key proxmox-backup-*.tar.zst.age | tar -xzstf - -C /tmp/restore-test
cd /tmp/restore-test/terraform
terraform plan  # Should show: No changes. Your infrastructure matches the configuration.

cd /tmp/restore-test/ansible
ansible-playbook playbooks/site.yml --check  # Should show: ok=N changed=0
```

**Timeline**: 2 days

---

### Phase 4: User Story 3 - Automation (Tasks T039-T048)

**Purpose**: Systemd timer for scheduled execution, rotation policy implementation

**Deliverables**:
- Systemd service unit (executes backup playbook as root)
- Systemd timer unit (OnCalendar=daily at 02:00)
- Timer/service deployment via Ansible
- Timer enabled and started
- Rotation policy (30 daily backups)
- Monthly backup preservation (12 monthly: first backup of each month)
- Pre-backup rotation (delete old before creating new)
- Safety check (preserve at least 1 backup even if policy deletes)
- Rotation logging (deleted filenames, reason, timestamp)
- Idempotency verification (running twice creates new backup only)

**Success Criteria**:
- `systemctl status proxmox-backup.timer` shows active and enabled
- Timer runs daily at 2 AM
- After 48 hours, two dated backups exist on NAS
- After 30 days, exactly 30 daily backups exist (rotation working)
- First backup of each month preserved even if >30 days old
- At least 1 backup always preserved even if rotation policy triggers
- Running backup twice in quick succession creates two backups with different timestamps

**Validation**:
```bash
# On Proxmox host
systemctl status proxmox-backup.timer  # Should show: Active: active (waiting)
systemctl list-timers --all | grep proxmox-backup  # Should show next trigger time

# Check timer logs
journalctl -u proxmox-backup.timer --since today

# Simulate 48 hours (or wait)
# Check NAS
ssh root@192.168.1.109
ls -lt /volume1/homelab_backups/proxmox/ | head -3
# Should show two backups with different timestamps

# Test rotation (simulate 35 daily backups)
# Create dummy files: proxmox-backup-20251101-020000.tar.zst.age through proxmox-backup-20251205-020000.tar.zst.age
# Run backup
ansible-playbook ansible/playbooks/backup_proxmox.yml
# Check rotation log
grep "Rotation:" /var/log/proxmox-backup.log
# Should show: Deleted backups older than 30 days, preserved monthly backups
```

**Timeline**: 2 days

---

### Phase 5: User Story 4 - Verification (Tasks T049-T056)

**Purpose**: Integrity checking without full restore, post-backup validation

**Deliverables**:
- Verification script (decrypt, list, validate checksums)
- Post-backup verification task (runs after transfer)
- Checksum generation in manifest (SHA256 for each file)
- Checksum validation in verification script
- Verification integrated into backup workflow (fail if post-verification fails)
- Verification logging (success/failure, files verified, duration)
- Exit code handling (0=success, 1=decrypt fail, 2=checksum mismatch, 3=missing files)
- Verification documentation (command usage, exit codes, troubleshooting)

**Success Criteria**:
- Verification script decrypts archive without extraction
- Verification lists all expected files (LXC configs, Terraform state, inventory)
- Verification validates checksums against manifest
- Verification completes in <60 seconds
- Corrupted backup detected (manually truncate file, run verify, should fail with exit 2)
- Post-backup verification fails backup if corruption detected

**Validation**:
```bash
# Run verification
time ./scripts/backup/verify_proxmox_backup.sh \
  /path/to/proxmox-backup-*.tar.zst.age \
  /path/to/proxmox-backup.key

# Should output:
# ✓ Decryption successful
# ✓ Archive listing complete (234 files)
# ✓ Checksum validation: 234/234 passed
# ✓ Verification complete (elapsed: 23s)
# Exit code: 0

# Test corruption detection
cp proxmox-backup-*.tar.zst.age corrupted.tar.zst.age
truncate -s 50M corrupted.tar.zst.age  # Simulate corruption
./scripts/backup/verify_proxmox_backup.sh corrupted.tar.zst.age proxmox-backup.key
# Should output:
# ✗ Checksum validation failed: 12/234 files mismatch
# Exit code: 2
```

**Timeline**: 2 days

---

### Phase 6: User Story 5 - Notifications (Tasks T057-T064)

**Purpose**: Email alerts on backup failure (optional success emails)

**Deliverables**:
- Email notification template (subject, body with error/success details)
- Email sender task (uses SMTP credentials from Bitwarden/Kuma)
- Failure notification in error handler (catches failures, sends email with context)
- Backup metrics in notification (size, duration, file count, checksum)
- Optional success notification (configurable, default: false)
- Specific failure type notifications (NFS mount fail, encryption fail, disk full, verification fail)
- Notification configuration in group_vars (SMTP host, port, from/to, enable/disable)
- Notification documentation (setup, testing, troubleshooting)

**Success Criteria**:
- Failure email sent within 5 minutes of backup failure
- Email subject: "Proxmox Backup Failed: <hostname>"
- Email body includes: error type, timestamp, log excerpt, remediation steps
- Success email (if enabled) includes: backup filename, size, file count, SHA256 checksum, duration
- Notification configuration in `ansible/group_vars/proxmox_hosts.yml`

**Validation**:
```bash
# Simulate NFS mount failure
ssh root@192.168.1.112
umount /mnt/backup-nas  # Unmount NFS share

# Trigger backup
ansible-playbook ansible/playbooks/backup_proxmox.yml

# Check email (within 5 minutes)
# Subject: Proxmox Backup Failed: pve
# Body:
#   Error: NFS mount failed (192.168.1.109:/volume1/homelab_backups/proxmox)
#   Timestamp: 2025-12-22 02:00:15
#   Log excerpt: [mount error details]
#   Remediation: Check NAS availability, verify NFS service running, check network connectivity

# Test success notification (enable in group_vars)
# Edit ansible/group_vars/proxmox_hosts.yml:
#   proxmox_backup_notify_on_success: true
# Run backup
ansible-playbook ansible/playbooks/backup_proxmox.yml
# Check email
# Subject: Proxmox Backup Successful: pve
# Body:
#   Backup: proxmox-backup-20251222-143052.tar.zst.age
#   Size: 87 MB
#   Files: 234
#   Checksum: sha256:a7f3d2c8e1b4...
#   Duration: 8m 23s
```

**Timeline**: 2 days

---

### Phase 7: Polish & Documentation (Tasks T065-T080)

**Purpose**: Restore runbook, edge case handling, monitoring integration, final docs

**Deliverables**:
- Comprehensive restore runbook (step-by-step for each file type)
- Break-glass encryption key recovery documentation
- Manual backup execution documentation
- Quickstart guide (one-time setup, first backup)
- Retry logic for /etc/pve access (exponential backoff, max 3 attempts)
- NFS mount validation before backup
- Disk space check before backup (staging: 1 GB, NAS: 200 MB)
- Graceful failure handling (preserve previous backup, no partial archives)
- Encryption key fingerprint in metadata (.meta file alongside archive)
- Secret exclusion verification (scan for API keys, tokens, passwords in plaintext)
- Backup size monitoring (warning if >200 MB, error if >500 MB)
- Key rotation procedure documentation
- Integration test playbook (run backup, verify archive, decrypt, validate)
- Uptime Kuma monitoring check documentation (latest backup timestamp check)
- Main README.md update (backup feature summary)
- site.yml update (include proxmox_backup role)

**Success Criteria**:
- Restore runbook exists with clear prerequisites, step-by-step instructions, verification steps
- Edge cases documented and handled (NFS unavailable, disk full, /etc/pve unavailable, concurrent execution)
- Backup size warnings logged if >200 MB
- Integration test playbook runs successfully
- README.md includes backup feature section with restore pointer

**Validation**:
```bash
# Test restore procedure (on fresh Proxmox VM)
# Follow docs/operations/backups-proxmox-config-restore.md
# 1. Install fresh Proxmox VE 8.x
# 2. Retrieve encryption key from Bitwarden
# 3. Download latest backup from NAS
# 4. Decrypt: age -d -i proxmox-backup.key proxmox-backup-*.tar.zst.age > backup.tar.zst
# 5. Extract: tar -xzstf backup.tar.zst -C /tmp/restore
# 6. Restore LXC configs: cp /tmp/restore/etc/pve/lxc/*.conf /etc/pve/lxc/
# 7. Restore network: cp /tmp/restore/etc/network/interfaces /etc/network/interfaces
# 8. Restore fstab: cp /tmp/restore/etc/fstab /etc/fstab
# 9. Verify: pct list (should show LXCs), ip a (should show network config)

# Test integration
ansible-playbook ansible/playbooks/test_backup.yml
# Should: Run backup → verify archive exists → decrypt → validate contents → cleanup
```

**Timeline**: 3-4 days

---

## Risk Mitigation

### Technical Risks

**RISK-001: /etc/pve race conditions (Medium)**
- **Mitigation Implemented**: Retry logic with exponential backoff (tasks T069)
  - Max 3 attempts: 0s, 2s, 4s delays
  - Log warning if retry succeeded
  - Fail with error if all attempts exhausted
- **Testing**: Simulate /etc/pve unavailability, verify retry behavior

**RISK-002: NFS mount unavailability (Low)**
- **Mitigation Implemented**: Pre-backup mount validation (tasks T070)
  - Check mount exists: `mountpoint -q /mnt/backup-nas`
  - Check mount writable: `touch /mnt/backup-nas/.writetest && rm /mnt/backup-nas/.writetest`
  - Graceful failure: Log error, send notification, preserve previous backup
- **Testing**: Unmount NFS, run backup, verify failure notification

**RISK-003: Encryption key loss (High)**
- **Mitigation Implemented**: Break-glass documentation (tasks T066)
  - Paper backup procedure documented
  - Quarterly key recovery drill (separate from backup automation)
  - Bitwarden export procedure documented
- **Testing**: Key recovery drill (restore key from paper backup, decrypt old archive)

**RISK-004: Backup size growth (Low)**
- **Mitigation Implemented**: Size monitoring (tasks T075)
  - Log warning if >200 MB
  - Log error if >500 MB
  - Investigate large artifacts (documentation includes analysis steps)
- **Testing**: Create large dummy file in staging, verify warning logged

### Operational Risks

**RISK-005: Key rotation forgotten (Medium)**
- **Mitigation Implemented**: Key rotation documentation (tasks T076)
  - Generate new key procedure
  - Test decrypt old backup with new key
  - Update Bitwarden procedure
  - Label backup versions by key fingerprint (.meta file)
- **Testing**: Simulate key rotation, verify old backups still decryptable

**RISK-006: Silent notification failures (Medium)**
- **Mitigation Implemented**: Uptime Kuma integration (tasks T078)
  - Monitor latest backup timestamp on NAS
  - Alert if >36 hours old (should be daily)
  - Test notification delivery during setup
- **Testing**: Stop SMTP service, trigger backup failure, verify Kuma alert

**RISK-007: Outdated restore procedure (High)**
- **Mitigation Implemented**: Quarterly restore drill (documented in spec)
  - Not automated (separate manual testing)
  - Documented in runbook with checklist
  - Update runbook based on drill findings
- **Testing**: Schedule quarterly drill (January 2026), document findings

---

## Testing Strategy

### Unit Testing (Per-Task Validation)

Each Ansible task includes assertions and validation:
- `assert` module for prerequisites (age installed, staging dir exists)
- `stat` module for file existence checks
- `command` module with `failed_when` for external commands
- `debug` module with `var` for troubleshooting

**Example** (from `ansible/roles/proxmox_backup/tasks/prerequisites.yml`):
```yaml
- name: Verify age is installed
  command: age --version
  register: age_version
  failed_when: age_version.rc != 0
  changed_when: false

- name: Assert age version is 1.1.0+
  assert:
    that:
      - age_version.stdout is search("age 1\\.[1-9]")
    fail_msg: "age version must be 1.1.0+, found {{ age_version.stdout }}"
```

### Integration Testing (Full Backup Cycle)

**Test Playbook**: `ansible/playbooks/test_backup.yml`

**Steps**:
1. Run backup playbook
2. Verify archive exists on NAS
3. Download archive
4. Decrypt with test key
5. List contents
6. Validate manifest checksums
7. Extract sample files
8. Compare with source files
9. Cleanup test artifacts

**Success Criteria**:
- All steps pass without errors
- Archive size within expected range (50-150 MB)
- All expected files present in archive
- Checksums match manifest
- Sample files identical to source

**Execution**:
```bash
ansible-playbook ansible/playbooks/test_backup.yml --extra-vars "backup_test_mode=true"
```

### Restore Testing (Quarterly Drill)

**Not automated** - manual procedure documented in `docs/operations/backups-proxmox-config-restore.md`

**Drill Checklist**:
1. Provision fresh Proxmox VM (separate from production)
2. Retrieve encryption key from Bitwarden
3. Download latest backup from NAS
4. Decrypt backup
5. Extract backup to temporary directory
6. Restore LXC configs to /etc/pve/lxc/
7. Restore network config to /etc/network/interfaces
8. Restore fstab to /etc/fstab
9. Restore Tailscale config
10. Verify LXCs appear in Proxmox UI
11. Verify network configuration correct
12. Verify NFS mounts defined
13. Restore Terraform state to local repo
14. Run `terraform plan` - verify zero diff
15. Restore Ansible inventory to local repo
16. Run `ansible-playbook site.yml --check` - verify zero changes
17. Document drill findings
18. Update restore runbook if issues found

**Frequency**: Quarterly (January, April, July, October)

**Owner**: Homelab operator (manual execution)

---

## Timeline & Milestones

### Week 1: MVP (Phases 0-2)
- **Day 1**: Manual prerequisites (NAS setup, key generation) + Phase 1 (foundation)
- **Days 2-3**: Phase 2 (User Story 1 - basic backup)
- **Day 4**: MVP validation and testing
- **Milestone**: Manual backup execution works end-to-end, encrypted archive on NAS

### Week 2: Automation & IaC (Phases 3-4)
- **Days 1-2**: Phase 3 (User Story 2 - IaC artifacts)
- **Days 3-4**: Phase 4 (User Story 3 - systemd timer + rotation)
- **Day 5**: Integration testing
- **Milestone**: Automated daily backups running, rotation enforced

### Week 3: Reliability (Phases 5-6)
- **Days 1-2**: Phase 5 (User Story 4 - verification)
- **Days 3-4**: Phase 6 (User Story 5 - notifications)
- **Day 5**: Edge case testing
- **Milestone**: Backup reliability established (verification + monitoring)

### Week 4: Polish & Docs (Phase 7)
- **Days 1-2**: Restore runbook + quickstart documentation
- **Days 3-4**: Edge case handling + monitoring integration
- **Day 5**: Final integration test + feature completion
- **Milestone**: Feature complete, ready for production use

**Total Timeline**: 4 weeks (3-4 weeks of focused work)

**Effort Estimate**: 80-100 hours

---

## Success Metrics (Post-Implementation)

### Performance Metrics
- ✅ Backup completion time: Measure over 7 days, target <10 minutes average
- ✅ Archive size: Measure over 7 days, target <100 MB average
- ✅ Verification time: Measure over 7 days, target <60 seconds average
- ✅ Rotation scan time: Measure weekly, target <30 seconds

### Reliability Metrics
- ✅ Backup success rate: Measure over 30 days, target 100% (zero failed backups)
- ✅ Verification success rate: Measure over 30 days, target 100% (zero corrupted archives)
- ✅ Timer reliability: Measure over 30 days, verify daily execution at 2 AM

### Quality Metrics
- ✅ Terraform plan diff: Zero changes after state restore
- ✅ Ansible check mode: Zero changes after inventory restore
- ✅ Secret exposure: Zero plaintext secrets in logs, staging, or NAS
- ✅ Restore time: <2 hours from fresh Proxmox install to verified configuration

### Operational Metrics
- ✅ NAS storage usage: Monitor over 60 days, verify stable ~4 GB (42 backups @ ~100 MB)
- ✅ Failure detection time: Measure notification latency, target <10 minutes
- ✅ Manual execution reliability: Document any issues encountered during quarterly drills

**Review Cadence**:
- Weekly for first month (performance/reliability)
- Monthly thereafter (operational)
- Quarterly drill results (quality/restore validation)

---

## Deployment Checklist

### Pre-Deployment Validation
- [ ] Manual prerequisites complete (NAS share, encryption key, NFS test)
- [ ] Ansible inventory updated with backup variables
- [ ] Git-ignored secrets file created with age public key
- [ ] Backup role structure exists
- [ ] Integration test playbook passes
- [ ] Documentation complete (setup, restore runbook, quickstart)

### Deployment Steps
1. [ ] Commit all changes to feature branch (013-proxmox-config-backup)
2. [ ] Create PR with comprehensive description (link spec, tasks, validation results)
3. [ ] Review constitution compliance (checklist in PR)
4. [ ] Merge PR to main
5. [ ] Pull latest main on Ansible control machine
6. [ ] Run backup playbook manually first time: `ansible-playbook ansible/playbooks/backup_proxmox.yml`
7. [ ] Verify backup on NAS: `ssh root@192.168.1.109 ls -lh /volume1/homelab_backups/proxmox/`
8. [ ] Verify systemd timer active: `ssh root@192.168.1.112 systemctl status proxmox-backup.timer`
9. [ ] Enable monitoring in Uptime Kuma (check latest backup timestamp)
10. [ ] Schedule first quarterly restore drill (January 2026)

### Post-Deployment Monitoring
- [ ] Day 1: Verify first automated backup ran (check timer logs)
- [ ] Day 2: Verify second backup exists (rotation working)
- [ ] Day 7: Review backup logs (any errors/warnings?)
- [ ] Day 30: Verify rotation (exactly 30 daily backups on NAS)
- [ ] Day 60: Verify monthly preservation (first backup of previous month retained)

---

## Maintenance & Evolution

### Regular Maintenance Tasks
- **Daily**: Automated backup execution (systemd timer)
- **Weekly**: Review backup logs for warnings/errors
- **Monthly**: Verify rotation policy working (backup count on NAS)
- **Quarterly**: Restore drill (test procedure, update runbook)
- **Annually**: Encryption key rotation (optional, documented procedure)

### Future Enhancements (Post-MVP)
- **FUP-001**: Offsite backup replication (sync to cloud storage)
- **FUP-002**: Automated restore testing (quarterly drill automation)
- **FUP-003**: Backup metrics dashboard (Prometheus/Grafana)
- **FUP-004**: Incremental backups (rsync-based)
- **FUP-005**: Backup integrity monitoring (bit rot detection)
- **FUP-006**: Multi-site backup (second NAS at different location)
- **FUP-007**: Immutable backups (NAS snapshots, ransomware protection)
- **FUP-008**: Key rotation automation (re-encrypt all backups)
- **FUP-009**: Router config backup (UniFi/pfSense)
- **FUP-010**: Web UI (backup history, manual trigger, download)

### Evolution Criteria
Feature is considered **production-ready** when:
- ✅ All 5 user stories implemented and validated
- ✅ 30 consecutive days of successful automated backups
- ✅ First quarterly restore drill completed successfully
- ✅ All success criteria (SC-001 through SC-010) met
- ✅ Documentation complete and validated by operator

Feature is considered **mature** when:
- ✅ 90 consecutive days of successful automated backups
- ✅ Three quarterly restore drills completed successfully
- ✅ Zero operational issues requiring manual intervention
- ✅ Monitoring integration complete (Uptime Kuma)
- ✅ Operator comfortable with manual backup execution and restore procedure

At maturity, consider prioritizing follow-up features based on operational needs.
