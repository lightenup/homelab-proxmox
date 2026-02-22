# Data Model: Proxmox Token Privilege Separation

**Feature Branch**: `036-token-privilege-separation`
**Date**: 2026-02-22

## Entities

### 1. Token Tier (Conceptual — documentation only)

| Field | Type | Description |
|-------|------|-------------|
| tier_number | integer (1–3) | Privilege level |
| credential | string | Token ID or grant description |
| scope | string | Allowed operations |
| used_by | string | Which system/context uses this tier |

**Instances** (static, not stored):

| Tier | Credential | Scope | Used By |
|------|-----------|-------|---------|
| 1 | `terraform@pve!terraform-token` | Container lifecycle, network, rootfs, SSH keys | Terraform (CI + laptop) |
| 2 | `ci` user + passwordless `sudo pct` | `pct set -features`, `pct set -mp<N>`, `pct reboot` | Orchestrator post-create (CI + laptop) |
| 3 | `root@pam!rebuild` | Full Proxmox API | Manual operator only (DR) |

**Invariants**:
- Tier 1 is the only credential passed to Terraform.
- Tier 2 is exercised only by the orchestrator post-create step.
- Tier 3 is never referenced in automated flows.

### 2. Service Mountpoint (tfvars variable)

**Source**: `service_mountpoints` in `terraform/environments/*.tfvars`

**Type** (HCL):
```hcl
map(map(object({
  mp       = string              # Container-side mount path
  volume   = string              # Host-side path or storage volume
  readonly = optional(bool)      # Read-only flag (default: false) — NEW
  size     = optional(string)    # Disk size (storage-backed only)
  slot     = optional(number)    # Mount slot (storage-backed only)
  key      = optional(string)    # Mount key (storage-backed only)
  storage  = optional(string)    # Storage pool (storage-backed only)
})))
```

**Classification rule**: If `volume` starts with `/`, it is a **host-path bind mount** (consumed by orchestrator). Otherwise, it is a **storage-backed volume** (consumed by Terraform module).

**Example**:
```hcl
service_mountpoints = {
  nextcloud = {
    data = {
      mp       = "/mnt/nextcloud"
      volume   = "/mnt/nas/homelab_nextcloud"
      # readonly defaults to false (read-write)
    }
  }
  jellyfin = {
    video = {
      mp       = "/media/video"
      volume   = "/mnt/nas/video"
      readonly = true
    }
  }
}
```

### 3. Bind Mount Operation Result

**Structure** (internal to orchestrator, emitted in step summary):

| Field | Type | Description |
|-------|------|-------------|
| host_path | string | Host-side mount path (volume) |
| container_path | string | Container-side mount point (mp) |
| permission | "ro" \| "rw" | Derived from `readonly` flag |
| result | "applied" \| "skipped" \| "failed" | Operation outcome |
| detail | string (optional) | Failure cause + remediation (FR-018) |
| mp_index | integer | The `mp<N>` index used |

### 4. Evidence Artifact — Bind Mount Report

**File**: `reports/apply/lxc-bind-mounts.txt` (one per run)

**Schema** (text key=value format, matching existing `lxc-features.txt` pattern):
```
ctid=<container_id>
service=<service_slug>
mount_count=<N>
--- mount 0 ---
host_path=<volume>
container_path=<mp>
permission=<ro|rw>
mp_index=<N>
result=<applied|skipped|failed>
--- pct config (before) ---
<filtered pct config output>
--- pct config (after) ---
<filtered pct config output>
```

### 5. Step Summary (CI / terminal output)

**Destination**: `$GITHUB_STEP_SUMMARY` (CI) or stdout (laptop)

**Format**: Markdown table (see research.md R-006)

## State Transitions

### Container Mount Lifecycle

```
[No mounts] → orchestrator reads tfvars → validate allowlist
  → [Allowed] → check existing mounts (pct config)
    → [Already exists] → result=skipped
    → [New mount] → pct set → result=applied
  → [Disallowed] → result=failed (allowlist violation)
→ [Any applied?] → pct reboot → wait SSH
→ [All skipped/none] → no reboot
→ Emit summary + evidence
```

## Relationships

```
service_mountpoints (tfvars)
  ├── storage-backed volumes ──→ Terraform mountpoint {} block (filtered by startswith check)
  └── host-path bind mounts ──→ Orchestrator post-create step
        ├── validate against allowlist (/mnt/nas/)
        ├── check idempotency (pct config comparison)
        ├── apply via sudo pct set -mp<N>
        ├── reboot if new mounts applied
        └── emit evidence (lxc-bind-mounts.txt) + step summary
```
