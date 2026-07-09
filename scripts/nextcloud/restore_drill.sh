#!/bin/bash
# restore_drill.sh — On-demand Nextcloud restore drill (run on the Nextcloud LXC, VMID 105).
#
# Steps:
#   1. Verify NFS backup target is reachable (fail-closed if not)
#   2. Trigger nextcloud-backup.service to force a fresh artefact
#   3. Select the newest artefact from /mnt/nextcloud/backups/
#   4. Capture the live oc_users sentinel count
#   5. Extract the artefact's DB dump into a temporary directory
#   6. Import the dump into a scratch mariadb:11 container
#   7. Assert import rc=0 and oc_users count matches the live sentinel
#   8. Print ROLLBACK_ARTEFACT=<path> (the rollback point for the next hop)
#   9. Tear down the scratch container and temp directory
#   Exits non-zero on any failure (fail-closed).
#
# LIVE RESTORE PROCEDURE (FR-010) — use this if a hop fails and rollback is needed:
#   Prerequisites: record ROLLBACK_ARTEFACT from the pre-hop drill run.
#
#   1. Extract the artefact:
#        mkdir -p /tmp/nc_restore
#        tar -xzf "$ROLLBACK_ARTEFACT" -C /tmp/nc_restore --strip-components=1
#
#   2. Enable maintenance mode:
#        docker exec -u www-data nextcloud_app php occ maintenance:mode --on
#
#   3. Drop and recreate the live database (source .env first for credentials):
#        source <(grep '^MYSQL_' /opt/nextcloud/.env)
#        docker exec nextcloud_db mariadb -u root -p"$MYSQL_ROOT_PASSWORD" -e \
#          "DROP DATABASE $MYSQL_DATABASE; \
#           CREATE DATABASE $MYSQL_DATABASE CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;"
#
#   4. Import the dump:
#        docker exec -i nextcloud_db \
#          mariadb -u root -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE" \
#          < /tmp/nc_restore/dump.sql
#
#   5. Restore config.php if present in the artefact:
#        [[ -f /tmp/nc_restore/config.php ]] && \
#          docker cp /tmp/nc_restore/config.php nextcloud_app:/var/www/html/config/config.php
#
#   6. Revert the image pin one major back in group_vars/services/vars.yml
#      and re-run the pipeline (Prod 1 → Prod 2 for service=nextcloud).
#
#   7. Disable maintenance mode after the pipeline completes:
#        docker exec -u www-data nextcloud_app php occ maintenance:mode --off
#
#   8. Verify: docker exec -u www-data nextcloud_app php occ status
#        Expected: versionstring=<previous-major>.x, maintenance=false, needsDbUpgrade=false
#
#   9. Clean up: rm -rf /tmp/nc_restore

set -euo pipefail

INSTALL_DIR="/opt/nextcloud"
BACKUP_DIR="/mnt/nextcloud/backups"
SCRATCH_CONTAINER="nc_drill_db"
SCRATCH_ROOT_PASS="drill_tmp_$(date +%s)_$$"

err() { echo "ERROR: $*" >&2; exit 1; }

cleanup() {
    docker rm -f "$SCRATCH_CONTAINER" >/dev/null 2>&1 || true
    [[ -n "${TMPDIR:-}" ]] && rm -rf "$TMPDIR"
}
trap cleanup EXIT

# --- 0. NFS fail-closed check ---
if ! timeout 5 ls "$BACKUP_DIR" >/dev/null 2>&1; then
    err "NFS backup target unreachable at $BACKUP_DIR. Fix the mount and retry."
fi

# --- 1. Read credentials from .env ---
ENV_FILE="$INSTALL_DIR/.env"
[[ -f "$ENV_FILE" ]] || err ".env not found at $ENV_FILE"
MYSQL_USER=$(grep '^MYSQL_USER=' "$ENV_FILE" | cut -d'=' -f2-)
MYSQL_PASSWORD=$(grep '^MYSQL_PASSWORD=' "$ENV_FILE" | cut -d'=' -f2-)
MYSQL_DATABASE=$(grep '^MYSQL_DATABASE=' "$ENV_FILE" | cut -d'=' -f2-)
[[ -n "$MYSQL_USER" && -n "$MYSQL_PASSWORD" && -n "$MYSQL_DATABASE" ]] \
    || err "Failed to parse MYSQL_USER / MYSQL_PASSWORD / MYSQL_DATABASE from $ENV_FILE"

