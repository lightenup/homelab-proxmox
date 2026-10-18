# Rebuild Orchestrator - Idempotent Restore Runbook

**Purpose**: Restore a Proxmox VE host from bare metal to fully operational homelab
**Audience**: Operators performing system restoration or validation
**Idempotency**: Safe to run multiple times - no changes applied if system already in desired state
**Created**: 2026-02-10

---

## Overview

This runbook guides you through **restoring** your homelab infrastructure using the idempotent rebuild orchestrator. Start with a fresh Proxmox VE 9 installation and end with a fully operational system with all services running.

**What This Does**:
- ✅ Restores LXC containers from backup archives
- ✅ Rebuilds infrastructure using NAS-backed Terraform state
- ✅ Configures services with environment isolation (lab/prod)
- ✅ Validates and remediates mount configurations
- ✅ Executes from laptop (no SSH required after prerequisites)
- ✅ **Idempotent**: Only applies changes needed to reach desired state

**What This Is NOT**:
- ❌ NAS data restoration from Hetzner backups (see [backups-proxmox-config-restore.md](../operations/backups-proxmox-config-restore.md))
- ❌ Initial NAS infrastructure setup
- ❌ Network/DNS configuration

**Starting Point**: Fresh Proxmox VE 9 installation with network configured
**Ending Point**: Fully operational homelab with all services healthy
**Timeline**: 1-2 hours for complete restoration (lab or prod)

---

## Prerequisites Checklist

Before starting restoration, verify these requirements:

### 1. Laptop Requirements

- [ ] **macOS laptop** with network access to PVE and NAS
- [ ] **Repository cloned** at `/Users/<you>/Development/private/homelab-proxmox`
- [ ] **SSH access to PVE**: `ssh pve` works without password
- [ ] **Network connectivity**: Laptop on same network as PVE (192.168.1.0/24)

### 2. NAS Infrastructure

Verify NAS is accessible and contains state from previous deployment:

```bash
# Check NAS directories exist
ssh pve "ls -ld /mnt/nas/homelab_ci/infra_state/{lab,prod}/"

# Expected output (if restoring existing system):
# drwxr-xr-x 9 1024 users 4096 /mnt/nas/homelab_ci/infra_state/lab/
# drwxr-xr-x 6 1024 users 4096 /mnt/nas/homelab_ci/infra_state/prod/

# If directories don't exist, orchestrator will create them during first run
```

- [ ] **NAS accessible from PVE**: `/mnt/nas/homelab_ci/` mounted
- [ ] **State directories exist** (or can be created): `lab/` and `prod/`
- [ ] **Previous state available** (if restoring existing environment)

### 3. Credentials Required

- [ ] **Proxmox API Token** (Bitwarden: "Proxmox API Token - Rebuild")
  - Token ID: `root@pam!rebuild`
  - Token Secret: (retrieve from Bitwarden)
  - **Setup guide**: [proxmox-api-token-setup.md](./proxmox-api-token-setup.md)
- [ ] **Age Encryption Key** (if testing with real backups)
  - Bitwarden: "Proxmox Backup Age Key"

### 4. Backup Archive

**Required for full restoration** (skip if only validating existing system):

- [ ] **Backup archive extracted** on PVE at `/root/restore-YYYYMMDD/`
- [ ] **Backup contains**:
  - LXC configurations in `lxc-configs/`
  - IaC artifacts in `iac-artifacts/` (optional, NAS state preferred)

**If no backup needed**: Use `--phase mounts --phase services --phase verify` to skip the restore and iac phases

---

## Part 1: Laptop Setup (One-Time)

### Step 1.1: Configure NFS Mount

**Reference**: [laptop-nfs-setup.md](./laptop-nfs-setup.md)

> **Important**: macOS autofs uses a **direct map** (`/-`) approach.
> See [laptop-nfs-setup.md](./laptop-nfs-setup.md) for full details.

