# Quickstart: Pipeline Promotion UX

**Branch**: `024-pipeline-promotion-ux`  
**Date**: 2026-01-09  
**Audience**: Homelab operators and CI/CD workflow users

This guide explains how to use the improved CI/CD pipeline workflows for LXC container deployments.

---

## Overview

The Pipeline Promotion UX feature provides two main workflows:

1. **LXC Deploy (LAB)**: Deploy to LAB environment only (plan or plan+apply)
2. **LXC Promote (LAB → PROD)**: Deploy to LAB, then promote to PROD with approval

Both workflows use bounded inputs (dropdowns, booleans) instead of free-text fields to reduce operator error.

---

## Prerequisites

### GitHub Permissions
- **LAB deploys**: Write access to repository, can trigger workflow_dispatch
- **PROD deploys**: Must be in "required reviewers" list for `prod` Environment

### Proxmox Access
- Workflows use self-hosted GitHub Actions runner with SSH access to Proxmox host
- Runner must have SSH keys configured for `ci@pve` user

### Secrets Configuration
- `ANSIBLE_VAULT_PASSWORD`: Ansible vault password (repository secret)
- `PROXMOX_TOKEN_SECRET`: Proxmox API token secret (repository secret, PROD only)

---

## Workflow 1: LXC Deploy (LAB)

**Use case**: Iterate on a single service in LAB environment

### Inputs

| Input | Type | Required | Description |
|-------|------|----------|-------------|
| `service` | Choice | Yes | Service to deploy (dropdown with allowlist) |
| `apply` | Boolean | Yes | Plan+apply (true) or plan-only (false) |
| `confirm_destructive` | Boolean | Conditional | Check to allow apply if plan detects destructive changes |

### How to Run

1. Navigate to **Actions** → **LXC Deploy (LAB)**
2. Click **Run workflow**
3. Select **service** from dropdown (e.g., `immich`, `jellyfin`)
4. Toggle **apply**:
   - `false` (unchecked): Plan-only mode (safe, no changes)
   - `true` (checked): Plan+apply mode (makes changes)
5. Leave **confirm_destructive** unchecked (only check if plan is destructive)
6. Click **Run workflow**

### Expected Behavior

#### Plan-Only Mode (`apply: false`)
1. Workflow runs Terraform plan on LAB
2. Generates evidence pack with plan output
3. Uploads LAB snapshot artifact
4. Completes (no changes made)

#### Plan+Apply Mode (`apply: true`)
1. Workflow runs Terraform plan on LAB
2. Checks for destructive changes (replace/destroy)
  - If destructive: workflow fails unless `confirm_destructive: true`
3. Runs Terraform apply (makes changes)
4. Runs second apply for idempotency check
5. Generates evidence pack and LAB snapshot
6. Completes

### Destructive Changes Workflow

If plan detects destructive changes (replace or destroy operations):

1. Workflow fails with message: "Plan is destructive (replace/destroy)"
2. Review plan output in evidence artifact
3. If changes are acceptable:
   - Rerun workflow with **same inputs**
  - Check `confirm_destructive: true`
4. Workflow proceeds with apply

### Artifacts

- **Evidence pack**: `service-deploy-evidence-<run-id>` (downloadable artifact)
  - Contains: plan output, apply logs, blast-radius.json, LAB snapshot
- **LAB snapshot**: `reports/lab-snapshot.json` in evidence pack
  - Shows: container state, service evidence pointers, mount validation

---

## Workflow 2: LXC Promote (LAB → PROD)

**Use case**: Promote a service from LAB to PROD after validation

### Inputs

| Input | Type | Required | Description |
|-------|------|----------|-------------|
| `service` | Choice | Yes | Service to promote (dropdown with allowlist) |
| `confirm_destructive_lab` | Boolean | Conditional | Check to proceed if LAB plan is destructive |
| `confirm_destructive_prod` | Boolean | Conditional | Check to proceed if PROD plan is destructive |

### How to Run

1. Navigate to **Actions** → **LXC Promote (LAB → PROD)**
2. Click **Run workflow**
3. Select **service** from dropdown
4. Leave destructive confirmations unchecked initially
5. Click **Run workflow**

