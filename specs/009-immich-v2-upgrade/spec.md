# Feature Specification: Immich v2.4.0 Upgrade

**Feature Branch**: `009-immich-v2-upgrade`
**Created**: December 19, 2024
**Status**: Draft
**Input**: Upgrade Immich from v1.121.0 to v2.4.0 with NAS-backed storage, fresh v2 compose layout, and Ansible automation

## Overview

### Goal

Upgrade Immich photo management service from v1.121.0 to v2.4.0, implementing the upstream-recommended v2 compose layout with NAS-backed storage. Ensure all configuration and data are stored on the Synology NAS mount for easy rebuilds and disaster recovery. Automate the entire upgrade process through Ansible for repeatability.

### Current State

- **LXC Container**: VMID 101, hostname `immich`, IP 192.168.1.213, Debian bookworm
- **Immich Version**: v1.121.0 (pinned in `ansible/group_vars/services/vars.yml`)
- **Storage**:
  - NAS export: `192.168.1.109:/volume1/homelab_immich`
  - Mounted on Proxmox host: `/mnt/nas/homelab_immich`
  - Bind-mounted into LXC: `/mnt/immich`
- **Docker Compose Location**: `/opt/immich` inside LXC
- **Data Status**: No meaningful user data exists (mobile app version mismatch prevented adoption)
- **Services**: immich-server, immich-machine-learning, redis, postgres using older v1 compose structure

### Scope

**In Scope**:
- Upgrade to Immich v2.4.0 using official v2 docker-compose structure
- Migrate to new v2 environment variable patterns (UPLOAD_LOCATION, etc.)
- Store all user data (library) on NAS mount at `/mnt/immich/library-v2`
- Update Ansible role and templates for v2 compatibility
- Remove deprecated v1 compose services/configurations
- Implement idempotent Ansible automation
- Document upgrade and rollback procedures
- Preserve existing backup/restore functionality

**Out of Scope**:
- Migration of v1 user data (none exists to migrate)
- Changes to LXC configuration or network settings
- External exposure/reverse proxy modifications
- Mobile app configuration changes
- Authentication/user management changes beyond default Immich v2 behavior

### Non-Goals

- Supporting in-place v1 to v2 database migrations (treating as fresh deploy)
- Maintaining backward compatibility with v1 configuration
- Preserving old v1 compose directory structure

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Infrastructure Operator Upgrades Immich via Ansible (Priority: P1)

As an infrastructure operator, I need to upgrade Immich to v2.4.0 by running a single Ansible playbook command, so that the service is updated reliably without manual intervention and can be repeated across environments.

**Why this priority**: This is the primary delivery mechanism and core requirement. Without automated upgrade capability, the feature fails its main objective.

**Independent Test**: Run `ansible-playbook playbooks/site.yml` against the Immich LXC, verify Immich v2.4.0 containers start successfully and API responds.

**Acceptance Scenarios**:

1. **Given** current Immich v1.121.0 is running, **When** operator runs `ansible-playbook playbooks/site.yml`, **Then** Immich upgrades to v2.4.0 with v2 compose structure, all containers are healthy, and API endpoint `/api/server/ping` returns success
2. **Given** Immich v2.4.0 is already running, **When** operator re-runs the same Ansible playbook, **Then** no changes are made (idempotent), containers remain healthy
3. **Given** upgrade playbook completes, **When** operator checks docker containers, **Then** container names match expected v2 naming (immich_server, immich_postgres, immich_redis, immich_machine_learning)

---

### User Story 2 - System Validates NAS Storage Configuration (Priority: P1)

As an infrastructure operator, I need the upgrade process to verify that the NAS mount is properly configured and writable, so that Immich can store photos on network storage and survive LXC rebuilds.

**Why this priority**: Storage configuration is critical for data persistence and disaster recovery strategy. Incorrect storage setup causes data loss.

**Independent Test**: Run Ansible playbook, check that `/mnt/immich/library-v2` is created inside LXC and writable by Docker containers.

**Acceptance Scenarios**:

1. **Given** NAS mount exists at `/mnt/immich` inside LXC, **When** Ansible configures Immich, **Then** UPLOAD_LOCATION environment variable points to `/mnt/immich/library-v2` and directory is created with correct permissions
2. **Given** Immich containers start, **When** user uploads a test photo via web UI, **Then** file appears in `/mnt/immich/library-v2` on NAS mount
3. **Given** operator verifies storage, **When** checking from Proxmox host at `/mnt/nas/homelab_immich`, **Then** library-v2 directory and contents are visible

---

### User Story 3 - Operator Performs Break-Glass Manual Upgrade (Priority: P2)

