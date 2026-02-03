# Implementation Plan: Immich v2.4.0 Upgrade

**Feature**: 009-immich-v2-upgrade
**Created**: December 19, 2024
**Status**: Ready for Implementation

## Overview

This plan details the step-by-step implementation for upgrading Immich from v1.121.0 to v2.4.0. It provides both automated (Ansible) and manual (break-glass) approaches.

## Prerequisites

- [ ] NAS export `192.168.1.109:/volume1/homelab_immich` is mounted on Proxmox host at `/mnt/nas/homelab_immich`
- [ ] LXC 101 has bind mount configured: `/mnt/immich` → `/mnt/nas/homelab_immich`
- [ ] Docker and docker-compose-plugin are installed in LXC
- [ ] Ansible control node has connectivity to LXC 101 (192.168.1.213)
- [ ] Ansible vault password is available for secrets access
- [ ] Backup of current compose directory exists (will be automated)

## Track A: Ansible Automation (Primary Implementation)

### Phase 1: Update Configuration Variables

**Objective**: Update Ansible variables to specify v2 version and paths

**Steps**:
1. Edit `ansible/group_vars/services/vars.yml`:
   - Change `immich_version: "v1.121.0"` to `immich_version: "v2.4.0"`
   - Add `immich_data_dir: "/opt/immich-data"` for local database storage
   - Keep `immich_install_dir: "/opt/immich-app"` for compose files

2. Edit `ansible/roles/immich/defaults/main.yml`:
   - Update default version to v2.4.0
   - Add `immich_upload_location: "/mnt/immich/library-v2"` for NAS-backed library

**Verification**:
- Variables are syntactically correct YAML
- Version pin is explicit (v2.4.0, not v2 or release)

### Phase 2: Update Ansible Role Templates

**Objective**: Create v2-compatible docker-compose.yml and .env templates

**Steps**:
1. Update `ansible/roles/immich/templates/docker-compose.yml.j2`:
   - Replace entire file with v2 structure from upstream
   - Use 4 services: immich-server, immich-machine-learning, redis, database
   - Remove any v1 microservices container references
   - Update image references:
     - Server: `ghcr.io/immich-app/immich-server:{{ immich_version }}`
     - ML: `ghcr.io/immich-app/immich-machine-learning:{{ immich_version }}`
     - Redis: `docker.io/valkey/valkey:9@sha256:fb8d272e529ea567b9bf1302245796f21a2672b8368ca3fcb938ac334e613c8f`
     - Database: `ghcr.io/immich-app/postgres:14-vectorchord0.4.3-pgvectors0.2.0@sha256:bcf63357191b76a916ae5eb93464d65c07511da41e3bf7a8416db519b40b1c23`
   - Update volume mappings:
     - Server: `{{ immich_upload_location }}:/data` (v2 uses /data not /usr/src/app/upload)
     - Database: `{{ immich_data_dir }}/postgres:/var/lib/postgresql/data`
   - Add health checks for all services
   - Set restart policy to "always" for all services

2. Update `ansible/roles/immich/templates/.env.j2`:
   - Add UPLOAD_LOCATION={{ immich_upload_location }}
   - Add DB_DATA_LOCATION={{ immich_data_dir }}/postgres
   - Add IMMICH_VERSION={{ immich_version }}
   - Add TZ=Etc/UTC (or parameterize timezone)
   - Keep existing DB_* and REDIS_* variables
   - Remove any v1-specific variables

**Verification**:
- Template syntax is valid Jinja2
- All variable references are defined in defaults or group_vars
- Compose file matches upstream v2 structure

### Phase 3: Update Ansible Role Tasks

**Objective**: Modify role tasks to support v2 deployment and ensure idempotency

**Steps**:
1. Edit `ansible/roles/immich/tasks/main.yml`:
   - Add pre-flight check: Verify `/mnt/immich` mount exists and is writable
   - Add task: Create backup of existing compose dir (timestamped)
   - Update directory creation tasks:
     - Create `{{ immich_data_dir }}/postgres` for database
     - Create `{{ immich_upload_location }}` for library
     - Remove old v1 directory structure (library, uploads, thumbs, etc.)
   - Keep existing template deployment tasks
   - Update docker compose module to use `community.docker.docker_compose_v2`
   - Add task: Wait for port 2283 to be reachable
   - Add task: Verify API health endpoint responds

