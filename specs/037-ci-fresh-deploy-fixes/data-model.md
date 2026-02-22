# Data Model: CI Fresh-Deploy Pipeline Fixes

**Date**: 2026-02-22 | **Branch**: `037-ci-fresh-deploy-fixes`

## Entities

This feature does not introduce persistent data models or database entities.
All changes are to the orchestrator script flow and evidence artifact files.

### Evidence Artifacts (New)

#### `reports/apply/lxc-deploy-key.txt`

Key-value report file recording deploy key injection action.

| Field | Type | Description |
|-------|------|-------------|
| `ctid` | int | Container ID |
| `key_file` | string | Path to deploy public key on PVE host |
| `key_fingerprint` | string | SSH key fingerprint (sha256) |
| `action` | enum | `injected` \| `skipped` (already present) |
| `authorized_keys_line_count_before` | int | Lines in authorized_keys before injection |
| `authorized_keys_line_count_after` | int | Lines in authorized_keys after injection |

#### `reports/apply/network-check.txt`

Key-value + section-delimited report for network reachability check.

| Field | Type | Description |
|-------|------|-------------|
| `ctid` | int | Container ID |
| `expected_ip` | string | IP address checked |
| `ping_status` | enum | `ok` \| `unreachable` |
| `--- ip addr show eth0 ---` | section | Container interface state (on failure) |
| `--- ip route ---` | section | Container routing table (on failure) |
| `--- pct config net ---` | section | Host-side network config (on failure) |

### Environment Variables (Modified)

| Variable | Old Default | New Default | Notes |
|----------|-------------|-------------|-------|
| `SSH_WAIT_SECONDS` | `300` | `120` | Spec D-005 |

### Environment Variables (Unchanged)

| Variable | Value | Notes |
|----------|-------|-------|
| `SSH_WAIT_SLEEP_SECONDS` | `5` | Step interval, unchanged |
| `ANSIBLE_LXC_SSH_KEY_FILE` | `~/.ssh/id_lxc_deploy` | Deploy key path, unchanged |
| `USE_TFVARS_SSH_KEYS` | (unset) | Bypass flag, unchanged |

## State Transitions

### Deploy Key Injection Flow

```
Container Created (Terraform apply)
  → Check container running (pct status)
    → [not running] → ERROR: "container not running"
    → [running] → Check deploy key file exists on PVE
      → [missing] → ERROR: "deploy key file not found"
      → [exists] → pct exec: check if key in authorized_keys
        → [present] → SKIP (log "already present")
        → [absent] → pct exec: mkdir + chmod + append key
          → SUCCESS (log "injected")
```

### Network Reachability Check Flow

```
Deploy Key Injected (or skipped)
  → ping -c 1 -W 5 <service_ip>
    → [success] → PASS → proceed to SSH wait loop
    → [failure] → Capture diagnostics:
      → pct exec: ip addr show eth0
      → pct exec: ip route
      → pct config: grep net
      → Write to evidence + stderr
      → FAIL → die (do NOT proceed to SSH wait)
```
