# Tasks: Internal Reverse Proxy Baseline

## Phase 1: Setup & Prerequisites

- [x] T001 Create `ansible/roles/reverse_proxy` directory structure (tasks, templates, handlers, defaults).
- [x] T002 Define default variables in `ansible/roles/reverse_proxy/defaults/main.yml` (e.g., `caddy_conf_dir: /etc/caddy/conf.d`).

## Phase 2: Foundational (Caddy Base)

- [x] T003 Implement Caddy installation in `ansible/roles/reverse_proxy/tasks/main.yml` (add official Apt key & repo, install `caddy` package).
- [x] T004 Create `ansible/roles/reverse_proxy/templates/Caddyfile.j2` (Main config: `auto_https off`, import `conf.d/*.caddy`, log to stdout).
- [x] T005 Implement tasks to create configuration directory `/etc/caddy/conf.d` and deploy main `Caddyfile`.
- [x] T006 Implement service handler in `ansible/roles/reverse_proxy/handlers/main.yml` (restart/reload caddy).
- [x] T007 Update `ansible/playbooks/services.yml` to apply `reverse_proxy` role to `reverse_proxy` host.

## Phase 3: User Story 1 - Basic Proxy Setup

- [x] T008 [US1] Create `ansible/roles/reverse_proxy/templates/immich.caddy.j2` (Reverse proxy rule: `:80` -> `immich_ip:immich_port`, ensuring `X-Forwarded-Proto` is set).
- [x] T009 [US1] Define `immich_ip` and `immich_port` in `ansible/group_vars/services/vars.yml` (if not already present/accessible).
- [x] T010 [US1] Implement task to deploy `immich.caddy` to `/etc/caddy/conf.d/immich.caddy`.
- [x] T011 [US1] Run playbook to deploy Caddy and Immich configuration.
- [x] T012 [US1] Verify HTTP access: `curl -I http://192.168.1.211/` returns 200/302 from Immich.

## Phase 4: User Story 2 - Persistence & Idempotency

- [x] T013 [US2] Verify Idempotency: Re-run playbook and confirm 0 changes.
- [x] T014 [US2] Verify Persistence: Reboot `proxy` LXC and confirm service auto-starts and is reachable.

## Phase 5: User Story 3 - Documentation & Maintenance

- [x] T015 [US3] Create `docs/reverse-proxy.md` documenting the modular structure, update procedure, and how to add new services.

## Dependencies

- US1 depends on Phase 1 & 2.
- US2 depends on US1.
- US3 depends on US1.