2. Create new task file `ansible/roles/immich/tasks/preflight.yml` (included from main.yml):
   - Check NAS mount exists
   - Check Docker daemon is running
   - Check sufficient disk space for database
   - Validate Ansible variables are set

3. Update handlers in `ansible/roles/immich/handlers/main.yml`:
   - Keep "Restart immich" handler
   - Ensure handler uses docker compose v2 command format

**Verification**:
- Ansible syntax check passes: `ansible-playbook --syntax-check playbooks/site.yml`
- Dry-run completes: `ansible-playbook playbooks/site.yml --check --diff`

### Phase 4: Test Ansible Deployment

**Objective**: Execute Ansible playbook and verify successful upgrade

**Steps**:
1. Run playbook against Immich LXC:
   ```bash
   ansible-playbook -i ansible/inventories/generated/hosts.yml \
     ansible/playbooks/site.yml \
     --limit immich \
     --ask-vault-pass
   ```

2. Monitor playbook execution for errors

3. Verify deployment:
   - Check containers are running: `docker compose ps` (in LXC)
   - Check API health: `curl http://192.168.1.213:2283/api/server/ping`
   - Check web UI: Navigate to http://192.168.1.213:2283
   - Verify NAS mount: Check `/mnt/immich/library-v2` exists

4. Test idempotency - re-run playbook:
   - Should complete with no changes (ok=X changed=0)
   - Containers should not restart

5. Test upload functionality:
   - Complete initial setup wizard
   - Upload test photo via web UI
   - Verify file appears in `/mnt/immich/library-v2`

**Verification**:
- All acceptance scenarios from spec pass
- No errors in playbook output
- Services remain healthy after re-run

### Phase 5: Test Rollback Procedure

**Objective**: Validate rollback capability

**Steps**:
1. Locate backup compose directory (timestamped)
2. Stop current stack: `docker compose down`
3. Restore backup: Move backup to `/opt/immich-app`
4. Update variables to v1.121.0
5. Redeploy with Ansible
6. Verify v1 is running

**Verification**:
- v1 can be successfully restored
- Rollback procedure is documented

## Track B: Manual Break-Glass Procedures

**When to Use**: Ansible fails, emergency maintenance, troubleshooting

### Manual Upgrade Steps (from PVE host)

1. **Backup existing configuration**:
   ```bash
   pct exec 101 -- bash -c "cp -r /opt/immich-app /opt/immich-app.backup-$(date +%Y%m%d-%H%M%S)"
   ```

2. **Stop current Immich stack**:
   ```bash
   pct exec 101 -- bash -c "cd /opt/immich-app && docker compose down"
   ```

3. **Verify NAS mount inside LXC**:
   ```bash
   pct exec 101 -- bash -c "test -d /mnt/immich && echo 'Mount OK' || echo 'Mount MISSING'"
   pct exec 101 -- bash -c "touch /mnt/immich/test.txt && rm /mnt/immich/test.txt && echo 'Writable' || echo 'Not writable'"
   ```

4. **Create required directories**:
   ```bash
   pct exec 101 -- bash -c "mkdir -p /opt/immich-data/postgres"
   pct exec 101 -- bash -c "mkdir -p /mnt/immich/library-v2"
   ```

5. **Download v2 compose files**:
   ```bash
   pct exec 101 -- bash -c "cd /opt/immich-app && wget -O docker-compose.yml https://github.com/immich-app/immich/releases/download/v2.4.0/docker-compose.yml"
   pct exec 101 -- bash -c "cd /opt/immich-app && wget -O example.env https://github.com/immich-app/immich/releases/download/v2.4.0/example.env"
   ```

6. **Edit .env file with custom values**:
   ```bash
   pct exec 101 -- bash -c "cd /opt/immich-app && cat > .env << 'EOF'
   UPLOAD_LOCATION=/mnt/immich/library-v2
   DB_DATA_LOCATION=/opt/immich-data/postgres
   IMMICH_VERSION=v2.4.0
   TZ=Etc/UTC
   DB_PASSWORD=<your-password-here>
   DB_USERNAME=postgres
   DB_DATABASE_NAME=immich
   EOF"
   ```

7. **Update docker-compose.yml volume paths**:
   - Edit to use `${UPLOAD_LOCATION}:/data`
   - Edit to use `${DB_DATA_LOCATION}:/var/lib/postgresql/data`

