# Plan: Backups & Restore Drill

## Phase 1: Backup Implementation

This phase focuses on creating the Ansible role and tasks to perform the backup and manage retention.

*   **Step 1.1:** Define variables for backup paths, retention, and scheduling in `ansible/group_vars/services/vars.yml` (or a new `backup` group).
*   **Step 1.2:** Create `ansible/roles/immich_backup` structure.
*   **Step 1.3:** Implement the backup script template (`backup.sh.j2`) that handles `pg_dump`, compression, and rotation/pruning.
*   **Step 1.4:** Implement Ansible tasks to deploy the script and set up a Systemd timer (or Cron job) for daily execution.
*   **Step 1.5:** Create `ansible/playbooks/backup.yml` to trigger an immediate backup (wrapping the role).

## Phase 2: Restore Drill Implementation

This phase implements the verification logic.

*   **Step 2.1:** Create `ansible/playbooks/restore-drill.yml`.
*   **Step 2.2:** Implement tasks to:
    *   Identify the latest backup file.
    *   Generate a temporary `docker-compose.restore.yml` (using unique project name and ports).
    *   Start the test database container.
    *   Restore the database dump.
    *   Start the test application container.
    *   Wait for health check (`/api/server/ping`).
    *   Tear down the test stack.

## Phase 3: Documentation & Verification

*   **Step 3.1:** Run the backup playbook and verify artifacts on the NAS.
*   **Step 3.2:** Run the restore drill playbook and verify success.
*   **Step 3.3:** Create `docs/immich-backup-restore.md` detailing the process, locations, and manual recovery steps.

## Execution Order

1.  Implement Phase 1 (Backup).
2.  Verify Backup.
3.  Implement Phase 2 (Restore Drill).
4.  Verify Restore Drill.
5.  Write Documentation.