As an infrastructure operator, I need documented manual upgrade steps executable via `pct exec` from Proxmox host, so that I can intervene if Ansible fails or perform emergency maintenance.

**Why this priority**: Break-glass procedures provide safety net for automation failures and critical incident response.

**Independent Test**: Follow manual upgrade steps from plan document using only `pct exec` commands, verify successful upgrade without Ansible.

**Acceptance Scenarios**:

1. **Given** Ansible playbook fails mid-upgrade, **When** operator follows manual procedure to stop old stack and deploy new compose files, **Then** Immich v2 starts successfully
2. **Given** operator executes manual backup before upgrade, **When** checking backup location, **Then** old compose directory exists at `/opt/immich-app.backup-YYYYMMDD` with timestamped name
3. **Given** manual upgrade completes, **When** running `docker compose ps` inside LXC, **Then** all v2 services show "healthy" status

---

### User Story 4 - Validate Service Health Post-Upgrade (Priority: P1)

As an infrastructure operator or end user, I need to verify that upgraded Immich v2.4.0 is fully functional, so that I can confidently use the service for photo management.

**Why this priority**: Health validation ensures the upgrade achieved its intended outcome and service is production-ready.

**Independent Test**: Execute health check commands and access web UI, verify all functionality works as expected.

**Acceptance Scenarios**:

1. **Given** Immich v2.4.0 is running, **When** operator runs `curl http://192.168.1.213:2283/api/server/ping`, **Then** API returns successful response
2. **Given** web UI is accessible, **When** user navigates to `http://192.168.1.213:2283`, **Then** Immich v2 login/setup wizard displays
3. **Given** operator checks container health, **When** running `docker compose ps` inside LXC, **Then** all containers show "Up" status with health checks passing
4. **Given** mobile app connects, **When** user configures app with server URL, **Then** app successfully authenticates and can browse/upload photos

---

### User Story 5 - Rollback to Previous Version (Priority: P3)

As an infrastructure operator, I need documented rollback procedures to restore Immich v1.121.0, so that I can recover if v2 upgrade causes critical issues.

**Why this priority**: Safety mechanism for production environments, though less critical given no existing user data.

**Independent Test**: Perform upgrade, then execute rollback procedure, verify v1.121.0 is restored and functional.

**Acceptance Scenarios**:

1. **Given** v2 upgrade has issues, **When** operator restores backup compose directory and redeploys, **Then** v1.121.0 stack is running again
2. **Given** rollback is needed, **When** operator checks documentation, **Then** step-by-step rollback procedure is clearly documented
3. **Given** rollback completes, **When** checking service, **Then** v1.121.0 is accessible and containers are healthy

---

### Edge Cases

- **What happens when NAS mount is unavailable during upgrade?** Ansible should detect missing mount and fail gracefully with clear error message, preventing service degradation
- **What happens when Docker daemon is not running?** Pre-flight checks should verify Docker is active before attempting compose operations
- **What happens if Postgres container fails to start on v2?** Health checks should detect failure, operator should have manual recovery steps in documentation
- **What happens when re-running playbook during active upgrade?** Ansible tasks should be idempotent and safe to re-run; compose commands should handle in-progress operations gracefully
- **What happens if backup compose directory already exists?** Backup operation should append timestamp to avoid conflicts
- **What happens when UPLOAD_LOCATION path doesn't exist?** Ansible should create the directory with appropriate permissions before starting containers

## Requirements *(mandatory)*

### Functional Requirements

**Version and Deployment**:
- **FR-001**: Ansible MUST upgrade Immich from v1.121.0 to v2.4.0
- **FR-002**: System MUST use official Immich v2 docker-compose structure from upstream documentation
- **FR-003**: Ansible role MUST pin Immich version to v2.4.0 in configuration variables
- **FR-004**: Compose file MUST use official v2 image tags: `ghcr.io/immich-app/immich-server:${IMMICH_VERSION}` and `ghcr.io/immich-app/immich-machine-learning:${IMMICH_VERSION}`

**Storage and Data Persistence**:
- **FR-005**: System MUST store Immich photo library at `/mnt/immich/library-v2` on NAS-backed mount
- **FR-006**: Environment variable UPLOAD_LOCATION MUST be set to `/mnt/immich/library-v2`
- **FR-007**: Docker compose volume mapping MUST mount `${UPLOAD_LOCATION}:/data` for immich-server container
- **FR-008**: Postgres database files MUST be stored on LXC local disk at `/opt/immich-data/postgres` for performance
- **FR-009**: Redis data MUST persist appropriately for session management
- **FR-010**: Machine learning model cache MUST use named Docker volume `model-cache`

