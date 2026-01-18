# Data Model

## Entities

### Encrypted Backup Set
Represents the complete Hyper Backup dataset stored in Hetzner S3.

**Fields**
- `bucket_name` (string, required): Hetzner S3 bucket name.
- `pool_prefix` (string, required): Pool directory prefix (e.g., Pool/0/0).
- `size_estimate_bytes` (integer, required): rclone size estimate.
- `snapshot_timestamp` (datetime, required): Backup snapshot time.
- `encryption_key_ref` (string, required): Reference to secure storage for the encryption key (no secrets in repo).

**Validation Rules**
- `size_estimate_bytes` must be greater than 0.
- `pool_prefix` must start with `Pool/`.

---

### DR Staging Location
Represents the NAS share where the backup is downloaded.

**Fields**
- `nas_share_path` (string, required): `/volume1/homelab_dr_test`.
- `pve_mount_path` (string, required): `/mnt/nas/homelab_dr_test`.
- `free_space_bytes` (integer, required): Measured free space prior to download.

**Validation Rules**
- `free_space_bytes` must be >= 2 × `size_estimate_bytes`.
- `pve_mount_path` must be mounted and writable.

---

### Drill Report
Captures the outcome of a drill run.

**Fields**
- `drill_id` (string, required): Unique identifier (date-based).
- `run_timestamp` (datetime, required): Start time of the drill.
- `operator` (string, required): Person running the drill.
- `backup_set_ref` (string, required): Identifier for the Encrypted Backup Set.
- `staging_location_ref` (string, required): Identifier for the DR Staging Location.
- `steps_completed` (array of strings, required): Ordered steps executed.
- `outcome` (enum, required): `success`, `partial`, `failed`.
- `issues` (array of strings, optional): Blockers or failures encountered.
- `artifacts` (array of strings, optional): Paths or links to logs/screenshots.

**Validation Rules**
- `outcome` must match one of `success`, `partial`, `failed`.
- `steps_completed` must include a decryption validation step when `outcome` is `success`.

**State Transitions**
- `planned` → `in_progress` → `success` | `partial` | `failed`

## Relationships
- `Drill Report` references one `Encrypted Backup Set` and one `DR Staging Location`.
