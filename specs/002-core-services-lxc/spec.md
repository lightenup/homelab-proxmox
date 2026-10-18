# Feature Specification: Ansible Bootstrap for Core Service LXCs

**Feature Branch**: `002-core-services-lxc`
**Created**: 2025-12-15
**Status**: Draft
**Input**: User description: "Ansible Bootstrap for Core Service LXCs"

## Clarifications

### Session 2025-12-15

- Q: How to handle missing Python on target hosts? → A: Bootstrap: Include a `raw` task to install `python3` if missing.
- Q: Which user should Ansible connect as? → A: Dedicated User: Attempt to connect as `ansible`.
- Q: How to provision the ansible user? → A: Two-stage Bootstrap: Connect as `root` first to create user, then switch.
- Q: Sudo privileges for ansible user? → A: Passwordless Sudo: Configure `NOPASSWD` in sudoers.
- Q: Which SSH key for ansible user? → A: Reuse Admin Key: Authorize the same public key(s) used for root.

## User Scenarios & Testing

### User Story 1 - Dynamic Inventory Generation (Priority: P1)

As a platform engineer, I want to automatically generate the Ansible inventory from Terraform outputs so that I don't have to manually maintain IP addresses and can ensure consistency between Infrastructure (Terraform) and Configuration (Ansible).

**Why this priority**: This is the bridge between Terraform and Ansible. Without it, we cannot target the provisioned infrastructure reliably.

**Independent Test**: Run the generation script and verify `ansible/inventories/generated/hosts.yml` contains the correct IPs (without CIDR suffix) for all 4 services.

**Acceptance Scenarios**:

1. **Given** Terraform has valid outputs for `ansible_inventory` (potentially with CIDR), **When** I run `scripts/update_ansible_inventory.sh`, **Then** `ansible/inventories/generated/hosts.yml` is created/updated with valid YAML mapping service names to plain IPs (CIDR stripped).
2. **Given** the inventory is generated, **When** I run `ansible-inventory --list`, **Then** it returns a valid JSON representation of the hosts.

---

### User Story 2 - Bootstrap Configuration (Priority: P1)

As a platform engineer, I want to bootstrap the LXCs using the root user so that I can create a dedicated `ansible` user and prepare the environment for standard automation.

**Why this priority**: Essential for establishing a secure and standard automation user, separating initial provisioning from ongoing configuration.

**Independent Test**: Run `ansible-playbook playbooks/bootstrap.yml -u root` and verify the `ansible` user exists and has sudo access.

**Acceptance Scenarios**:

1. **Given** fresh LXCs with root SSH access, **When** I run `playbooks/bootstrap.yml` as root, **Then** Python 3 is installed (if missing).
2. **Given** the bootstrap playbook runs, **Then** an `ansible` user is created with the same authorized keys as root.
3. **Given** the `ansible` user is created, **Then** it has passwordless sudo (`NOPASSWD`) configured.

---

### User Story 3 - Baseline Configuration & Connectivity (Priority: P2)

As a platform engineer, I want to apply a standard baseline configuration using the dedicated `ansible` user so that I can verify the bootstrap process and ensure all services have a common foundation.

**Why this priority**: Validates the `ansible` user's access and applies common configuration.

**Independent Test**: Run `ansible-playbook playbooks/site.yml` (defaulting to `ansible` user) and verify success.

**Acceptance Scenarios**:

1. **Given** the bootstrap process is complete, **When** I run `ansible -m ping all` as the `ansible` user, **Then** all hosts respond with SUCCESS.
2. **Given** reachable hosts, **When** I run `playbooks/site.yml`, **Then** `apt update` runs and core packages are installed.
3. **Given** the playbook has run once, **When** I run it again, **Then** it reports no configuration or package changes (allowing for optional apt cache refresh tasks).

## Requirements

### Functional Requirements

- **FR-001**: System MUST provide a script (`scripts/update_ansible_inventory.sh`) to parse Terraform JSON output and generate `ansible/inventories/generated/hosts.yml`.
- **FR-002**: The generated inventory MUST group hosts under a `services` group.
- **FR-003**: The generated inventory MUST use the IP addresses defined in Terraform outputs.
- **FR-004**: The `lxc_base` Ansible role MUST perform `apt update` and `apt upgrade` (dist-upgrade).
- **FR-005**: The `lxc_base` Ansible role MUST install core dependencies (e.g., `python3`, `curl`, `wget`, `git`, `htop`).
- **FR-006**: The `site.yml` playbook MUST target the generated host group and apply the `lxc_base` role using the `ansible` user.
- **FR-007**: The solution MUST NOT commit the generated inventory file to version control. `.gitignore` MUST include `ansible/inventories/generated/hosts.yml`.
- **FR-008**: The solution MUST use the Ansible `raw` module to bootstrap Python 3 if it is missing on the target host.
- **FR-009**: The solution MUST configure Ansible to connect as the `ansible` user for standard operations (defined in inventory vars).
- **FR-010**: The solution MUST include a `playbooks/bootstrap.yml` that connects as `root` to create the `ansible` user and configure SSH access.
- **FR-011**: The solution MUST configure the `ansible` user with passwordless sudo access (`NOPASSWD`).
- **FR-012**: The solution MUST authorize the existing admin SSH key(s) (used for `root`) for the new `ansible` user.
- **FR-013**: The inventory generation script MUST strip any CIDR suffix (e.g., `/24`) from the IP address before writing `ansible_host`.
- **FR-014**: The inventory generation script MUST fail fast with a clear error message if Terraform state or output is missing.
- **FR-015**: The inventory generation script MUST depend on `jq` and check for its existence.

### Inventory Structure

The generated `hosts.yml` MUST follow this structure:

```yaml
all:
  children:
    services:
      hosts:
        proxy:
          ansible_host: 192.168.1.211
        # ... other hosts
      vars:
        ansible_user: ansible
        ansible_become: true
```

### Key Entities

- **Terraform Output**: The source of truth for IP addresses (JSON format).
- **Generated Inventory**: A YAML file (`hosts.yml`) acting as the dynamic bridge for Ansible.
- **Bootstrap Playbook**: `playbooks/bootstrap.yml` (Run as root).
- **Site Playbook**: `playbooks/site.yml` (Run as ansible).

### Service List

- `ntfy-lxc` – ntfy, the estate's push channel to the owner's phone, at `192.168.1.222`,
  LAN/tailnet only. State (SQLite message cache, auth DB) on local disk, no backup by design
  (FR-014, spec `082`).

## Success Criteria

### Measurable Outcomes

- **SC-001**: `scripts/update_ansible_inventory.sh` executes in < 5 seconds and produces valid YAML with plain IPs.
- **SC-002**: `ansible -m ping` succeeds for 100% of provisioned hosts using the `ansible` user.
- **SC-003**: `ansible-playbook playbooks/site.yml` execution time is < 5 minutes (after initial update).
- **SC-004**: Idempotency check returns no changed tasks on subsequent runs (excluding cache updates).
