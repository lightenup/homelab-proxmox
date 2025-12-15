# Implementation Plan - Synology NFS Mount on Proxmox Host + Bind Mount into Immich LXC

This plan outlines the steps to implement NFS mounting on the Proxmox host and bind mounting into the Immich LXC container.

## Phase 1: Proxmox Host Configuration (Ansible)

**Objective**: Configure the Proxmox host to mount the Synology NFS share persistently.

1.  **Update Ansible Inventory**: Ensure the Proxmox host (`pve`) is correctly defined in the inventory and accessible via Ansible.
2.  **Create Role**: Create a new role `proxmox_mounts` to handle NFS mounts.
    *   Install `nfs-common` package.
    *   Create the local mount point directory `/mnt/nas/homelab_immich`.
    *   Configure the mount using `ansible.posix.mount` (manages `/etc/fstab` and mount state).
    *   Ensure `nofail` option is used to prevent boot hangs if NAS is offline.
3.  **Run Playbook**: Execute the playbook against the Proxmox host.
4.  **Verify Host Mount**: Confirm the share is mounted and writable.

## Phase 2: Container Configuration (Terraform)

**Objective**: Configure the Immich LXC to bind mount the host directory.

1.  **Update Terraform Module**: Check `modules/lxc_service` for mount point support.
    *   If missing, add `mountpoint` variable and `mp0` configuration to the `proxmox_lxc` resource.
2.  **Update Configuration**: Modify `main.tf` or `prod.tfvars` to pass the mount configuration for the Immich container.
    *   Source: `/mnt/nas/homelab_immich`
    *   Target: `/mnt/immich`
3.  **Apply Terraform**: Run `terraform apply` to update the container configuration.
    *   *Note*: This might require a container restart.

## Phase 3: Verification & Persistence

**Objective**: Ensure the solution works end-to-end and survives reboots.

1.  **Verify Container Access**: Check if `/mnt/immich` exists in the container and is writable.
2.  **Test Persistence**: Reboot the Proxmox host (if permissible) or simulate by unmounting and running `mount -a`.
3.  **Idempotency Check**: Re-run Ansible and Terraform to ensure no changes are made when state is correct.
