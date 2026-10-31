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
- ✅ Rebuilds infrastructure using the Terraform state on `pve` (`state/prod`; `state/lab` is temporary)
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

### 2. Terraform state on pve

Terraform state is local to `pve` (spec 067), not on the NAS. Verify it exists on the host you are restoring:

```bash
ssh pve "ls -d /var/lib/homelab-proxmox/state/prod/*/ | wc -l"   # expect 12 on a healthy host

# Expected: the production services, each with a terraform.tfstate
# `state/lab` is absent unless a LAB rehearsal is running. That is normal.
```

- [ ] **State restored on PVE** (from the backup, see [backups-proxmox-config-restore.md](../operations/backups-proxmox-config-restore.md) Step 7)
- [ ] **NAS mounts** present on PVE for the service data (`/mnt/nas/...`), because bind mounts need them

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

### Step 1.1: No laptop NFS mount needed

Earlier versions of this runbook mounted `homelab_ci/infra_state` on the laptop. That is gone: state is local to
`pve`, and state-touching steps run on `pve` as `ci` over SSH. Confirm access instead:

```bash
ssh pve 'id && ls /var/lib/homelab-proxmox/state/'
# Expected: uid=...(ci) and the directory `prod` (plus `lab` only during a LAB run)
```

**✅ Checkpoint**: SSH access to `pve` as `ci` works

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

### Step 1.4: Select the environment

```bash
export ENVIRONMENT=prod   # or lab (only meaningful while a LAB rehearsal runs)
```

**✅ Checkpoint**: environment selected

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

**Purpose**: Verify state path resolution

```bash
# Run on pve, where the state lives
ssh pve 'cd ~/homelab-proxmox && ENVIRONMENT=prod bash -c "
  source scripts/lab/lib/state.sh
  echo State root: \$(resolve_state_root prod)
  echo Monitoring state: \$(get_service_state_path prod monitoring)
"'
```

**Expected Output**:
```
State root: /var/lib/homelab-proxmox/state/prod
Monitoring state: /var/lib/homelab-proxmox/state/prod/monitoring/terraform.tfstate
```

**✅ Validation**:
- [ ] Paths are under `/var/lib/homelab-proxmox/state/`
- [ ] The environment segment matches the one you selected

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
[INFO] State path: /var/lib/homelab-proxmox/state/prod/immich/terraform.tfstate
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

**Issue**: `ERROR: Cannot write to state root`
```bash
# Fix: state is local to pve; check the directory and its owner
ssh pve 'ls -ld /var/lib/homelab-proxmox/state /var/lib/homelab-proxmox/state/*'
# Setup: ansible/playbooks/setup-state-dirs.yml
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
- [ ] Prod state exists on PVE: `/var/lib/homelab-proxmox/state/prod/`
- [ ] Downtime window scheduled (if applicable)
- [ ] Rollback plan ready
- [ ] Confirmation you understand prod will be affected

### Step 3.1: Prod State Path Validation

```bash
ssh pve 'ls /var/lib/homelab-proxmox/state/prod/ | wc -l'
# Expected: 12
```

**✅ Validation**:
- [ ] Each service has `state/prod/<service>/terraform.tfstate`

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
- [ ] State read from `/var/lib/homelab-proxmox/state/prod/` paths
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
- [ ] State on PVE at `/var/lib/homelab-proxmox/state/prod/`
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

Lab and prod are separate directories. Lab exists only during a LAB rehearsal, so on a quiet host:

```bash
ssh pve 'ls /var/lib/homelab-proxmox/state/'      # expect: prod  (lab only while a rehearsal runs)
ssh pve 'ls /var/lib/homelab-proxmox/lab-scratch/'  # expect: empty
ssh pve 'sudo pct list | grep -c " lab-"'          # expect: 0
```

**✅ Validation**:
- [ ] `state/lab` absent, `lab-scratch` empty, no `lab-` containers
- [ ] The drift check is clean (see [state-drift.md](./state-drift.md))

### Validation 4.3: State Integrity

**Verify no state corruption** (terraform runs on `pve`):

```bash
ssh pve 'for statefile in /var/lib/homelab-proxmox/state/prod/*/terraform.tfstate; do
  service=$(basename "$(dirname "$statefile")")
  if terraform show -json "$statefile" > /dev/null 2>&1; then echo "✓ prod/$service: Valid"; else echo "✗ prod/$service: CORRUPTED"; fi
done'
```

**✅ Validation**:
- [ ] All state files parse
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

### Issue: Service data mount not accessible

**Symptoms**:
- `ERROR: NAS mount not found` on `pve`

**Solutions**:
```bash
ssh pve 'mount | grep /mnt/nas'
ssh pve 'sudo systemctl daemon-reload && sudo mount -a'
showmount -e 192.168.1.109
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

**Solutions**:
```bash
# 1. Run state-touching steps on pve as ci
ssh pve 'id; ls -ld /var/lib/homelab-proxmox/state /var/lib/homelab-proxmox/state/*'

# 2. Recreate the directories if they are missing (root Ansible, from the laptop)
ansible-playbook ansible/playbooks/setup-state-dirs.yml -k
```

### Issue: Wrong environment (lab state accessed in prod mode)

**Symptoms**:
- Prod rebuild reading `state/lab`, or the reverse

**Solutions**:
```bash
echo $ENVIRONMENT                      # must be prod or lab
export ENVIRONMENT=prod                # explicitly set it
ssh pve 'cd ~/homelab-proxmox && bash -c "source scripts/lab/lib/state.sh && resolve_state_root prod"'
# Expected: /var/lib/homelab-proxmox/state/prod
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

1. **Check state is intact**:
   ```bash
   ssh pve "ls /var/lib/homelab-proxmox/state/prod/"
   ```

2. **Run the drift check** to see what differs from the containers:
   ```bash
   ssh pve "sudo systemctl start state-drift-check.service && cat /var/lib/homelab-proxmox/artifacts/state-drift/latest.json"
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
