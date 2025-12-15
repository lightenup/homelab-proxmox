# Tasks: Ansible Bootstrap for Core Service LXCs

**Feature**: Ansible Bootstrap for Core Service LXCs
**Status**: Draft
**Spec**: [specs/002-core-services-lxc/spec.md](specs/002-core-services-lxc/spec.md)

## Phase 1: Setup (Inventory Generation)
*Implement dynamic inventory generation from Terraform.*

- [x] T001 [US1] Create `scripts/update_ansible_inventory.sh` to parse Terraform output, strip CIDR suffixes, and generate `ansible/inventories/generated/hosts.yml`
- [x] T002 [US1] Update `.gitignore` to exclude `ansible/inventories/generated/hosts.yml` and ensure directory exists
- [x] T003 [US1] Verify script execution: Check generated YAML for correct structure and plain IPs (STOP POINT: Review generated inventory)
- [x] T004 [US1] Verify/Update `ansible/ansible.cfg` to ensure it loads the generated inventory (or document usage of `-i`)

## Phase 2: Bootstrap (Root Access)
*Provision the dedicated ansible user.*

- [x] T005 [US2] Create `ansible/playbooks/bootstrap.yml` to install Python 3 (raw), create `ansible` user, and configure sudo/SSH (copying authorized_keys from root)
- [x] T006 [US2] Run `ansible-playbook playbooks/bootstrap.yml -u root` and verify success
- [x] T007 [US2] Verify `ansible` user access: `ansible -m ping all -u ansible` (STOP POINT: Must succeed for all hosts)

## Phase 3: Baseline Configuration (Ansible User)
*Apply standard configuration to all LXCs.*

- [x] T008 [US3] Create/Update `ansible/roles/lxc_base/tasks/main.yml` (and handlers) to include `apt update`, `apt upgrade`, and core packages installation
- [x] T009 [US3] Create/Update `ansible/playbooks/site.yml` to target `services` group and apply `lxc_base` role (defaulting to `ansible` user)
- [x] T010 [US3] Run `ansible-playbook playbooks/site.yml` and verify success
- [x] T011 [US3] Run playbook again to verify idempotency (changed=0 for config tasks)

## Dependencies
- US2 depends on US1 (Inventory)
- US3 depends on US2 (Bootstrap)