**Create autofs direct map** (`/etc/auto_nfs`):
```bash
sudo tee /etc/auto_nfs <<'EOF'
/Volumes/nas/homelab_ci  -fstype=nfs,rw,nfsvers=3,resvport  192.168.1.109:/volume1/homelab_ci
/Volumes/nas/homelab_dr_test  -fstype=nfs,rw,nfsvers=3,resvport  192.168.1.109:/volume1/homelab_dr_test
/Volumes/nas/homelab_backups  -fstype=nfs,rw,nfsvers=3,resvport  192.168.1.109:/volume1/homelab_backups
EOF
```

> **Warning**: No blank lines in `/etc/auto_nfs` — macOS stops parsing at the first blank line.

**Register direct map in auto_master**:
```bash
# Add this line to /etc/auto_master:
/-    auto_nfs
```

**Reload automount**:
```bash
sudo automount -vc
```

**Expected output**:
```
automount: /net updated
automount: /home updated
automount: /Volumes/nas/homelab_ci updated
automount: /Volumes/nas/homelab_dr_test updated
automount: /Volumes/nas/homelab_backups updated
automount: no unmounts
```

### Step 1.2: Validate NFS Access

```bash
# Test 1: Mount triggers on access
ls /Volumes/nas/homelab_ci/infra_state/

# Expected: lab/ prod/
```

```bash
# Test 2: Lab state accessible
ls /Volumes/nas/homelab_ci/infra_state/lab/

# Expected: 6+ directories (homeassistant, immich, jellyfin, monitoring, reverse_proxy, ansible)
```

```bash
# Test 3: Write access works
touch /Volumes/nas/homelab_ci/infra_state/lab/.test-$(date +%s) && \
  rm /Volumes/nas/homelab_ci/infra_state/lab/.test-*

# Expected: No error
```

**✅ Checkpoint**: NFS mount configured and working

### Step 1.3: Configure Proxmox API Credentials

**Reference**: [proxmox-api-token-setup.md](./proxmox-api-token-setup.md)

**Retrieve credentials from Bitwarden**:
1. Open Bitwarden
2. Search for "Proxmox API Token - Rebuild"
3. Copy Token ID and Token Secret

**Export environment variables** (in your working terminal):
```bash
# Use single quotes to avoid zsh history expansion (!)
export PROXMOX_API_TOKEN_ID='root@pam!rebuild'
export PROXMOX_API_TOKEN_SECRET='<paste secret from Bitwarden>'

# Verify export worked
echo "Token ID: $PROXMOX_API_TOKEN_ID"
echo "Token Secret: ${PROXMOX_API_TOKEN_SECRET:0:20}..." # Show first 20 chars only
```

**Test API access**:
```bash
# Test authentication to PVE API
curl -k -H "Authorization: PVEAPIToken=$PROXMOX_API_TOKEN_ID=$PROXMOX_API_TOKEN_SECRET" \
  https://192.168.1.112:8006/api2/json/version

# Expected: JSON response with PVE version info
```

**✅ Checkpoint**: API credentials configured and validated

### Step 1.4: Enable NAS State Mode

```bash
export USE_NAS_STATE=true
export ENVIRONMENT=lab

# Verify state library works
bash -c 'source scripts/lab/lib/state.sh && resolve_state_root'

# Expected: /Volumes/nas/homelab_ci/infra_state/lab
```

**✅ Checkpoint**: State library configured

---

## Part 2: Lab Environment Restoration

### Step 2.1: Phase 1 - Mounts Validation

**Purpose**: Verify mount checks and auto-remediation

```bash
# Run mounts phase only
task rebuild:plan -- --phase mounts --environment lab
```

**Expected Output**:
```
[INFO] Phase: mounts
[INFO] Running mount validation checks...
[PASS] MNT-001: Host mount /mnt/nas/homelab_immich exists
[PASS] MNT-002: Host mount /mnt/nas/photo exists
[PASS] MNT-003: Immich LXC mp0 bind mount configured
[PASS] MNT-004: Immich LXC mp1 bind mount configured
...
Phase: mounts - Status: completed
```

