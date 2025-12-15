# Tasks - Deploy Immich on the Immich LXC

## Phase 1: Setup & Prerequisites

- [x] T001 Create `ansible/roles/immich` directory structure (tasks, templates, defaults, handlers).
- [x] T002 Add `geerlingguy.docker` to `ansible/requirements.yml` (pinned version).
- [x] T003 Install Ansible Galaxy roles (`ansible-galaxy install -r ansible/requirements.yml`).
- [x] T004 Create `ansible/group_vars/services/secrets.yml` (encrypted with Ansible Vault) for DB password.
- [x] T005 Define default variables in `ansible/roles/immich/defaults/main.yml` (version, port, paths).

## Phase 2: Foundational (Docker & Storage)

- [x] T006 [US1] Configure `geerlingguy.docker` variables in `ansible/group_vars/services.yml` (users, compose plugin).
- [x] T007 [US1] Add `geerlingguy.docker` and `immich` roles to `ansible/playbooks/services.yml`.
- [x] T008 [US2] Implement storage directory creation in `ansible/roles/immich/tasks/main.yml` (ensure `/mnt/immich` subdirs exist).

## Phase 3: User Story 1 - Initial Deployment

- [x] T009 [US1] Create `docker-compose.yml.j2` template in `ansible/roles/immich/templates/` (based on official example).
- [x] T010 [US1] Create `.env.j2` template in `ansible/roles/immich/templates/` (mapping vars to env).
- [x] T011 [US1] Implement tasks to deploy templates to `/opt/immich` in `ansible/roles/immich/tasks/main.yml`.
- [x] T012 [US1] Implement task to run `docker compose up -d` using `community.docker.docker_compose_v2` (or shell).
- [x] T013 [US1] Add smoke test task (wait for port 2283) in `ansible/roles/immich/tasks/main.yml`.
- [x] T014 [US1] Run playbook and verify Immich is running and reachable.

## Phase 4: User Story 2 - Data Persistence

- [x] T015 [US2] Verify data persistence manually (create file in `/mnt/immich`, restart stack, check file).
- [x] T016 [US2] Verify persistence across LXC reboot (reboot LXC, check service auto-start and data).

## Phase 5: User Story 3 - Idempotency and Updates

- [x] T017 [US3] Verify idempotency (re-run playbook, expect 0 changes).
- [x] T018 [US3] Document update procedure in `docs/immich-maintenance.md` (change version var, re-run playbook).

## Dependencies

- US1 depends on Phase 1 & 2.
- US2 depends on US1.
- US3 depends on US1.

## Implementation Strategy

1.  **Setup**: Get the role structure and Docker dependency ready.
2.  **MVP (US1)**: Get the stack running with hardcoded/default values first, then parameterize.
3.  **Persistence (US2)**: Verify the mount points are actually being used by the containers.
4.  **Refinement (US3)**: Ensure the playbook is clean and idempotent.
