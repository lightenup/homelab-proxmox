# Immich Maintenance Guide

## Current Version

Immich is currently running **v2.4.0** (upgraded from v1.121.0 in December 2024).

## Upgrading Immich

Immich is deployed via Ansible using Docker Compose. To upgrade Immich to a new version:

### Pre-Upgrade Checklist

1. **Check Release Notes**: Review the [Immich Release Notes](https://github.com/immich-app/immich/releases) for any breaking changes or special upgrade instructions.
2. **Verify Backup**: Ensure the automated backup process is working and recent backups exist.
3. **Check Storage**: Verify NAS mount is healthy and has sufficient space.
4. **Note Current Version**: Record the current version for rollback purposes.

### Upgrade Procedure

1. **Update Version Variable**:
   Edit `ansible/group_vars/services/vars.yml` and update the `immich_version` variable:

   ```yaml
   immich_version: "v2.4.0" # Update this to the desired version
   ```

   > **Note**: Always pin to a specific version (e.g., `v2.4.0`) rather than using `release` or `v2` tags. This ensures controlled, tested upgrades.

2. **Review Template Changes** (if major version upgrade):
   - Check if docker-compose structure has changed in new version
   - Review environment variables for deprecations or new requirements
   - Compare against upstream: https://docs.immich.app/install/docker-compose

3. **Run Ansible Playbook**:
   Run the site playbook targeting only the Immich host:

   ```bash
   ansible-playbook -i ansible/inventories/generated/hosts.yml \
     ansible/playbooks/site.yml \
     --limit immich \
     --ask-vault-pass
   ```

   The playbook will automatically:
   - Run preflight checks (NAS mount, Docker daemon, disk space)
   - Backup existing compose directory with timestamp
   - Update docker-compose.yml and .env files
   - Pull new Docker images
   - Recreate containers with new version
   - Remove orphaned containers
   - Wait for services to be healthy
   - Verify API health endpoint

4. **Verify Upgrade Success**:
   After playbook completes, run these verification steps:

   ```bash
   # Check all containers are running and healthy
   ssh root@192.168.1.213 "cd /opt/immich-app && docker compose ps"

   # Verify API responds
   curl -f http://192.168.1.213:2283/api/server/ping

   # Check web UI loads
   # Navigate to http://192.168.1.213:2283

   # Verify uploads work
   # Upload a test photo via web UI and confirm it appears in gallery
   ```

5. **Test Idempotency** (recommended):
   Re-run the playbook to confirm it completes with no changes:

   ```bash
   ansible-playbook -i ansible/inventories/generated/hosts.yml \
     ansible/playbooks/site.yml \
     --limit immich \
     --ask-vault-pass
   ```

   Expected output: `changed=0` with all tasks showing "ok"

### Rollback Procedure

If the upgrade causes issues, you can rollback to the previous version:

1. **Locate Backup**:
   Backups are created automatically in `/opt/immich-app.backup-<timestamp>` on the Immich LXC.

   ```bash
   ssh root@192.168.1.213 "ls -ld /opt/immich-app.backup-*"
   ```

2. **Stop Current Stack**:
   ```bash
   ssh root@192.168.1.213 "cd /opt/immich-app && docker compose down"
   ```

3. **Restore Backup**:
   ```bash
   ssh root@192.168.1.213 "rm -rf /opt/immich-app && \
     cp -r /opt/immich-app.backup-YYYYMMDD-HHMMSS /opt/immich-app"
   ```

4. **Revert Version in Ansible**:
   Edit `ansible/group_vars/services/vars.yml` and set `immich_version` back to the previous version.

5. **Redeploy with Ansible**:
   ```bash
   ansible-playbook -i ansible/inventories/generated/hosts.yml \
     ansible/playbooks/site.yml \
     --limit immich \
     --ask-vault-pass
   ```

6. **Verify Rollback**:
   - Check containers are running
   - Verify web UI is accessible
   - Confirm API responds
   - Test that existing uploads are still accessible

## Backup and Restore

### Storage Locations

Immich v2 uses the following storage locations:

-   **Photo Library (NAS)**: `/mnt/immich/library-v2` - User-uploaded photos and videos stored on NAS
-   **Database (Local)**: `/opt/immich-data/postgres` - PostgreSQL data on LXC local disk for performance
-   **Configuration**: `/opt/immich-app/` - Docker Compose files and environment config

The NAS mount `/mnt/immich` is a bind mount from Proxmox host's `/mnt/nas/homelab_immich` which connects to Synology NAS export `192.168.1.109:/volume1/homelab_immich`.

### Backup Strategy

1. **Automated Backups**: The `immich_backup` role handles automated database backups (see [immich-backup-restore.md](immich-backup-restore.md))
2. **Photo Library**: Photos on NAS are protected by NAS's own backup strategy
3. **Configuration**: Compose files are backed up automatically before upgrades and stored in version control

### Manual Backup

To manually backup before major changes:

```bash
# Backup database
ssh root@192.168.1.213 "cd /opt/immich-app && \
  docker compose exec -T database pg_dumpall -U postgres > /mnt/immich/backups/manual-backup-$(date +%Y%m%d).sql"

# Backup configuration
ssh root@192.168.1.213 "tar -czf /mnt/immich/backups/config-backup-$(date +%Y%m%d).tar.gz \
  -C /opt/immich-app docker-compose.yml .env"
```

Ensure these directories are included in your NAS backup plan.

## Health Checks

### Quick Health Verification

```bash
# Check all containers are healthy
ssh root@192.168.1.213 "cd /opt/immich-app && docker compose ps"

# Check API health endpoint
curl -f http://192.168.1.213:2283/api/server/ping

# Check web UI
# Navigate to http://192.168.1.213:2283
```

### Expected Container Status

All four containers should show status "Up" with "(healthy)":

- `immich_server` - Main API and web interface
- `immich_machine_learning` - ML features (face recognition, object detection)
- `immich_redis` - Cache and session storage
- `immich_postgres` - Database

## Troubleshooting

### Container Issues

**Check Logs**:
```bash
# View logs for specific service
ssh root@192.168.1.213 "cd /opt/immich-app && docker compose logs immich_server --tail 100"

# View all service logs
ssh root@192.168.1.213 "cd /opt/immich-app && docker compose logs --tail 50"

# Follow logs in real-time
ssh root@192.168.1.213 "cd /opt/immich-app && docker compose logs -f"
```

**Check Container Status**:
```bash
ssh root@192.168.1.213 "cd /opt/immich-app && docker compose ps"
```

**Restart Containers**:
```bash
# Restart specific service
ssh root@192.168.1.213 "cd /opt/immich-app && docker compose restart immich_server"

# Restart all services
ssh root@192.168.1.213 "cd /opt/immich-app && docker compose restart"
```

### Storage Issues

**Verify NAS Mount**:
```bash
# Check mount exists
ssh root@192.168.1.213 "test -d /mnt/immich && echo 'Mount OK' || echo 'Mount MISSING'"

# Check writable
ssh root@192.168.1.213 "touch /mnt/immich/test.txt && rm /mnt/immich/test.txt && echo 'Writable' || echo 'Not writable'"

# Check from Proxmox host
ssh root@proxmox-host "ls -la /mnt/nas/homelab_immich/library-v2"
```

**Check Disk Space**:
```bash
# Inside LXC
ssh root@192.168.1.213 "df -h"

# Database size
ssh root@192.168.1.213 "du -sh /opt/immich-data/postgres"

# Library size
ssh root@192.168.1.213 "du -sh /mnt/immich/library-v2"
```

### Database Issues

**Check Database Connection**:
```bash
ssh root@192.168.1.213 "cd /opt/immich-app && \
  docker compose exec database psql -U postgres -d immich -c '\dt'"
```

**Check Database Logs**:
```bash
ssh root@192.168.1.213 "cd /opt/immich-app && docker compose logs database --tail 100"
```

### API/Web UI Issues

**Test API Endpoint**:
```bash
# Health check
curl -f http://192.168.1.213:2283/api/server/ping

# Get server version
curl -s http://192.168.1.213:2283/api/server/version | jq .
```

**Check Network Connectivity**:
```bash
# From Ansible control node
nc -zv 192.168.1.213 2283

# Check container ports
ssh root@192.168.1.213 "ss -tlnp | grep 2283"
```

### Performance Issues

**Check Container Resources**:
```bash
ssh root@192.168.1.213 "docker stats --no-stream"
```

**Check System Resources**:
```bash
ssh root@192.168.1.213 "free -h && uptime"
```

## Common Issues and Solutions

### Issue: Containers Not Starting

**Symptoms**: `docker compose ps` shows containers in "Exit" or "Restarting" state

**Solutions**:
1. Check logs for error messages
2. Verify environment variables in `.env` file
3. Check disk space is sufficient
4. Verify NAS mount is accessible
5. Try recreating containers: `docker compose up -d --force-recreate`

### Issue: Can't Upload Photos

**Symptoms**: Upload fails or photos not appearing

**Solutions**:
1. Verify NAS mount is writable
2. Check UPLOAD_LOCATION in `.env` matches actual path
3. Check container logs for permission errors
4. Verify directory ownership: `ls -la /mnt/immich/library-v2`

### Issue: Mobile App Can't Connect

**Symptoms**: Mobile app shows connection error

**Solutions**:
1. Verify server is accessible: `curl http://192.168.1.213:2283/api/server/ping`
2. Check firewall rules allow port 2283
3. Verify URL in mobile app matches server IP
4. Check if mDNS name resolves: `immich.local` (if configured)
5. Update mobile app to compatible version with Immich v2

### Issue: High Memory Usage

**Symptoms**: Container or LXC running out of memory

**Solutions**:
1. Check machine learning model cache size
2. Reduce concurrent ML jobs in Immich settings
3. Consider increasing LXC memory allocation
4. Review ML settings in Immich admin panel

## Emergency Procedures

### Complete Service Restart

```bash
# Stop all services
ssh root@192.168.1.213 "cd /opt/immich-app && docker compose down"

# Start all services
ssh root@192.168.1.213 "cd /opt/immich-app && docker compose up -d"

# Wait for healthy status
sleep 30
ssh root@192.168.1.213 "cd /opt/immich-app && docker compose ps"
```

### Force Redeploy via Ansible

```bash
ansible-playbook -i ansible/inventories/generated/hosts.yml \
  ansible/playbooks/site.yml \
  --limit immich \
  --ask-vault-pass
```

## References

- [Immich Documentation](https://docs.immich.app/)
- [Immich Docker Compose Install](https://docs.immich.app/install/docker-compose)
- [Immich Environment Variables](https://docs.immich.app/install/environment-variables)
- [Immich GitHub Releases](https://github.com/immich-app/immich/releases)