**If mount check fails**:
- Auto-remediation should trigger (`task ansible:mounts`)
- Check re-runs automatically
- Evidence at: `artifacts/rebuild-runs/<run_id>/reports/mounts/`

**✅ Validation**:
- [ ] All mount checks pass
- [ ] Evidence files created in artifacts/
- [ ] No manual intervention needed

### Step 2.2: Phase 2 - State Library Resolution

**Purpose**: Verify state path resolution works from laptop

```bash
# Test state paths manually
USE_NAS_STATE=true ENVIRONMENT=lab bash -c '
  source scripts/lab/lib/state.sh
  echo "State root: $(resolve_state_root)"
  echo "Monitoring state: $(get_service_state_path monitoring)"
  echo "Inventory path: $(get_inventory_path)"
'
```

**Expected Output**:
```
State root: /Volumes/nas/homelab_ci/infra_state/lab
Monitoring state: /Volumes/nas/homelab_ci/infra_state/lab/monitoring/terraform.tfstate
Inventory path: /Volumes/nas/homelab_ci/infra_state/lab/ansible/inventories/generated/hosts.yml
```

**✅ Validation**:
- [ ] Paths use `/Volumes/nas/` (macOS detection working)
- [ ] Environment is `lab`
- [ ] All functions return expected paths

### Step 2.3: Phase 3 - Restore Phase (LXC Containers)

**Purpose**: Restore LXC containers from backup archive

**Note**: Skip this phase if you're only validating an existing system (no restoration needed)

```bash
# First run: Use plan mode to see what would be restored
task rebuild:plan -- --phase restore --environment lab --backup-dir /root/restore-YYYYMMDD

# If output looks correct, run apply mode
task rebuild:apply -- --phase restore --environment lab --backup-dir /root/restore-YYYYMMDD
```

**Expected Output**:
```
[INFO] Phase: restore
[INFO] Restoring LXC configurations from backup...
[INFO] Found 6 containers to restore
[PASS] LXC-001: Container immich restored (CTID: 100)
[PASS] LXC-002: Container monitoring restored (CTID: 101)
...
Phase: restore - Status: completed
```

**✅ Validation**:
- [ ] All containers restored successfully
- [ ] No errors during LXC creation
- [ ] Containers visible in Proxmox UI
- [ ] Evidence artifacts created

**Idempotency Note**: If containers already exist with correct configuration, phase reports "no changes needed"

### Step 2.4: Phase 4 - Services Phase (Infrastructure as Code)

**Purpose**: Apply infrastructure configuration using Terraform from laptop

**Idempotency**: Terraform only applies changes needed to reach desired state. If infrastructure matches state, no changes are made.

```bash
# First: Plan mode to preview changes
task rebuild:plan -- --phase services --environment lab

# If changes look correct: Apply mode
task rebuild:apply -- --phase services --environment lab
```

**Expected Output (Apply Mode)**:
```
[INFO] Phase: services
[INFO] Processing service: immich (mode: apply)
[INFO] State path: /Volumes/nas/homelab_ci/infra_state/lab/immich/terraform.tfstate
Terraform initialized
Terraform apply output...
Apply complete! Resources: 2 added, 1 changed, 0 destroyed.
[PASS] SRV-001: Service immich deployed successfully
[INFO] Processing service: monitoring (mode: apply)
...
Phase: services - Status: completed
```

**✅ Validation**:
- [ ] All services configured successfully
- [ ] State written to NAS (survives host rebuild)
- [ ] Services accessible (check URLs/ports)
- [ ] Evidence logs at: `artifacts/rebuild-runs/<run_id>/reports/services/<service>.log`

**Idempotency Note**: If infrastructure already matches desired state:
```
[INFO] Service immich: No changes needed (0 to add, 0 to change, 0 to destroy)
```

**Common Issues**:

