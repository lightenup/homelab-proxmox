# Tasks: Local DNS & Naming

## Phase 1: Setup

- [x] T001 Create `ansible/roles/mdns_base` directory structure (tasks, handlers, defaults).

## Phase 2: Foundational

- [x] T002 Implement `ansible/roles/mdns_base/tasks/main.yml` to install `avahi-daemon` and `libnss-mdns`.
- [x] T003 Add task to `ansible/roles/mdns_base/tasks/main.yml` to ensure `/etc/hosts` contains `127.0.1.1 <hostname>` (Debian requirement for reliable resolution).
- [x] T004 Add task to `ansible/roles/mdns_base/tasks/main.yml` to enable and start `avahi-daemon` service.
- [x] T005 Create `ansible/roles/mdns_base/handlers/main.yml` to restart avahi-daemon when configuration changes.

## Phase 3: User Story 1 (Admin Access via Hostname)

- [x] T006 [US1] Create `ansible/playbooks/naming.yml` targeting `proxmox` and `services` groups.
- [x] T007 [US1] Run `ansible/playbooks/naming.yml` against all hosts (`pve`, `proxy`, `immich`, `adguard`, `homeassistant`).
- [x] T008 [US1] Verify `ping pve.local` resolves correctly from the admin laptop.
- [x] T009 [US1] Verify `ping proxy.local` resolves correctly from the admin laptop.

## Phase 4: User Story 2 (Inter-Service Resolution)

- [x] T010 [US2] Verify `ping immich.local` works from inside the `homeassistant` LXC.
- [x] T011 [US2] Verify `getent hosts adguard.local` works from inside the `proxy` LXC.

## Phase 5: User Story 3 (Automated Configuration)

- [x] T012 [US3] Re-run `ansible/playbooks/naming.yml` to verify idempotency (changed=0).

## Phase 6: Documentation & Polish

- [x] T013 Create `docs/naming-and-mdns.md` documenting `.local` usage, Android limitations, and future `home.arpa` plans.