### Expected Behavior

#### Stage 1: LAB Deploy
1. Workflow runs plan on LAB
2. Checks for destructive changes
  - If destructive: fails unless `confirm_destructive_lab: true`
3. Runs apply on LAB
4. Generates LAB evidence pack with snapshot
5. LAB stage completes

#### Stage 2: Approval Gate
1. Workflow pauses automatically (GitHub Environment protection)
2. Notification sent to required reviewers
3. Reviewer(s) examine:
   - LAB evidence artifact
   - Plan output
   - LAB snapshot (container state, evidence pointers)
4. Reviewer approves or rejects in GitHub UI

#### Stage 3: PROD Deploy (after approval)
1. Workflow provisions `prod.tfvars` on Proxmox host
   - Renders template with `PROXMOX_TOKEN_SECRET` from GitHub Secrets
   - Validates token ID and secret presence
   - Generates redacted proof in evidence (no secrets logged)
2. Runs plan on PROD
3. Checks for destructive changes
  - If destructive: fails unless `confirm_destructive_prod: true`
4. Runs apply on PROD
5. Generates PROD evidence pack with snapshot and tfvars proof
6. PROD stage completes

### Approval Workflow

When workflow pauses at approval gate:

1. **GitHub sends notification** to required reviewers
2. **Reviewer navigates** to Actions → Workflow run → "Review deployments"
3. **Reviewer examines** LAB artifacts:
   - Download evidence pack
   - Check `reports/lab-snapshot.json` for container state
   - Review plan output for expected changes
4. **Reviewer approves or rejects**:
   - **Approve**: Workflow proceeds to PROD
   - **Reject**: Workflow stops (operator must fix and rerun)

### Destructive Changes in Promotion

If destructive changes detected in LAB or PROD:

1. Workflow fails at appropriate stage
2. Review plan output in evidence
3. Rerun with appropriate confirmation:
  - LAB destructive: `confirm_destructive_lab: true`
  - PROD destructive: `confirm_destructive_prod: true`

### Artifacts

- **LAB evidence pack**: `service-deploy-evidence-lab-<run-id-1>-<run-id-2>`
- **PROD evidence pack**: `service-deploy-evidence-prod-<run-id>`
  - Includes: `reports/prod-tfvars/validation.json` (redacted tfvars proof)
  - Includes: `reports/lab-snapshot.json` (PROD snapshot)

---

## Understanding Destructive Changes

### What is a Destructive Change?

Terraform operations that replace or destroy existing resources:
- **Replace**: Resource recreated with new ID (e.g., IP address change)
- **Destroy**: Resource deleted

### Why Explicit Confirmation?

Destructive changes can cause downtime or data loss. Explicit confirmation ensures operator awareness.

### Confirmation Checkboxes

If a plan includes replace/destroy operations, rerun with the matching confirmation checkbox set to `true`.

### Example Workflow with Destructive Changes

1. Run promote workflow (no confirmations)
2. LAB plan detects destructive change → workflow fails
3. Review plan output: "Plan will replace module.immich_lxc (IP changed)"
4. Rerun workflow with `confirm_destructive_lab: true`
5. LAB apply proceeds
6. Approval granted
7. PROD plan detects destructive change → workflow fails
8. Review plan output
9. Rerun workflow with both:
  - `confirm_destructive_lab: true`
  - `confirm_destructive_prod: true`
10. PROD apply proceeds

---

## LAB Snapshot Artifacts

### What is a LAB Snapshot?

JSON document capturing:
- **Containers**: VMID, hostname, status, IPv4 address
- **Services**: Terraform state paths, module names
- **Latest Evidence**: Pointers to most recent evidence packs per service
- **Mount Checks**: Validation of declared mounts (e.g., `/media/video` read-only)

### How to Access

1. Navigate to workflow run in Actions
2. Scroll to **Artifacts** section
3. Download evidence artifact (e.g., `service-deploy-evidence-<run-id>`)
4. Extract tarball
5. Open `reports/lab-snapshot.json`

### Snapshot Example