**Issue**: `ERROR: NAS mount not found`
```bash
# Fix: Verify NFS mount
ls /Volumes/nas/homelab_ci/
sudo automount -vc
```

**Issue**: `ERROR: Cannot write to state root`
```bash
# Fix: Check NAS permissions
ls -la /Volumes/nas/homelab_ci/infra_state/lab/
# Verify write access with test file
```

**Issue**: `Terraform authentication failed`
```bash
# Fix: Re-export credentials (use single quotes for zsh)
export PROXMOX_API_TOKEN_ID='root@pam!rebuild'
export PROXMOX_API_TOKEN_SECRET='<from Bitwarden>'
```

### Step 2.5: Phase 5 - Verify Phase

**Purpose**: Validate service health and inventory

```bash
# Run verify phase
task rebuild:plan -- --phase verify --environment lab
```

**Expected Output**:
```
[INFO] Phase: verify
[INFO] Running service health checks...
[PASS] Service immich is healthy
[PASS] Service monitoring is healthy
...
[INFO] Updating Ansible inventory...
Phase: verify - Status: completed
```

**✅ Validation**:
- [ ] All services report healthy
- [ ] Inventory updated
- [ ] Evidence artifacts complete

### Step 2.6: Complete Lab Restoration (All Phases)

**Purpose**: Complete restoration from PVE 9 bare metal to operational system

```bash
# First: Preview entire restoration
task rebuild:plan -- --environment lab --backup-dir /root/restore-YYYYMMDD

# If preview looks correct: Execute full restoration
task rebuild:apply -- --environment lab --backup-dir /root/restore-YYYYMMDD
```

**Expected Output (Apply Mode)**:
```
[INFO] Rebuild orchestrator starting
[INFO] Mode: apply
[INFO] Environment: lab
[INFO] Backup directory: /root/restore-20260210

Preflight Summary:
- Total phases: 5 (mounts, restore, iac, services, verify)
- Evidence directory: artifacts/rebuild-runs/rebuild-20260210-123456/

[INFO] Phase 1/5: mounts - STARTING
[PASS] All mounts validated (remediated 2 issues)
[INFO] Phase 2/5: restore - STARTING
[PASS] Restored 6 LXC containers
[INFO] Phase 3/5: iac - STARTING
[PASS] IaC state accessible from NAS
[INFO] Phase 4/5: services - STARTING
[PASS] Configured 6 services (2 created, 4 no changes)
[INFO] Phase 5/5: verify - COMPLETED
[PASS] All services healthy

=== Rebuild Summary ===
Total phases: 5
Completed: 5
Failed: 0
Duration: 18m 23s
Evidence: artifacts/rebuild-runs/rebuild-20260210-123456/

System Status: OPERATIONAL ✓
```

**✅ Validation**:
- [ ] All 5 phases complete successfully
- [ ] Services accessible and healthy
- [ ] Evidence bundle complete
- [ ] System operational (can access Immich, monitoring dashboards, etc.)

**Idempotency Test**: Run again immediately:
```bash
task rebuild:apply -- --environment lab --backup-dir /root/restore-20260210
```

Expected: All phases report "no changes needed" since system already in desired state.

### Step 2.7: Review Evidence Artifacts

```bash
# Navigate to evidence directory
cd artifacts/rebuild-runs/

# Find latest run
LATEST_RUN=$(ls -t | grep rebuild- | head -1)
echo "Latest run: $LATEST_RUN"

# Review structure
tree $LATEST_RUN -L 2

# Expected structure:
# rebuild-20260210-123456/
# ├── state.json
# └── reports/
#     ├── mounts/
#     ├── services/
#     ├── preflight-summary.txt
#     └── rebuild-phase-summary.md
```

**Review key evidence files**:
```bash
cd $LATEST_RUN

# Preflight summary
cat reports/preflight-summary.txt

# Phase summary
cat reports/rebuild-phase-summary.md

# Service logs
ls -lh reports/services/
cat reports/services/monitoring.log | tail -50
```

