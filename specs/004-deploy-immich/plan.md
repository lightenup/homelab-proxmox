# Plan: Deploy Immich on the Immich LXC

## Phase 1: Preparation and Role Structure

1.  **Define Variables**:
    *   Set up `ansible/group_vars/services.yml` (or host-specific vars) with Immich configuration:
        *   Version (e.g., `release` or specific tag).
        *   Ports (default 2283).
        *   Data paths (root: `/mnt/immich`).
        *   Database credentials (using Ansible Vault or local vars).
2.  **Create Ansible Role**:
    *   Create `ansible/roles/immich` structure.
    *   Define `tasks/main.yml`, `templates/docker-compose.yml.j2`, `templates/.env.j2`.

## Phase 2: Implementation

3.  **Install Docker**:
    *   Add tasks to install Docker Engine and Docker Compose plugin on the LXC.
    *   Ensure `docker` service is enabled and running.
4.  **Configure Storage**:
    *   Add tasks to create necessary subdirectories under `/mnt/immich` (e.g., `postgres`, `redis`, `library`, `uploads`, `profile`, `thumbs`, `video`).
    *   Set appropriate ownership/permissions (likely `root` or a dedicated user if mapped correctly, but typically Docker runs as root inside LXC unless rootless).
5.  **Deploy Application**:
    *   Template `docker-compose.yml` and `.env` to `/opt/immich`.
    *   Use `community.docker.docker_compose_v2` module (or shell command if module unavailable) to bring up the stack.
    *   Ensure restart policy is `unless-stopped` or `always`.

## Phase 3: Validation and Maintenance

6.  **Health Checks**:
    *   Add a task to wait for port 2283 to be listening.
    *   Add a task to curl the health endpoint (if available) or login page.
7.  **Update Procedure**:
    *   Verify that changing the version variable and re-running the playbook triggers a pull and recreate.
8.  **Documentation**:
    *   Update `README.md` or `docs/` with management instructions.

## Stop Points

*   **SP-001**: Confirm Docker installation and version.
*   **SP-002**: Confirm `docker-compose.yml` generation and content (secrets check).
*   **SP-003**: Confirm successful startup and reachability.
