# Immich Backup & Restore

## Overview

This document describes the backup strategy and restore procedures for the Immich instance.

## Backup Strategy

- **Frequency**: Daily at 04:30 AM.
- **Content**:
  - PostgreSQL Database Dump (using `pg_dump`).
  - `docker-compose.yml` and `.env` files.
  - **Note**: The actual media library (`upload` volume) is backed up separately via NAS snapshots/replication (not covered by this script).
- **Location**: `/mnt/immich/backups` (Mounted from Synology NAS).
- **Retention Policy**:
  - Daily: 7 days
  - Weekly: 4 weeks
  - Monthly: 12 months

### Automated Backup

The backup is handled by a Systemd timer on the Immich host (`immich-backup.timer`).
It executes `/usr/local/bin/backup_immich.sh`.

### Manual Backup

You can trigger a backup manually via Ansible:

```bash
ansible-playbook ansible/playbooks/backup.yml -i ansible/inventories/generated/hosts.yml
```

Or directly on the host:

```bash
sudo /usr/local/bin/backup_immich.sh
```

## Restore Drill

A "Restore Drill" is an automated test that verifies the integrity of the backups. It does **not** overwrite the production instance.

### How it works

1. Finds the latest backup tarball.
2. Extracts it to a temporary directory (`/tmp/immich-restore-drill`).
3. Creates a mock directory structure for uploads (required for server startup).
4. Starts a parallel Immich stack on port **2284**.
5. Restores the database dump into the test database.
6. Verifies the API is reachable (`/api/server/ping`).
7. Tears down the test stack and cleans up.

### Running the Drill

```bash
ansible-playbook ansible/playbooks/restore-drill.yml -i ansible/inventories/generated/hosts.yml
```

## Disaster Recovery (Manual Restore)

In case of a total failure, follow these steps to restore the service.

1. **Stop the existing stack**:
   ```bash
   cd /opt/immich
   docker compose down
   ```

2. **Locate the backup**:
   Find the latest backup in `/mnt/immich/backups`.
   ```bash
   ls -l /mnt/immich/backups
   ```

3. **Extract the backup**:
   ```bash
   tar -xzf /mnt/immich/backups/immich-backup-YYYYMMDD-HHMMSS.tar.gz -C /tmp/restore
   ```

4. **Restore Configuration**:
   Copy the `docker-compose.yml` and `.env` if they are missing or corrupted.
   ```bash
   cp /tmp/restore/docker-compose.yml /opt/immich/
   cp /tmp/restore/.env /opt/immich/
   ```

5. **Start the Database**:
   Start only the database container first.
   ```bash
   docker compose up -d database redis
   ```

6. **Restore the Database**:
   Drop the existing database (if needed) and restore from dump.
   ```bash
   cat /tmp/restore/dump.sql | docker exec -i immich_postgres psql -U postgres immich
   ```

7. **Start the rest of the stack**:
   ```bash
   docker compose up -d
   ```

8. **Verify**:
   Check logs and access the web UI.
