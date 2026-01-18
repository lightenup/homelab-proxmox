# Phase 0 Research

## Decisions

### 1) Publish a dedicated DR drill runbook in docs/runbooks
- **Decision**: Create a standalone runbook at docs/runbooks/dr-drill-playbook.md for the end-to-end drill.
- **Rationale**: Keeps DR procedures discoverable, versioned, and separate from script README notes; aligns with existing docs/runbooks structure.
- **Alternatives considered**: Embed in scripts/dr/README.md; use a quickstart-only doc in the spec folder.

### 2) Use the dedicated DR test NAS share for downloads
- **Decision**: Target `/volume1/homelab_dr_test`, mounted on PVE at `/mnt/nas/homelab_dr_test`.
- **Rationale**: Prevents accidental overwrites of production data and isolates drill artifacts.
- **Alternatives considered**: Reuse existing CI/share; make the target path variable for each run.

### 3) Enforce readiness check of free space >= 2× rclone size estimate
- **Decision**: Require free space to be at least double the rclone size estimate before initiating download.
- **Rationale**: Provides a safety margin for metadata and download overhead; avoids partial downloads.
- **Alternatives considered**: 1× estimate; fixed GB threshold.

### 4) Preserve Hyper Backup Pool directory structure
- **Decision**: Download the full Pool/0/0... structure from Hetzner S3 without flattening or filtering.
- **Rationale**: DSM Hyper Backup Explorer requires the complete structure to validate decryption and integrity.
- **Alternatives considered**: Partial download; selective folders only.

### 5) Validate decryption using DSM Hyper Backup Explorer
- **Decision**: Use DSM Hyper Backup Explorer for the final validation step.
- **Rationale**: Confirms the restoration chain end-to-end within the Synology-supported tool.
- **Alternatives considered**: Command-line restore validation only; skipping decryption validation.