```json
{
  "generated_at": "2026-01-09T08:05:00Z",
  "environment": "lab",
  "containers": [
    {
      "vmid": 200,
      "hostname": "immich-lab",
      "status": "running",
      "ipv4": "192.168.1.50"
    }
  ],
  "services": [
    {
      "service": "immich",
      "state_path": "/var/lib/homelab-proxmox/state/services/immich"
    }
  ],
  "latest_evidence": {
    "immich": {
      "run_id": "20260109T075500Z-apply-lab-immich-abc123",
      "path": "/var/lib/homelab-proxmox/artifacts/service-deploy-runs/..."
    }
  },
  "mount_checks": [
    {
      "container_vmid": 200,
      "mount_path": "/media/video",
      "mounted": true,
      "read_only": true,
      "source": "192.168.1.109:/volume1/video"
    }
  ],
  "errors": []
}
```

### Snapshot Use Cases

- **Quick inventory**: See what's running in LAB without SSH
- **Evidence tracking**: Find latest evidence pack for a service
- **Mount validation**: Confirm shared media mounts are correct
- **Troubleshooting**: Check container status and IP addresses

---

## Troubleshooting

### Error: "Invalid --service"

**Cause**: Service not in allowlist  
**Fix**: Check `scripts/lab/service-scope-allowlist.json` for valid services

### Error: "Plan is destructive"

**Cause**: Terraform plan includes replace/destroy operations  
**Fix**: Review plan output, then rerun with appropriate `confirm_destructive` value

### Error: "Waiting for approval"

**Cause**: PROD stage waiting for required reviewer approval  
**Fix**: Contact required reviewers; they must approve in GitHub UI

### Error: "tfvars validation failed"

**Cause**: `prod.tfvars` provisioning detected invalid token ID or missing secret  
**Fix**: Verify `PROXMOX_TOKEN_SECRET` is set correctly in repository secrets; check evidence for specific validation errors

### Evidence Pack Missing

**Cause**: Workflow failed before evidence collection  
**Fix**: Check workflow logs for errors in preflight checks; ensure Proxmox host is reachable

---

## Best Practices

### LAB Iteration
1. Start with plan-only (`apply: false`) to preview changes
2. Review plan output in evidence artifact
3. Run plan+apply (`apply: true`) when ready

### PROD Promotion
1. Always test in LAB first (use LAB deploy workflow)
2. Verify LAB snapshot shows expected state
3. Use promote workflow (not LAB deploy) for PROD changes
4. Review LAB evidence before approving PROD

### Destructive Changes
1. Always review plan output before confirming destructive operations
2. Understand blast radius (what will be replaced/destroyed)
3. Consider alternative approaches (e.g., in-place updates) if possible

---

## FAQ

### Q: Can I deploy to PROD without LAB?
**A**: No. The promote workflow always runs LAB first. This enforces testing before production changes.

### Q: Can I bypass the PROD approval gate?
**A**: No (by design). PROD changes always require manual approval from required reviewers. Repository admins can override in true emergencies, but this is logged.

### Q: What if LAB apply succeeds but PROD approval is rejected?
**A**: LAB changes remain (LAB is separate environment). Fix issues, then rerun promote workflow. LAB will be redeployed (idempotent).

### Q: How do I add a new service to the workflows?
**A**: Add service to `scripts/lab/service-scope-allowlist.json`, then update workflow YAML choice lists. Both must be kept in sync.

### Q: Where are secrets stored?
**A**: GitHub repository secrets (Settings → Secrets → Actions). `prod.tfvars` is rendered on Proxmox host only; never committed to repository.

### Q: What's the difference between LAB and PROD snapshots?
**A**: Same schema, different `environment` field. LAB snapshot shows LAB containers; PROD snapshot shows PROD containers. Both are included in respective evidence packs.

---

## Next Steps

- Review [data-model.md](./data-model.md) for detailed entity schemas
- Review [research.md](./research.md) for technical decisions and rationale
- Review [plan.md](./plan.md) for full implementation roadmap

---

**Document Version**: 1.0  
**Last Updated**: 2026-01-09
