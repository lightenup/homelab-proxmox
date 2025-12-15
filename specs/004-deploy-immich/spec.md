# Feature Specification: Deploy Immich on the Immich LXC

**Feature Branch**: `004-deploy-immich`
**Created**: 2025-12-15
**Status**: Draft
**Input**: User description: "Deploy Immich on the Immich LXC"

## Clarifications

### Session 2025-12-15
- Q: Should we pin the Immich version or track `release`? → A: **Pin to specific version** (e.g., `v1.121.0`) to ensure stability and controlled updates.
- Q: How should secrets (DB password) be handled? → A: **Ansible Vault** - Encrypt secrets in the repo for better security and portability.
- Q: How should Docker be installed? → A: **Use `geerlingguy.docker` role**, pinned to a specific version in `requirements.yml` for repeatability.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Initial Deployment (Priority: P1)

As a homelab administrator, I want to deploy the Immich stack to the dedicated LXC container using Ansible so that the service is up and running with minimal manual intervention.

**Why this priority**: This is the core functionality of the feature.

**Independent Test**: Run the Ansible playbook against a fresh or existing LXC and verify containers are running.

**Acceptance Scenarios**:

1. **Given** the `immich` LXC is running and accessible via SSH, **When** I run the Ansible playbook, **Then** Docker and Docker Compose are installed.
2. **Given** the playbook execution completes, **When** I check the process list on the LXC, **Then** the Immich containers (server, microservices, machine-learning, redis, postgres) are running.
3. **Given** the stack is running, **When** I access `http://192.168.1.213:2283`, **Then** the Immich Welcome/Login page loads.

---

### User Story 2 - Data Persistence (Priority: P1)

As a user, I want my photos and database to be stored on the mounted NAS storage so that my data survives container recreation and LXC reboots.

**Why this priority**: Critical for data safety.

**Independent Test**: Create a dummy file in the data directory, restart the stack/LXC, and verify the file remains.

**Acceptance Scenarios**:

1. **Given** the Immich stack is running, **When** I create a test file in `/mnt/immich/library/test.txt`, **Then** the file is visible on the Proxmox host at `/mnt/nas/homelab_immich/library/test.txt`.
2. **Given** I have created a test file in the data volume, **When** I run `docker compose down` and then `docker compose up`, **Then** the test file still exists.
3. **Given** the stack is running, **When** I reboot the `immich` LXC, **Then** the stack starts automatically and the data is still accessible.

---

### User Story 3 - Idempotency and Updates (Priority: P2)

As an administrator, I want to be able to re-run the deployment playbook without breaking the running service, and use it to update the stack when new versions are released.

**Why this priority**: Ensures maintainability and ease of updates.

**Independent Test**: Run the playbook twice; update the version variable and run again.

**Acceptance Scenarios**:

1. **Given** a running Immich deployment, **When** I re-run the Ansible playbook, **Then** no containers are recreated unless configuration changed, and the service remains available.
2. **Given** a new version of Immich is available, **When** I update the version variable and run the playbook, **Then** the new images are pulled and the containers are recreated with the new version.

### Edge Cases

- **Network Failure**: If the NAS mount is unavailable, the service should fail to start gracefully or the playbook should fail fast (handled by previous spec's mount configuration, but app should probably wait for mount).
- **Port Conflict**: If port 2283 is in use (unlikely in dedicated LXC), the deployment might fail.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST run Immich using Docker Compose on the `immich` LXC.
- **FR-001a**: Docker Engine MUST be installed using the `geerlingguy.docker` Ansible role, pinned to a specific version in `requirements.yml`.
- **FR-002**: All persistent data (uploads, library, database, cache) MUST be stored under `/mnt/immich`.
- **FR-003**: Deployment MUST be idempotent (re-running playbook does not break system).
- **FR-004**: The repository MUST NOT contain sensitive values (passwords, secrets); these MUST be encrypted using Ansible Vault.
- **FR-005**: The Immich service MUST automatically start after the LXC reboots.
- **FR-006**: The system MUST support a controlled update procedure via Ansible by changing a pinned version variable (not using `latest` tag).
- **FR-007**: The Ansible playbook MUST include a "smoke test" to validate the service is reachable via HTTP.

### Key Entities *(include if feature involves data)*

- **Immich Stack**: The set of Docker containers comprising the application (Server, Microservices, Machine Learning, Redis, Postgres).
- **Data Volume**: The directory structure under `/mnt/immich` mapping to the NAS.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Immich UI is reachable at `http://192.168.1.213:2283` within 2 minutes of playbook completion.
- **SC-002**: Data written to the application persists across a full LXC reboot.
- **SC-003**: Re-running the playbook on a healthy system completes with 0 changed tasks (except potentially the smoke test).
