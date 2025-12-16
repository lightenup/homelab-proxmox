## Clarifications

### Session 2025-12-16
- Q: How should backup success/failure be reported? → A: Log to systemd journal only (Option A).
- Q: What if the NAS mount is unavailable? → A: Fail immediately (Option A).
- Q: Should the restore drill cleanup the test stack? → A: Always cleanup (Option A).
- Q: What time should the daily backup run? → A: 04:30 AM.
- Q: What is the target database container name? → A: immich_postgres.

## 1. Overview

This feature implements a robust, automated backup and restore strategy for the Immich service. It focuses on the critical application state (Postgres database) and ensures that backups are stored safely on the Synology NAS. Crucially, it includes a "Restore Drill" capability to verify that backups are valid and can be used to recover the service.

## 2. Goals

*   **Automated Backups:** Schedule nightly backups of the Immich Postgres database.
*   **Safe Storage:** Store backups on the Synology NAS (mounted via NFS).
*   **Retention Policy:** Maintain a history of backups (Daily: 7, Weekly: 4, Monthly: 6).
*   **Verified Recovery:** Provide an automated "drill" to restore a backup into a test instance and verify functionality.
*   **Infrastructure-as-Code:** Manage all backup/restore logic via Ansible.

## 3. Scope

### In Scope
*   **Immich Database:** Full `pg_dump` of the `immich_postgres` container.
*   **Configuration:** Backup of `docker-compose.yml` and `.env` (sanitized or encrypted if needed, though Ansible Vault is the source of truth).
*   **Storage:** Saving artifacts to a dedicated folder on the existing NAS share.
*   **Restore Drill:** A playbook to spin up a temporary, isolated Immich stack on the same host, restore the DB, and check health.

### Out of Scope
*   **Media Files:** Backup of the actual photo/video library is handled by Synology-side snapshots/Hyper Backup (not managed by this spec).
*   **Proxmox Backup Server (PBS):** Not used for this v1 implementation.
*   **Off-site Backups:** Cloud replication is a future enhancement.

## 4. Architecture & Design

### 4.1 Backup Strategy
*   **Source:** `immich_postgres` Docker container.
*   **Method:** `pg_dump` executed via `docker exec`.
*   **Destination:** `/mnt/media/backups/immich` (path to be confirmed/configured in vars).
*   **Format:** Compressed SQL dump (`.sql.gz`).
*   **Scheduling:** Systemd timer managed by Ansible (or Ansible cron).

### 4.2 Restore Drill Strategy
To avoid disrupting the production instance or requiring complex Terraform operations, the restore drill will:
1.  **Target:** The existing `immich` LXC.
2.  **Isolation:** Create a secondary Docker Compose project (`immich-restore-test`).
3.  **Configuration:** Use a modified `docker-compose.yml` listening on a different port (e.g., `2284`) and using a separate DB volume.
4.  **Process:**
    *   Spin up the test stack (DB only initially).
    *   Restore the latest backup into the test DB.
    *   Start the application container.
    *   Poll `/api/server/ping` for success.
    *   Tear down the test stack and volumes.

### 4.3 Retention
*   A script or Ansible task will run post-backup to prune files in the backup directory based on the defined policy (7 daily, 4 weekly, 6 monthly).

### 4.4 Observability
*   Backup execution logs will be captured via standard systemd journaling (stdout/stderr). No external notification service is configured for v1.

## 5. Functional Requirements

*   **FR-001:** The system MUST perform a full database dump of Immich every 24 hours.
*   **FR-002:** Backups MUST be compressed (gzip) to save space.
*   **FR-003:** Backups MUST be stored on the mounted NAS share.
*   **FR-004:** The system MUST automatically delete backups older than the retention policy.
*   **FR-005:** The restore drill MUST be runnable on-demand via Ansible.
*   **FR-006:** The restore drill MUST NOT affect the running production Immich instance.
*   **FR-007:** The restore drill MUST verify that the application API is responsive.
*   **FR-008:** The backup process MUST fail immediately and exit with an error code if the destination NAS path is not writable or mounted.
*   **FR-009:** The restore drill MUST always destroy the test stack and volumes after execution, regardless of success or failure.

## 6. Configuration Variables

| Variable | Default | Description |
| :--- | :--- | :--- |
| `immich_backup_path` | `/mnt/media/backups/immich` | Path on the LXC where backups are stored. |
| `immich_backup_retention_days` | `7` | Number of daily backups to keep. |
| `immich_backup_schedule` | `*-*-* 04:30:00` | Systemd calendar schedule for the backup timer. |
| `immich_db_container_name` | `immich_postgres` | Name of the running Postgres container to dump. |
| `immich_restore_test_port` | `2284` | Port for the restore drill instance. |

## 7. Security Considerations

*   **Secrets:** Database passwords in the backup script must be handled via Ansible Vault or environment variables, never hardcoded.
*   **Access:** The backup directory should be restricted to the root/immich user.

## 8. Alternatives Considered

*   **New LXC for Restore:** Creating a fresh LXC for every drill is cleaner but requires Terraform automation or manual steps, violating the "Ansible-driven" constraint for this specific drill.
*   **In-place Restore:** Too risky for a drill; could cause data loss if the backup is corrupt.