**Configuration Management**:
- **FR-011**: Ansible role MUST template docker-compose.yml matching v2 structure
- **FR-012**: Ansible role MUST template .env file with v2-compatible environment variables
- **FR-013**: Configuration MUST set timezone to UTC or user-specified value
- **FR-014**: Database credentials MUST be templated from Ansible vault or encrypted variables
- **FR-015**: Compose file MUST expose Immich on port 2283 mapped to container port 2283

**Service Dependencies and Health**:
- **FR-016**: immich-server container MUST depend on redis and database services
- **FR-017**: All services MUST have restart policy set to "always"
- **FR-018**: Health checks MUST be enabled for all containers
- **FR-019**: Ansible MUST wait for port 2283 to be reachable before completing deployment

**Migration and Compatibility**:
- **FR-020**: Deployment MUST remove deprecated v1 services (microservices container if present)
- **FR-021**: Deployment MUST update Redis image from redis:6.2-alpine to official valkey/redis v9 image
- **FR-022**: Deployment MUST update Postgres image to official Immich postgres:14-vectorchord image
- **FR-023**: System MUST NOT migrate v1 data (treating as fresh v2 installation)

**Automation and Idempotency**:
- **FR-024**: Running Ansible playbook multiple times MUST be idempotent (no unintended changes on repeat runs)
- **FR-025**: Ansible MUST create required directories before starting services
- **FR-026**: Ansible MUST backup existing compose directory before upgrade with timestamp
- **FR-027**: Ansible handlers MUST restart Immich only when configuration changes

**Verification and Validation**:
- **FR-028**: System MUST expose API endpoint `/api/server/ping` that returns successful response when healthy
- **FR-029**: Deployment MUST verify all containers reach "running" state
- **FR-030**: Documentation MUST include verification steps for operators to validate upgrade success

### Assumptions

- Synology NAS NFS export is already configured and mounted on Proxmox host
- LXC container has bind mount configured for `/mnt/immich` pointing to Proxmox host's `/mnt/nas/homelab_immich`
- Docker and docker-compose-plugin are already installed in LXC via existing roles
- No user data exists in current v1 installation that needs preservation
- Network connectivity between LXC and NAS is reliable
- Operator has Ansible vault password or access to encrypted secrets
- Postgres performance is acceptable on LXC local disk (decision: local SSD is faster than NAS for database workloads)
- Backup/restore functionality from existing immich_backup role will continue to function with v2

### Key Entities

- **Immich Installation**: Complete deployment of Immich v2.4.0, consists of compose file, environment configuration, and running containers
- **Docker Compose Stack**: Collection of four services (immich-server, immich-machine-learning, redis, database) defined in docker-compose.yml
- **Photo Library**: User-uploaded photos and videos stored at UPLOAD_LOCATION on NAS mount, organized by Immich's internal structure
- **Persistent Storage**: Combination of NAS-backed library storage and LXC-local database storage optimized for performance and durability
- **Configuration Templates**: Jinja2 templates in Ansible role that generate docker-compose.yml and .env files from variables

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Immich web interface is accessible at http://192.168.1.213:2283 and displays v2 UI within 5 minutes of Ansible playbook completion
- **SC-002**: API health endpoint returns successful response when queried, indicating all backend services are operational
- **SC-003**: Photo uploads are successfully stored on NAS mount and remain accessible after LXC container restart
- **SC-004**: Re-running Ansible playbook completes in under 2 minutes with no service restarts when configuration is unchanged
- **SC-005**: All four container services (server, machine-learning, redis, database) show healthy status within 3 minutes of stack startup
- **SC-006**: Operators can complete upgrade process by executing single playbook command without manual intervention
- **SC-007**: Mobile app successfully connects to upgraded server and can browse/upload photos
- **SC-008**: System continues to function normally after NAS remount or LXC reboot, demonstrating proper persistence
- **SC-009**: Backup procedures complete successfully against v2 installation, maintaining disaster recovery capability
- **SC-010**: Documentation enables operators to validate upgrade success through defined verification steps in under 10 minutes

## Risks and Mitigations

### Risk: Data Loss During Upgrade

**Likelihood**: Low
**Impact**: High
**Mitigation**:
- Perform backup of existing compose directory before upgrade (automated in Ansible)
- No user data exists currently, so data loss risk is minimal
- Document rollback procedure in case v2 is incompatible
- Store critical config on version control

### Risk: NAS Mount Unavailable

**Likelihood**: Low
**Impact**: High
**Mitigation**:
- Add Ansible pre-flight check to verify `/mnt/immich` mount exists and is writable
- Document manual mount verification steps
- Implement health check that fails fast if UPLOAD_LOCATION is not writable

