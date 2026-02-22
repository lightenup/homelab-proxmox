# Quickstart: CI Fresh-Deploy Pipeline Fixes

**Branch**: `037-ci-fresh-deploy-fixes`

## What Changes

Two new post-create steps are added to `pve-service-deploy apply`, inserted between
Terraform apply + CTID extraction and the SSH wait loop:

1. **Deploy key injection** (Tier 2): `pct exec` writes `id_lxc_deploy.pub` into the
   container's `/root/.ssh/authorized_keys` — idempotent, preserves existing keys.
2. **Network reachability check**: `ping -c 1 -W 5 <ip>` — hard gate with diagnostic
   capture on failure via `pct exec`.

The SSH wait timeout default is reduced from 300s to 120s.

## Flow (cmd_apply)

```
Terraform apply → extract CTID → extract service_ip
  → [NEW] inject_deploy_key(ctid, lxc_key_file)
  → [NEW] check_network_reachability(ctid, service_ip)
  → [MODIFIED] SSH wait loop (default 120s, was 300s)
  → DNS check → Feature flags → Bind mounts → Ansible bootstrap → Healthcheck
```

## Testing Locally

```bash
# Dry-run the orchestrator for an existing service (idempotent — safe)
SSH_WAIT_SECONDS=30 ./scripts/lab/pve-service-deploy apply \
  --environment lab --service jellyfin

# The deploy key injection should log "skipped (already present)"
# The network check should log "ping_status=ok"
```

## Testing in CI

Trigger "Lab 1 — LXC Promote" workflow for `nextcloud` (the service that
exposed the defect). The pipeline should complete without manual key injection.

## Evidence Artifacts

After a successful run, check the evidence pack:
- `reports/apply/lxc-deploy-key.txt` — key injection proof
- `reports/apply/network-check.txt` — network reachability proof
