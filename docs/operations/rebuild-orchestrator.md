# Rebuild Orchestrator (Idempotent)

**Feature**: 033-idempotent-rebuild
**Purpose**: Run a safe, idempotent rebuild from macOS using existing Taskfile + scripts/lab orchestration.

## Entry Points

- Taskfile targets:
  - task rebuild:plan -- [flags]
  - task rebuild:apply CONFIRM=<confirm-string> -- [flags]
- Launcher script: [scripts/rebuild/run-rebuild.sh](scripts/rebuild/run-rebuild.sh)

## Required Inputs

- Proxmox host reachable via SSH (set `PROXMOX_HOST` and `SSH_USER` if needed).
- Extracted backup directory on the Proxmox host (set `--backup-dir`).

## PVE Access

The rebuild system expects `ssh pve` (or your chosen alias) to work from the laptop. Configure a host alias in `~/.ssh/config`, then reuse that alias across Terraform, Ansible, and rebuild scripts.

### Privilege Tiers

Standard rebuild operations use **Tier 1** (Terraform, `terraform@pve` API token) for container provisioning and **Tier 2** (orchestrator `pct set` via `sudo`) for post-create configuration such as bind mounts and feature flags.

Manual break-glass operations (disaster recovery only) may use **Tier 3** (`root@pam!rebuild` API token) when Tier 1 and Tier 2 access is insufficient to recover the system. Tier 3 must never appear in automated CI/CD flows.

See [constitution — Token Privilege Tiers](../../.specify/memory/constitution.md#token-privilege-tiers) for the full three-tier model definition and enforcement rules.

Example `~/.ssh/config` entry:

- Host pve
  - HostName 192.168.20.2
  - User ci
  - IdentityFile ~/.ssh/id_ed25519

Environment alignment:

- Rebuild: `PROXMOX_HOST=pve` or `SSH_TARGET=pve` (uses SSH config)
- Terraform: set `proxmox_node = "pve"` and `proxmox_api_url` to the same host
- Ansible inventory: use `pve` as the host alias with `ansible_user=ci`

## Examples

Plan-only (default):

- task rebuild:plan -- --environment lab --backup-dir /root/restore-YYYYMMDD

Apply (requires confirmation string):

- task rebuild:apply CONFIRM=rebuild-prod -- --environment prod --backup-dir /root/restore-YYYYMMDD

## Key Flags

- `--mode plan|apply`: Set plan-only or apply mode (plan is default).
- `--environment lab|prod`: Target environment (default lab).
- `--confirm <string>`: Required for apply and for prod runs.
- `--phase <name>` or `--phases mounts,restore,iac,services,verify`: Limit phases.
- `--backup-dir <path>`: Path to extracted backup on the Proxmox host.
- `--remote-repo-root <path>`: Repo root on Proxmox host (default `/var/lib/homelab-proxmox`).
- `--apply-network`: Apply network restore step (opt-in).
- `--apply-fstab`: Apply fstab restore step (opt-in).
- `REBUILD_IMMICH_CTID=<ctid>`: Override Immich CTID lookup (alternatively set `immich_ctid` in scripts/lab/rebuild-config.json).
- `SSH_TARGET=<alias>`: Use a specific SSH config host alias (defaults to `PROXMOX_HOST`).

## State Architecture

### Storage Locations

**NAS-Backed State** (current):
- Path: `/mnt/nas/homelab_ci/infra_state/<environment>/<service>/terraform.tfstate`
- Environments: `lab`, `prod` (production)
- Access:
  - **PVE**: via `/mnt/nas/homelab_ci` NFS mount
  - **Laptop**: via `/Volumes/nas/homelab_ci` autofs (see [docs/runbooks/laptop-nfs-setup.md](../../docs/runbooks/laptop-nfs-setup.md))
  - **GH Actions**: via symlinks at `/var/lib/homelab-proxmox/state/services/<service>/` (transitional)

**Legacy State** (deprecated, backward compatibility only):
- Path: `/var/lib/homelab-proxmox/state/services/<service>/terraform.tfstate`
- Used by: GH Actions workflows (via symlinks during transition)
- Status: Symlinks point to NAS-backed state
- Removal: After all workflows migrated to USE_NAS_STATE mode

### Environment Separation

State files are isolated per environment to prevent cross-environment pollution:
- **Lab**: `infra_state/lab/<service>/` - Testing and development
- **Production**: `infra_state/prod/<service>/` - Production services

The `ENVIRONMENT` variable must be set correctly to access the appropriate state.

### Enabling NAS State

For services phase execution from laptop:
```bash
export USE_NAS_STATE=true
export ENVIRONMENT=lab  # or static
# Use single quotes to avoid zsh history expansion (!)
export PROXMOX_API_TOKEN_ID='root@pam!rebuild'
export PROXMOX_API_TOKEN_SECRET='<secret>'

task rebuild:plan -- --phase services
```

Without `USE_NAS_STATE=true`, scripts use legacy paths (backward compatible).

## Evidence Outputs

Evidence is stored locally under [artifacts/rebuild-runs](artifacts/rebuild-runs) in a run-specific directory:

- reports/preflight-summary.txt
- reports/rebuild-phase-summary.md
- reports/restore/restore-summary.txt
- reports/iac/iac-summary.txt
- reports/services/
- reports/verify/verify-summary.txt
- state.json

## Guardrails

- Lab is the default environment.
- Prod runs require an explicit confirmation string.
- Apply runs require an explicit confirmation string even in lab.
- Network and fstab restores require opt-in flags.