**✅ Validation**:
- [ ] state.json contains all phase statuses
- [ ] All report files present
- [ ] No error messages in service logs
- [ ] Phase summary shows all completed

**✅ LAB RESTORATION COMPLETE**

---

## Part 3: Prod Environment Restoration

**⚠️ CRITICAL**: Production restoration affects live services. Use with caution.

### Pre-Prod Checklist

- [ ] Lab restoration tested successfully first
- [ ] Prod backup extracted and ready (if doing full restore)
- [ ] Prod state exists on NAS: `/mnt/nas/homelab_ci/infra_state/prod/`
- [ ] Downtime window scheduled (if applicable)
- [ ] Rollback plan ready
- [ ] Confirmation you understand prod will be affected

### Step 3.1: Prod State Path Validation

```bash
# Verify prod paths resolve correctly
USE_NAS_STATE=true ENVIRONMENT=prod bash -c '
  source scripts/lab/lib/state.sh
  echo "Prod state root: $(resolve_state_root)"
  echo "Monitoring state: $(get_service_state_path monitoring)"
'
```

**Expected Output**:
```
Prod state root: /Volumes/nas/homelab_ci/infra_state/prod
Monitoring state: /Volumes/nas/homelab_ci/infra_state/prod/monitoring/terraform.tfstate
```

**✅ Validation**:
- [ ] Paths use `prod` (not `lab` or `static`)
- [ ] Environment isolation working

### Step 3.2: Prod Mounts Validation

```bash
# Test prod mounts (plan mode, no confirmation needed)
task rebuild:plan -- --phase mounts --environment prod
```

**Expected**: Same mount checks as lab, but targeting prod environment

**✅ Validation**:
- [ ] Mount checks pass
- [ ] No cross-environment pollution

### Step 3.3: Prod Preview (Plan Mode)

**Purpose**: Preview changes before applying to production

```bash
# Preview entire restoration without making changes
task rebuild:plan -- --environment prod --backup-dir /root/restore-YYYYMMDD
```

**Expected Output**:
```
[INFO] Environment: prod
[INFO] Mode: plan
[INFO] Processing prod services...
```

**✅ Validation**:
- [ ] Terraform plans against prod infrastructure
- [ ] State read from `/Volumes/nas/.../prod/` paths
- [ ] Plan shows expected state (no surprises)
- [ ] No changes applied (plan mode only)

### Step 3.4: Prod Complete Restoration (Apply Mode)

**⚠️ WARNING**: This will restore/configure production infrastructure!

**Only proceed if**:
- [ ] Plan mode review completed (Step 3.3)
- [ ] Expected changes are correct
- [ ] Backup/rollback plan ready
- [ ] Ready to accept downtime (if applicable)

```bash
# Execute full production restoration (requires confirmation)
task rebuild:apply CONFIRM=rebuild-prod -- --environment prod --backup-dir /root/restore-YYYYMMDD
```

**Expected Output**:
```
[INFO] Environment: prod
[INFO] Mode: apply
[WARN] Apply mode will make changes to production infrastructure
[INFO] Confirmation string validated: rebuild-prod
Proceeding with restoration...

[INFO] Phase 1/5: mounts - COMPLETED
[INFO] Phase 2/5: restore - COMPLETED (6 containers)
[INFO] Phase 3/5: iac - COMPLETED
[INFO] Phase 4/5: services - COMPLETED (3 created, 3 unchanged)
[INFO] Phase 5/5: verify - COMPLETED

Production Status: OPERATIONAL ✓
```

**✅ Validation**:
- [ ] All phases successful
- [ ] Production services accessible
- [ ] State on NAS at `/mnt/nas/homelab_ci/infra_state/prod/`
- [ ] No cross-environment contamination

**Idempotency Test**: Run again:
```bash
task rebuild:apply CONFIRM=rebuild-prod -- --environment prod --backup-dir /root/restore-YYYYMMDD
```
Expected: "No changes needed" for all phases.