### Risk: Configuration Mismatch with v2

**Likelihood**: Medium
**Impact**: Medium
**Mitigation**:
- Reference official upstream v2 docker-compose.yml and .env examples
- Test deployment in isolated environment before production
- Implement comprehensive health checks post-deployment
- Document expected container names and service structure

### Risk: Postgres Performance on LXC Disk

**Likelihood**: Low
**Impact**: Medium
**Mitigation**:
- Decision: Use LXC local disk for Postgres (SSDs are faster than NAS for database workloads)
- Monitor database performance after upgrade
- Document migration to NAS if performance is acceptable and persistence is preferred
- Ensure database is included in backup procedures

### Risk: Breaking Changes in v2 API

**Likelihood**: Low
**Impact**: Medium
**Mitigation**:
- Mobile app compatibility verified through testing
- API endpoint `/api/server/ping` provides health validation
- Document any mobile app version requirements
- v2 is stable release with backward compatibility considerations

## Upstream Documentation References

The following official Immich documentation was consulted for v2 specifications:

1. **Docker Compose Installation**: https://docs.immich.app/install/docker-compose
   - Official v2 docker-compose.yml structure
   - .env file configuration examples
   - Service definitions and volume mappings

2. **Environment Variables**: https://docs.immich.app/install/environment-variables
   - UPLOAD_LOCATION: Host path for uploads
   - IMMICH_VERSION: Image tag specification
   - DB_DATA_LOCATION: Database storage path
   - Database and Redis connection settings
   - TZ (timezone) configuration

3. **v2.0.0 Release Notes**: https://github.com/immich-app/immich/releases/tag/v2.0.0
   - Stable release announcement
   - Migration guidance from v1 to v2
   - Breaking changes documentation
   - New features in v2

4. **Official Docker Compose Example**: https://github.com/immich-app/immich/blob/main/docker/docker-compose.yml
   - Reference implementation of v2 compose structure
   - Container naming conventions
   - Health check configurations
   - Volume and network definitions

### Key v2 Changes from v1

Based on upstream documentation and compose file comparison:

1. **Simplified Architecture**: v2 eliminates the separate microservices container; immich-server now handles both API and worker tasks
2. **Updated Images**:
   - Postgres: `ghcr.io/immich-app/postgres:14-vectorchord0.4.3` (was `tensorchord/pgvecto-rs:pg14-v0.2.0`)
   - Redis: `docker.io/valkey/valkey:9` (was `redis:6.2-alpine`)
3. **Volume Mapping Change**: v1 used `/usr/src/app/upload`, v2 uses `/data` mount point with UPLOAD_LOCATION env var
4. **Environment Variables**: v2 introduces clearer UPLOAD_LOCATION and DB_DATA_LOCATION for compose-level configuration
5. **Version Pinning**: Upstream recommends pinning to specific tags like `v2.4.0` rather than using `release` tag

## Technical Decisions

### Decision: Fresh v2 Deploy vs In-Place Migration

**Decision**: Treat upgrade as fresh v2 deployment, not in-place migration
**Rationale**:
- No user data exists in current v1 installation
- Fresh deploy is simpler and lower risk
- Avoids potential database migration issues
- Allows clean implementation of v2 best practices

### Decision: Postgres on LXC Local Disk

**Decision**: Store Postgres data on LXC local disk at `/opt/immich-data/postgres`
**Rationale**:
- Database performance is significantly better on local SSD vs NFS
- Postgres recommends against network storage for data files
- Database is included in backup procedures for disaster recovery
- LXC snapshots can capture database state
- Photo library (the large data) is on NAS where it matters most

### Decision: New Library Path for v2

**Decision**: Create new library path `/mnt/immich/library-v2`
**Rationale**:
- Clear distinction from any v1 artifacts
- Allows keeping v1 data for rollback if needed
- Explicit versioning in path aids troubleshooting
- Follows convention of major version changes

### Decision: Pin to v2.4.0 Specifically

**Decision**: Use `IMMICH_VERSION=v2.4.0` not `v2` or `release`
**Rationale**:
- Explicit version pinning prevents unexpected updates
- Enables controlled upgrade testing in future
- Matches upstream best practice recommendations
- Provides clarity in documentation and troubleshooting

## Out of Scope (Explicit Non-Requirements)

- Migration of existing v1 user data (none exists)
- Changes to LXC hardware allocation or network configuration
- Implementation of HTTPS/TLS (handled at reverse proxy layer)
- External DNS configuration
- Mobile app updates or configuration
- Custom Immich feature configuration beyond defaults
- Performance tuning beyond standard deployment
- Multi-instance or high-availability setup
- Integration with external authentication providers
