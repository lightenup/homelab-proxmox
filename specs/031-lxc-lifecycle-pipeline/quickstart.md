# Phase 1 Quickstart: LXC Lifecycle Workflow Consolidation

## Overview
Use the unified LXC lifecycle pipeline for add/change/delete operations. The workflow always produces a plan and an apply, and blocks destructive changes until confirmation is provided via a tag.

## Add or Change a Service

1. Update Terraform service definition and outputs.
2. Update service configuration values (IP, mountpoints).
3. Ensure host variables and service playbooks are present.
4. Trigger the unified lifecycle pipeline (`lxc-lifecycle.yml`).
5. Review plan evidence and approve if required (tag confirmation for destructive changes).
6. Verify post-apply checks and drift status.

## Remove a Service (Full Cleanup)

1. Remove Terraform LXC definition and inventory output mapping.
2. Remove service IPs and mountpoints from variables.
3. Delete host variables if present.
4. Remove service from Ansible service lists, playbooks, and roles.
5. Remove reverse proxy and DNS references.
6. Trigger the unified lifecycle pipeline (`lxc-lifecycle.yml`).
7. If plan includes replace/destroy, apply the protected tag confirmation.
8. If data locations should be deleted, provide explicit data deletion confirmation (`delete-data`).
9. Run inventory update and healthcheck drift verification; retry if any step fails.

## Confirmation Rules

- Destructive apply requires a protected tag controlled by maintainers.
- Data deletion requires explicit confirmation before proceeding.

## Completion Criteria

- No orphaned inventory entries or proxy routes remain.
- Drift/healthcheck verification returns zero GAP/zombie entries.
- Re-running the workflow does not recreate removed services.
