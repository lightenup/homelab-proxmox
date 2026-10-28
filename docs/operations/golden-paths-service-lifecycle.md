# Golden Paths: Service Lifecycle

**Status**: Draft
**Last Updated**: 2026-01-18
**Context**: Standard procedures for adding, changing, and removing services in the homelab.

## Overview

This runbook defines the "Golden Paths" for service management. Following these procedures ensures:
1.  **Consistency**: All services are defined and monitored in the same way.
2.  **Reliability**: Healthchecks and monitoring are automatically configured.
3.  **Cleanliness**: No orphaned configuration or "zombie" services.
4.  **Safety**: Destructive changes require explicit confirmation.

> **`environment: lab` is not isolated.** The lab tfvars point at the production host, bridge and
> service IPs, and lab and prod share one Terraform state per service. A lab apply changes the
> real LXC. See [`docs/backlog/067`](../backlog/067-lab-prod-same-address-space.md).

## Unified LXC Lifecycle Pipeline

All add/change/delete operations use the single workflow: `.github/workflows/lxc-lifecycle.yml`.

**Workflow Inputs**:
- `service`: LXC service slug (e.g., `immich`)
- `action`: `add` | `change` | `delete`
- `environment`: `lab` | `prod`
- `confirm_destructive_tag`: required if the plan includes replace/destroy (tag must point at the commit)
- `confirm_data_delete`: required for delete (`delete-data`)
- `confirm_apply_prod`: required for prod apply (`deploy-prod`)

**Destructive Approval**:
- Maintainership is defined in [.github/CODEOWNERS](../.github/CODEOWNERS).
- Destructive approval is provided by a tag that points at the exact commit being deployed.

## 1. Add a New Service

**Goal**: Provision a new service (LXC) and register it for automation.

### Prerequisites
- Terraform installed
- Ansible installed
- Access to Proxmox API

### Procedure

1.  **Define Infrastructure (Terraform)**
  - Add a per-service root under `terraform/services/<service>/`.
  - Update `terraform/outputs.tf` (ansible inventory mapping).
  - Update `terraform/environments/*/tfvars` for `service_ips` and `service_mountpoints`.

### Bind Mount Configuration

If the new service requires NAS host-path bind mounts (e.g., media libraries, user data), follow this checklist before deploying:

**(a) Determine required host paths**
- Check service documentation for NAS storage needs. All paths MUST be under `/mnt/nas/` (enforced by the orchestrator allowlist).

**(b) Declare mounts in `service_mountpoints` in `terraform/environments/<env>.tfvars`**

  Add an entry for your service. Example (Nextcloud):
  ```hcl
  service_mountpoints = {
    nextcloud = {
      data = {
        mp     = "/mnt/nextcloud"
        volume = "/mnt/nas/homelab_nextcloud"
      }
    }
    # For read-only mounts, add: readonly = true
    # e.g. readonly = true
  }
  ```
  The `mp` field is the path inside the container; `volume` is the host NAS path.
  Set `readonly = true` for media or photo libraries that the service should not modify.

**(c) Deploy via `pve-service-deploy apply`**
- The orchestrator applies mounts automatically via `pct set` (Tier 2), no `root@pam` token required.
- The container is created by Terraform without host-path `mountpoint {}` blocks; bind mounts are applied in the post-create step.

**(d) Verify**
- Check the step summary for per-mount result states (`applied`, `skipped`, `failed`).
- Inspect `reports/apply/lxc-mountpoints.txt` in the evidence artifact for before/after container configuration.
- On re-deploy, already-applied mounts show as `skipped` (idempotent).

2.  **Register Service (Ansible)**
    - Run the task:
      ```bash
      task service:add -- <service_name> --port <port> --path <path>
      ```
    - This creates/updates `ansible/host_vars/<service_name>.yml`.

3.  **Deploy Service (Pipeline)**
  - Run the unified workflow with `action=add`.

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
  - Run the unified workflow with `action=change`.

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

1.  **Remove Infrastructure Definitions (Terraform)**
  - Remove `terraform/services/<service>/`.
  - Remove the service from `terraform/outputs.tf` (ansible inventory mapping).
  - Remove `service_ips` and `service_mountpoints` entries from `terraform/environments/*/tfvars`.

2.  **Remove Ansible References**
  - Delete `ansible/host_vars/<service>.yml`.
  - Remove the service from `ansible/playbooks/services.yml`.
  - Remove any service-specific playbooks or roles.

3.  **Remove Proxy/DNS References**
  - Delete reverse proxy templates and task references.
  - Update [docs/reverse-proxy.md](../reverse-proxy.md).

4.  **Remove Data Locations (with confirmation)**
  - Data deletion is gated by explicit confirmation: `confirm_data_delete=delete-data`.

5.  **Run Unified Pipeline (Delete)**
  - Run the unified workflow with `action=delete`.
  - If the plan is destructive, apply a confirmation tag pointing to the commit.
  - Ensure inventory update + drift checks pass.

## 4. Drift Detection

**Goal**: Ensure inventory matches reality and schema is valid.

### Procedure
- Run the drift check:
  ```bash
  task healthcheck:run -- --check-drift
  ```
- **GAP**: Service is in inventory but unreachable (Zombie). -> Remove from inventory or fix infra.
- **Schema Error**: `host_vars` has invalid keys. -> Fix the YAML file.