8. **Start v2 stack**:
   ```bash
   pct exec 101 -- bash -c "cd /opt/immich-app && docker compose pull"
   pct exec 101 -- bash -c "cd /opt/immich-app && docker compose up -d"
   ```

9. **Verify deployment**:
   ```bash
   pct exec 101 -- bash -c "cd /opt/immich-app && docker compose ps"
   pct exec 101 -- bash -c "curl -f http://localhost:2283/api/server/ping || echo 'API not ready'"
   ```

10. **STOP POINT**: Before proceeding, confirm:
    - [ ] All 4 containers show "Up" and "healthy" status
    - [ ] API ping returns successful response
    - [ ] Web UI loads at http://192.168.1.213:2283
    - [ ] Library directory exists and is writable

### Manual Rollback Steps

1. **Stop v2 stack**:
   ```bash
   pct exec 101 -- bash -c "cd /opt/immich-app && docker compose down"
   ```

2. **Restore backup**:
   ```bash
   pct exec 101 -- bash -c "rm -rf /opt/immich-app && cp -r /opt/immich-app.backup-YYYYMMDD-HHMMSS /opt/immich-app"
   ```

3. **Start v1 stack**:
   ```bash
   pct exec 101 -- bash -c "cd /opt/immich-app && docker compose up -d"
   ```

4. **Verify v1 is running**:
   ```bash
   pct exec 101 -- bash -c "docker compose ps"
   ```

## Dependencies

### Ansible Dependencies
- `community.docker` collection installed
- Target LXC has Python 3 installed
- SSH access configured for root@192.168.1.213

### External Dependencies
- Synology NAS operational and reachable
- NFS export accessible from Proxmox host
- Docker Hub and GitHub Container Registry reachable

### Repository Structure
```
ansible/
├── group_vars/services/vars.yml         # Update version variable
├── roles/immich/
│   ├── defaults/main.yml                 # Update defaults
│   ├── tasks/
│   │   ├── main.yml                      # Update tasks
│   │   └── preflight.yml                 # New: preflight checks
│   ├── templates/
│   │   ├── docker-compose.yml.j2         # Replace with v2 structure
│   │   └── .env.j2                       # Update with v2 env vars
│   └── handlers/main.yml                 # Ensure v2 compat
```

## Risk Management

### Critical Risks
1. **NAS mount unavailable**: Preflight checks will detect and fail fast
2. **Configuration mismatch**: Templates sourced from official upstream
3. **Data loss**: Automated backup before upgrade
4. **Service downtime**: Estimated 5-10 minutes during upgrade

### Rollback Triggers
- API health check fails after 5 minutes
- Containers fail to start
- Database migration errors (should not occur with fresh deploy)
- Storage mount issues

### Validation Gates
Each phase has verification steps that must pass before proceeding to next phase.

## Timeline Estimate

| Phase | Estimated Time | Critical Path |
|-------|---------------|---------------|
| Phase 1: Update variables | 15 minutes | No |
| Phase 2: Update templates | 30 minutes | Yes |
| Phase 3: Update tasks | 45 minutes | Yes |
| Phase 4: Test deployment | 30 minutes | Yes |
| Phase 5: Test rollback | 15 minutes | No |
| **Total** | **2.25 hours** | |

**Note**: Manual procedures are documented for emergency use but not included in timeline.

## Success Criteria Checklist

After implementation, verify all spec success criteria are met:

- [ ] SC-001: Web interface accessible at http://192.168.1.213:2283 within 5 minutes
- [ ] SC-002: API health endpoint returns successful response
- [ ] SC-003: Photo uploads stored on NAS and survive container restart
- [ ] SC-004: Re-running playbook completes in under 2 minutes with no changes
- [ ] SC-005: All four containers show healthy status within 3 minutes
- [ ] SC-006: Upgrade via single playbook command without manual steps
- [ ] SC-007: Mobile app successfully connects
- [ ] SC-008: System functions after NAS remount/LXC reboot
- [ ] SC-009: Backup procedures work with v2
- [ ] SC-010: Documentation enables validation in under 10 minutes

## Next Steps

After plan approval:
1. Create detailed tasks.md with checkboxes for execution tracking
2. Begin Phase 1 implementation
3. Test each phase thoroughly before proceeding
4. Update documentation after successful deployment
