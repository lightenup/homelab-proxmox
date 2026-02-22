# Quickstart: Token Privilege Separation

**Feature Branch**: `036-token-privilege-separation`

## What This Feature Does

Formalises a three-tier privilege model for Proxmox operations and generalises the per-service hardcoded bind-mount logic into a data-driven mechanism. After this feature:

1. **Tier 1** (Terraform) creates containers using the least-privilege `terraform@pve` token.
2. **Tier 2** (Orchestrator) applies host-path bind mounts and feature flags via `sudo pct set` on PVE.
3. **Tier 3** (Break-glass) is documented but never used in automation.

Any service can now declare NAS bind mounts in its tfvars entry, and the orchestrator will apply them generically — no more hardcoded per-service blocks.

## How to Add Bind Mounts to a Service

1. **Determine required mounts**: Check the service documentation for required host paths (e.g., NAS storage).

2. **Declare in tfvars** (`terraform/environments/<env>.tfvars`):
   ```hcl
   service_mountpoints = {
     myservice = {
       data = {
         mp       = "/mnt/mydata"           # Container-side path
         volume   = "/mnt/nas/myservice"     # Host-side path (must start with /mnt/nas/)
         readonly = false                     # Optional, defaults to false
       }
     }
   }
   ```

3. **Deploy**: Run `pve-service-deploy apply --environment lab --service myservice`. The orchestrator will:
   - Create the container via Terraform (Tier 1)
   - Apply bind mounts via `pct set` (Tier 2)
   - Produce evidence in `reports/apply/lxc-bind-mounts.txt`

4. **Verify**: Check the step summary for mount results (`applied`, `skipped`, or `failed`).

## Key Constraints

- Host paths **must** be under `/mnt/nas/` (allowlist enforced).
- The `readonly` attribute maps to `ro=1` in `pct set` format.
- Mounts are idempotent — re-running the deploy skips already-applied mounts.
- A container reboot occurs only when new mounts are applied.

## Development Workflow

```bash
# Run from laptop (same as CI)
cd scripts/lab
./pve-service-deploy apply --environment lab --service nextcloud

# CI runs the same command via SSH to PVE host
```

## File Locations

| Purpose | Path |
|---------|------|
| Orchestrator script | `scripts/lab/pve-service-deploy` |
| Tfvars examples | `terraform/environments/{lab,prod}.tfvars.example` |
| LXC module | `terraform/modules/lxc_service/` |
| Per-service Terraform | `terraform/services/<service>/` |
| Constitution (tier docs) | `.specify/memory/constitution.md` |
| Golden paths (onboarding) | `docs/operations/golden-paths-service-lifecycle.md` |
| Evidence profile | `scripts/lab/profiles.d/service-deploy.json` |
