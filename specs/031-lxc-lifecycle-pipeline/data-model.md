# Phase 1 Data Model: LXC Lifecycle Workflow Consolidation

## Entities

### Service
- **Represents**: A named LXC-backed service with infra, config, and automation references.
- **Key fields**: `name`, `lxc_id`, `ip_address`, `mountpoints`, `status`.
- **Relationships**: One Service → one LXC Instance; one Service → many Inventory Entries, Host Variables, Proxy Routes, Healthcheck Records, Data Locations.

### LXC Instance
- **Represents**: The Proxmox LXC managed by Terraform.
- **Key fields**: `lxc_id`, `node`, `template`, `resources`, `ssh_keys`.
- **Relationships**: One LXC Instance belongs to one Service.

### Inventory Entry
- **Represents**: Generated Ansible inventory targeting the Service.
- **Key fields**: `service_name`, `ansible_host`, `groups`.
- **Relationships**: One Service → one Inventory Entry.

### Host Variables
- **Represents**: Service-specific Ansible variables.
- **Key fields**: `service_name`, `vars`, `healthchecks`.
- **Relationships**: One Service → one Host Variables file (optional).

### Proxy/DNS Route
- **Represents**: Reverse proxy routing and DNS mapping.
- **Key fields**: `service_name`, `hostname`, `backend_target`.
- **Relationships**: One Service → many Proxy/DNS Routes.

### Healthcheck Record
- **Represents**: Monitoring or drift-check records for the Service.
- **Key fields**: `service_name`, `status`, `last_checked`.
- **Relationships**: One Service → one or more Healthcheck Records.

### Data Location
- **Represents**: NAS mounts, bind mounts, and data directories.
- **Key fields**: `service_name`, `path`, `mount_type`, `confirmed_for_deletion`.
- **Relationships**: One Service → many Data Locations.

### Pipeline Run
- **Represents**: A lifecycle execution run.
- **Key fields**: `run_id`, `action` (add/change/delete), `plan_artifact`, `apply_artifact`, `status`.
- **Relationships**: One Pipeline Run operates on one Service.

### Destructive Confirmation
- **Represents**: Approval signal for replace/destroy or data deletion.
- **Key fields**: `type` (label/tag), `set_by`, `set_at`.
- **Relationships**: One Pipeline Run → zero or one Destructive Confirmation.

## State Transitions

- **Service**: `active` → `removing` → `removed` (only after verification success).
- **Pipeline Run**: `planned` → `approved` (if destructive) → `applied` → `verified` → `complete`.
- **Data Location**: `present` → `confirmed_for_deletion` → `deleted`.