# --- 2. Capture live sentinel before backup (so we compare against a stable baseline) ---
LIVE_USER_COUNT=$(docker exec nextcloud_db \
    mariadb -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" \
    --batch --skip-column-names \
    "$MYSQL_DATABASE" \
    -e "SELECT COUNT(*) FROM oc_users;" 2>/dev/null) \
    || err "Failed to query live DB sentinel."
echo "Live sentinel: oc_users = $LIVE_USER_COUNT"

# --- 3. Force a fresh backup artefact ---
echo "Triggering nextcloud-backup.service..."
systemctl start nextcloud-backup.service \
    || err "nextcloud-backup.service failed. Check: journalctl -u nextcloud-backup.service"
echo "Backup service completed."

# --- 4. Select newest artefact ---
ARTEFACT=$(ls -t "$BACKUP_DIR"/nextcloud-backup-*.tar.gz 2>/dev/null | head -1)
[[ -n "$ARTEFACT" ]] || err "No backup artefact found in $BACKUP_DIR after triggering service."
echo "Selected artefact: $ARTEFACT"

# --- 5. Extract dump to a temp directory ---
TMPDIR=$(mktemp -d)
tar -xzf "$ARTEFACT" -C "$TMPDIR" --strip-components=1 \
    || err "Failed to extract artefact: $ARTEFACT"
DUMP_FILE="$TMPDIR/dump.sql"
[[ -f "$DUMP_FILE" ]] || err "dump.sql not found inside artefact $ARTEFACT"

# --- 6. Start scratch MariaDB container ---
echo "Starting scratch MariaDB container ($SCRATCH_CONTAINER)..."
docker run -d --name "$SCRATCH_CONTAINER" \
    -e MYSQL_ROOT_PASSWORD="$SCRATCH_ROOT_PASS" \
    -e MYSQL_DATABASE="$MYSQL_DATABASE" \
    mariadb:11 >/dev/null

# Wait for MariaDB to accept connections (up to 60 s)
READY=0
for i in $(seq 1 30); do
    if docker exec "$SCRATCH_CONTAINER" \
        mariadb -u root -p"$SCRATCH_ROOT_PASS" -e "SELECT 1;" >/dev/null 2>&1; then
        READY=1
        break
    fi
    sleep 2
done
[[ "$READY" -eq 1 ]] || err "Scratch MariaDB did not become ready within 60 s."

# --- 7. Import dump ---
echo "Importing DB dump..."
docker exec -i "$SCRATCH_CONTAINER" \
    mariadb -u root -p"$SCRATCH_ROOT_PASS" "$MYSQL_DATABASE" \
    < "$DUMP_FILE" \
    || err "DB dump import failed."
echo "Import succeeded (rc=0)."

# --- 8. Assert sentinel in drill DB ---
DRILL_USER_COUNT=$(docker exec "$SCRATCH_CONTAINER" \
    mariadb -u root -p"$SCRATCH_ROOT_PASS" \
    --batch --skip-column-names \
    "$MYSQL_DATABASE" \
    -e "SELECT COUNT(*) FROM oc_users;" 2>/dev/null) \
    || err "Failed to query oc_users from drill DB."

echo "Drill sentinel: oc_users = $DRILL_USER_COUNT"

[[ "$DRILL_USER_COUNT" -gt 0 ]] \
    || err "Sentinel check failed: oc_users count is 0 in restored dump."

[[ "$DRILL_USER_COUNT" == "$LIVE_USER_COUNT" ]] \
    || err "Sentinel mismatch: live=$LIVE_USER_COUNT drill=$DRILL_USER_COUNT."

# --- 9. Report ---
echo ""
echo "Verification Status: PASS"
echo "ROLLBACK_ARTEFACT=$ARTEFACT"
