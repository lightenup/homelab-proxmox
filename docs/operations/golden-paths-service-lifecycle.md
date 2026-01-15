# Golden Paths: Service Lifecycle

**Status**: Draft
**Last Updated**: 2025-12-30
**Context**: Standard procedures for adding, changing, and removing services in the homelab.

## Overview

This runbook defines the "Golden Paths" for service management. Following these procedures ensures:
1.  **Consistency**: All services are defined and monitored in the same way.
2.  **Reliability**: Healthchecks and monitoring are automatically configured.
3.  **Cleanliness**: No orphaned configuration or "zombie" services.

## 1. Add a New Service

**Goal**: Provision a new service (LXC) and register it for automation.

### Prerequisites
- Terraform installed
- Ansible installed
- Access to Proxmox API

### Procedure

1.  **Define Infrastructure (Terraform)**
    - Edit `terraform/main.tf` (or relevant module).
    - Add the `proxmox_lxc` resource.
    - Run `terraform apply`.

2.  **Register Service (Ansible Inventory)**
    - Run the task:
      ```bash
      task service:add -- <service_name> --port <port> --path <path>
      ```
    - This creates/updates `ansible/host_vars/<service_name>.yml`.

3.  **Deploy Service (Ansible)**
    - Run the playbook:
      ```bash
      ansible-playbook ansible/playbooks/site.yml --limit <service_name>
      ```

4.  **Verify**
    - Run the healthcheck suite:
      ```bash
      task healthcheck:run -- --filter <service_name>
      ```
    - Ensure status is `PASS`.

## 2. Change / Upgrade a Service

**Goal**: Update service version or configuration safely.

### Procedure

1.  **Update Configuration**
    - Use the task:
      ```bash
      task service:change -- <service_name> --port <new_port>
      ```
    - Or manually edit `ansible/host_vars/<service_name>.yml`.

2.  **Deploy**
    - Run the playbook:
      ```bash
      ansible-playbook ansible/playbooks/site.yml --limit <service_name>
      ```

3.  **Verify**
    - Run verification:
      ```bash
  task healthcheck:run -- --filter <service_name>
      ```

### Rollback
- Revert the change in `ansible/host_vars/<service_name>.yml`.
- Re-run the deployment playbook.

## 3. Remove a Service

**Goal**: Decommission a service and clean up all artifacts.

### Procedure

1.  **Remove from Inventory**
    - Run the task:
      ```bash
      task service:remove -- <service_name>
      ```
    - This removes the healthcheck configuration. You may also need to remove the file if the service is fully gone.

2.  **Destroy Infrastructure**
    - Edit `terraform/main.tf` to remove the resource.
    - Run `terraform apply`.

3.  **Verify Cleanup**
    - Run drift detection to ensure no zombies remain:
      ```bash
  task healthcheck:run -- --check-drift
      ```

## 4. Drift Detection

**Goal**: Ensure inventory matches reality and schema is valid.

### Procedure
- Run the drift check:
  ```bash
  task healthcheck:run -- --check-drift
  ```
- **GAP**: Service is in inventory but unreachable (Zombie). -> Remove from inventory or fix infra.
- **Schema Error**: `host_vars` has invalid keys. -> Fix the YAML file.