**✅ PROD RESTORATION COMPLETE**

---

## Part 4: Cross-Environment Validation

### Validation 4.1: Environment Isolation

**Verify lab and prod state completely separate**:

```bash
# Check lab state
ssh pve "ls /mnt/nas/homelab_ci/infra_state/lab/ | wc -l"

# Check prod state
ssh pve "ls /mnt/nas/homelab_ci/infra_state/prod/ | wc -l"

# Ensure different contents
ssh pve "diff -r /mnt/nas/homelab_ci/infra_state/lab/ /mnt/nas/homelab_ci/infra_state/prod/ || echo 'Isolated (expected)'"
```

**✅ Validation**:
- [ ] Lab and prod directories separate
- [ ] No accidental cross-environment writes
- [ ] State files independent

### Validation 4.2: Backward Compatibility (Symlinks)

**Verify GH Actions can still use legacy paths**:

```bash
# Check symlinks still intact
ssh pve "ls -la /var/lib/homelab-proxmox/state/services/ | grep '^l' | wc -l"

# Expected: 6 (all services symlinked)
```

```bash
# Verify symlink targets correct
ssh pve "readlink /var/lib/homelab-proxmox/state/services/monitoring"

# Expected: /mnt/nas/homelab_ci/infra_state/lab/monitoring
```

**Test legacy path access**:
```bash
# State accessible through symlink
ssh pve "cat /var/lib/homelab-proxmox/state/services/monitoring/terraform.tfstate | jq -r .version"

# Expected: State version number (e.g., "4")
```

**✅ Validation**:
- [ ] All symlinks present
- [ ] Symlinks point to lab environment (GH Actions default)
- [ ] Legacy path access works
- [ ] GH Actions workflows unaffected

### Validation 4.3: State Integrity

**Verify no state corruption**:

```bash
# Validate all state files
for env in lab prod; do
  for statefile in /Volumes/nas/homelab_ci/infra_state/$env/*/terraform.tfstate; do
    [[ -f "$statefile" ]] || continue
    service=$(basename $(dirname "$statefile"))
    if terraform show -json "$statefile" > /dev/null 2>&1; then
      echo "✓ $env/$service: Valid"
    else
      echo "✗ $env/$service: CORRUPTED"
    fi
  done
done
```

**✅ Validation**:
- [ ] All state files valid JSON
- [ ] Terraform can parse all states
- [ ] No corruption detected

---

## Part 5: Post-Restoration

### Step 5.1: Final Validation

**Verify system is fully operational**:

```bash
# Check all services responding
curl -I https://immich.yourdomain.com
curl -I https://grafana.yourdomain.com

# Verify from laptop you can access services
# Open browser and test each service

# Archive evidence
tar czf rebuild-evidence-$(date +%Y%m%d).tar.gz artifacts/rebuild-runs/

# Optional: Store evidence on NAS
scp rebuild-evidence-*.tar.gz pve:/mnt/nas/homelab_ci/evidence/
```

### Step 5.2: Verify Idempotency

**Test that running again makes no changes**:

```bash
# For lab
task rebuild:apply -- --environment lab --backup-dir /root/restore-YYYYMMDD

# Expected output for each phase:
# [INFO] Service <name>: No changes needed (infrastructure matches state)
# [INFO] Phase <N>: No changes required
```

This confirms the system is **idempotent** - safe to run multiple times.

### Step 5.3: Document Restoration

**Create restoration summary**:

```bash
cat > restoration-summary-$(date +%Y%m%d).md <<EOF
# System Restoration Summary

**Date**: $(date)
**Environment**: [lab/prod]
**Operator**: $(whoami)
**Starting State**: [Fresh PVE 9 / Existing system validation]

## Restoration Results
- Mounts phase: [PASS/FAIL] - Duration: __m __s
- Restore phase: [PASS/FAIL] - Containers restored: __
- IaC phase: [PASS/FAIL] - State accessible: [YES/NO]
- Services phase: [PASS/FAIL] - Services configured: __
- Verify phase: [PASS/FAIL] - All healthy: [YES/NO]

## Idempotency Test
- Second run completed: [YES/NO]
- Changes on second run: [NONE/list if any]
- Idempotent: [YES/NO]

## System Status
- Immich: [OPERATIONAL/DOWN]
- Monitoring: [OPERATIONAL/DOWN]
- Other services: [list status]

## Issues Encountered
- (List any issues and how they were resolved)

## Evidence
- Location: artifacts/rebuild-runs/
- Archive: rebuild-evidence-$(date +%Y%m%d).tar.gz

## Outcome
- System operational: [YES/NO]
- Duration: __h __m
- Notes: (any observations)
EOF

cat restoration-summary-$(date +%Y%m%d).md
```

**✅ RESTORATION COMPLETE**

Your system is now fully operational. The orchestrator can be run again at any time - it will only apply changes needed to maintain desired state (idempotent).

---

## Troubleshooting

### Issue: NFS mount not accessible

**Symptoms**:
- `ERROR: NAS mount not found at /Volumes/nas/homelab_ci`
- State library fails with missing directory error

**Solutions**:
```bash
# 1. Check mount status
ls /Volumes/nas/

# 2. Force remount
sudo automount -uc
sudo automount -vc

# 3. Test NFS connectivity
showmount -e 192.168.1.109

# 4. Manual mount (temporary)
sudo mkdir -p /Volumes/nas/homelab_ci
sudo mount -t nfs -o nfsvers=3,resvport 192.168.1.109:/volume1/homelab_ci /Volumes/nas/homelab_ci
```

### Issue: Terraform authentication failed

**Symptoms**:
- `Error: authentication failed`
- `401 Unauthorized`

**Solutions**:
```bash
# 1. Verify credentials exported
echo $PROXMOX_API_TOKEN_ID
echo ${PROXMOX_API_TOKEN_SECRET:0:20}...

# 2. Test API access
curl -k -H "Authorization: PVEAPIToken=$PROXMOX_API_TOKEN_ID=$PROXMOX_API_TOKEN_SECRET" \
  https://192.168.1.112:8006/api2/json/version

# 3. Re-export if needed (use single quotes for zsh)
export PROXMOX_API_TOKEN_ID='root@pam!rebuild'
export PROXMOX_API_TOKEN_SECRET='<from Bitwarden>'

# 4. Verify token hasn't expired
# Check Proxmox UI: Datacenter → Permissions → API Tokens
```

### Issue: State file not writable

**Symptoms**:
- `ERROR: Cannot write to state root`
- Permission denied when accessing NAS

**Solutions**:
```bash
# 1. Check NAS permissions
ls -la /Volumes/nas/homelab_ci/infra_state/

# 2. Verify NFS export settings
# Login to Synology DSM → Control Panel → Shared Folder → homelab_ci → NFS Permissions
# Ensure your laptop IP has Read/Write access

# 3. Test write access
touch /Volumes/nas/homelab_ci/infra_state/lab/.test
rm /Volumes/nas/homelab_ci/infra_state/lab/.test
```

### Issue: Wrong environment (lab state accessed in prod mode)

**Symptoms**:
- Prod rebuild accessing lab services
- Environment variable mismatch

**Solutions**:
```bash
# 1. Verify environment variable
echo $ENVIRONMENT

# 2. Explicitly set environment
export ENVIRONMENT=prod  # or lab

# 3. Check state path resolution
USE_NAS_STATE=true bash -c 'source scripts/lab/lib/state.sh && resolve_state_root'

# Expected for prod: /Volumes/nas/homelab_ci/infra_state/prod
# Expected for lab: /Volumes/nas/homelab_ci/infra_state/lab
```

### Issue: Evidence artifacts not created

**Symptoms**:
- artifacts/rebuild-runs/ empty or missing
- No evidence files after rebuild run

