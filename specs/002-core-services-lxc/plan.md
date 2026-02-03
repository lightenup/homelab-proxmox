# Implementation Plan: Ansible Bootstrap for Core Service LXCs

**Branch**: `002-core-services-lxc` | **Date**: 2025-12-15 | **Spec**: [specs/002-core-services-lxc/spec.md](specs/002-core-services-lxc/spec.md)
**Input**: Feature specification from `/specs/002-core-services-lxc/spec.md`

## Summary

Implement a dynamic inventory generation workflow using Terraform outputs and `jq` to feed Ansible. Establish a two-stage configuration workflow: a bootstrap playbook (run as root) to provision a dedicated `ansible` user, and a site playbook (run as ansible) to apply baseline configurations.

## Technical Context

**Language/Version**: Bash (Inventory Script), Ansible YAML (Configuration)
**Primary Dependencies**: `jq` (JSON processing), Ansible Core >= 2.10
**Target Platform**: Debian 12 (LXC Containers)
**Project Type**: Infrastructure / Configuration Management

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- [x] **No Secrets**: Inventory generation must not expose secrets.
- [x] **Idempotency**: Ansible playbooks must be idempotent.
- [x] **Single Source of Truth**: Terraform is the source for IPs; Ansible consumes them.

## Project Structure

### Documentation (this feature)

```text
specs/002-core-services-lxc/
├── plan.md
├── spec.md
└── tasks.md
```

### Source Code

```text
scripts/
└── update_ansible_inventory.sh  # Generates inventory (strips CIDR)

ansible/
├── ansible.cfg
├── inventories/
│   └── generated/
│       └── hosts.yml            # Generated (gitignored)
├── playbooks/
│   ├── bootstrap.yml            # Initial setup (root -> ansible user)
│   └── site.yml                 # Main entrypoint (ansible user)
└── roles/
    └── lxc_base/                # Baseline configuration
        ├── tasks/
        │   └── main.yml
        └── handlers/
            └── main.yml
```

## Technical Approach

### 1. Inventory Generation
- **Script**: `scripts/update_ansible_inventory.sh`
- **Input**: `terraform output -json ansible_inventory`
- **Processing**: Use `jq` to parse the JSON.
- **Transformation**: Strip CIDR suffix (e.g., `/24`) from IPs.
- **Output**: Generate YAML structure with `services` group and `ansible_user: ansible` var.
- **Constraints**: Fail fast if Terraform state is missing or `jq` is not installed.

### 2. Bootstrap Workflow
- **Playbook**: `playbooks/bootstrap.yml`
- **User**: Run as `root` (via `-u root` or inventory override).
- **Tasks**:
    - Install Python 3 (using `raw` module if needed).
    - Create `ansible` user.
    - Configure passwordless sudo for `ansible`.
    - Authorize admin SSH keys for `ansible` (copy from root's `authorized_keys` on target).

### 3. Baseline Configuration
- **Playbook**: `playbooks/site.yml`
- **User**: Run as `ansible` (default from inventory).
- **Role**: `lxc_base`
- **Tasks**:
    - `apt update` & `dist-upgrade`.
    - Install core packages (`curl`, `git`, etc.).

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Custom Script | Ansible's native Terraform inventory plugins can be complex/slow | Simple JSON parsing via `jq` is faster and sufficient for this scale |
| Two Playbooks | Need to transition from root (provisioning) to ansible (config) | Single playbook requires complex privilege escalation handling per task |