**Solutions**:
```bash
# 1. Check directory exists
ls -la artifacts/rebuild-runs/

# 2. Verify repository path
pwd  # Should be in homelab-proxmox root

# 3. Check for permission issues
ls -la artifacts/

# 4. Force create directory
mkdir -p artifacts/rebuild-runs/

# 5. Re-run rebuild with verbose logging
task rebuild:plan -- --environment lab --backup-dir /root/test --verbose
```

---

## Rollback Procedures

### If Restoration Encounters Issues

**Immediate actions**:

1. **Disable NAS state mode**:
   ```bash
   unset USE_NAS_STATE
   # Falls back to legacy paths automatically
   ```

2. **Verify symlinks still work**:
   ```bash
   ssh pve "ls -la /var/lib/homelab-proxmox/state/services/"
   # Symlinks preserve backward compatibility
   ```

3. **Restore from backup** (if state corrupted):
   ```bash
   # Follow disaster recovery guide
   # See: docs/operations/backups-proxmox-config-restore.md
   ```

4. **Revert code changes**:
   ```bash
   git stash  # Save local changes
   git checkout main  # Return to main branch
   ```

### Report Issues

If you find bugs or unexpected behavior:

1. **Capture evidence**:
   ```bash
   tar czf issue-evidence-$(date +%Y%m%d-%H%M).tar.gz artifacts/rebuild-runs/
   ```

2. **Capture state**:
   ```bash
   env | grep -E "ENVIRONMENT|USE_NAS|PROXMOX" > env-state.txt
   ```

3. **Create GitHub issue** with:
   - Test scenario that failed
   - Expected vs actual behavior
   - Evidence archive
   - Environment variables
   - Error messages

---

## Success Criteria

**Lab Restoration Complete** when:
- [ ] All 5 phases pass successfully
- [ ] Services accessible and healthy
- [ ] State persisted to NAS
- [ ] Second run shows "no changes needed" (idempotent)
- [ ] Evidence artifacts complete

**Prod Restoration Complete** when:
- [ ] All 5 phases pass successfully
- [ ] Production services operational
- [ ] State isolation verified (lab ≠ prod)
- [ ] Idempotency confirmed
- [ ] No cross-environment contamination

**System Fully Operational** when:
- [ ] Started with fresh PVE 9 (or existing system)
- [ ] All services responding to health checks
- [ ] Can access all web interfaces
- [ ] Monitoring dashboards showing data
- [ ] Subsequent runs make no changes
- [ ] System survives PVE host reboot (state on NAS)

---

## Routine Maintenance

**Regular Validation** (monthly recommended):
```bash
# Verify system still idempotent
task rebuild:apply -- --environment lab

# Expected: No changes needed
```

**After Infrastructure Changes**:
Run orchestrator to ensure state synchronized:
```bash
task rebuild:apply -- --environment [lab|prod]
```

**Before Major Changes**:
Run plan mode to preview impact:
```bash
task rebuild:plan -- --environment [lab|prod]
```

---

## References

- **Migration Checklist**: [specs/033-idempotent-rebuild/migration-checklist.md](../../specs/033-idempotent-rebuild/migration-checklist.md)
- **Quickstart Guide**: [specs/033-idempotent-rebuild/quickstart.md](../../specs/033-idempotent-rebuild/quickstart.md)
- **Laptop NFS Setup**: [laptop-nfs-setup.md](./laptop-nfs-setup.md)
- **API Token Setup**: [proxmox-api-token-setup.md](./proxmox-api-token-setup.md)
- **Disaster Recovery**: [../operations/backups-proxmox-config-restore.md](../operations/backups-proxmox-config-restore.md)
- **Delta Spec**: [specs/033-idempotent-rebuild/spec-delta-state-storage.md](../../specs/033-idempotent-rebuild/spec-delta-state-storage.md)

---

**Last Updated**: 2026-02-10
**Maintainer**: Infrastructure Team
**Status**: Ready for testing
