# Feature Specification: Synology NFS Mount on Proxmox Host + Bind Mount into Immich LXC

**Feature Branch**: `003-storage-nfs-synology`
**Created**: 2025-12-15
**Status**: Draft
**Input**: User description: "Synology NFS Mount on Proxmox Host + Bind Mount into Immich LXC"

## Clarifications

### Session 2025-12-15

- Q: How to manage persistent mounts? → A: fstab: Use `/etc/fstab` via Ansible `mount` module.
- Q: How to handle NFS permissions for unprivileged LXC? → A: Synology Squash: Configure Synology NFS rule to "Map all users to admin".
- Q: Where to place Ansible mount tasks? → A: New Role: Create `roles/proxmox_mounts` for modularity.

## User Scenarios & Testing

### User Story 1 - Proxmox Host NFS Mount (Priority: P1)

As a platform engineer, I want the Proxmox host to mount the Synology NFS share so that the storage is available to the hypervisor and can be shared with containers.

**Why this priority**: This is the prerequisite for providing storage to the Immich container. Without the host mount, the bind mount cannot function.

**Independent Test**: Run the Ansible playbook targeting the Proxmox host and verify the mount point exists and is writable.

**Acceptance Scenarios**:

1. **Given** a Proxmox host with network access to the Synology NAS, **When** the Ansible playbook runs, **Then** `nfs-common` is installed.
2. **Given** the playbook runs, **Then** the directory `/mnt/nas/homelab_immich` is created.
3. **Given** the playbook runs, **Then** the NFS share `192.168.1.109:/volume1/homelab_immich` is mounted at `/mnt/nas/homelab_immich`.
4. **Given** the mount is active, **When** I create a file `_host_write_test.txt` in the mount, **Then** the operation succeeds.
5. **Given** the host is rebooted, **Then** the NFS share is automatically remounted (via fstab or systemd).

---

### User Story 2 - Immich Container Bind Mount (Priority: P1)

As a platform engineer, I want the NFS mount to be passed through to the Immich container as a bind mount so that the application can access persistent storage without needing direct NFS access or credentials.

**Why this priority**: This provides the actual storage to the application container, completing the storage provisioning chain.

**Independent Test**: Apply the Terraform configuration and verify the mount point inside the Immich LXC.

**Acceptance Scenarios**:

1. **Given** the host NFS mount is active, **When** Terraform applies the configuration, **Then** the Immich container (CT 213) has a bind mount from `/mnt/nas/homelab_immich` to `/mnt/immich`.
2. **Given** the bind mount is active, **When** I list files in `/mnt/immich` inside the container, **Then** I can see files created on the host/NAS.
3. **Given** the bind mount is active, **When** I create a file `_ct_write_test.txt` inside `/mnt/immich` in the container, **Then** the operation succeeds and the file is visible on the host.
4. **Given** the container is restarted, **Then** the bind mount persists.

---

### Edge Cases

- **NAS Offline**: If the Synology NAS is unreachable during the Ansible run, the playbook should fail gracefully with a clear error message.
- **Boot Failure**: If the NAS is unreachable during Proxmox host boot, the boot process should not hang indefinitely (use `nofail` or appropriate systemd timeouts).
- **Existing Data**: If the mount point directory on the host already contains files (not empty), the mount should still proceed (standard Linux behavior hides underlying files), but ideally, we ensure the directory is empty or dedicated.
- **Permission Denied**: If the NFS export does not allow the Proxmox host IP, the mount command should fail and be reported.

## Requirements

### Functional Requirements

- **FR-001**: Host installs NFS client tooling (`nfs-common`) via Ansible.
- **FR-002**: Host mounts `192.168.1.109:/volume1/homelab_immich` at `/mnt/nas/homelab_immich`.
- **FR-003**: Host mount persists across reboot (configured via `/etc/fstab` with `nofail`).
- **FR-004**: Terraform attaches a bind mount to CT 213 (Source: `/mnt/nas/homelab_immich`, Target: `/mnt/immich`).
- **FR-005**: No secrets committed (no NAS credentials; NFS is IP/ACL based).
- **FR-006**: Solution is idempotent: re-running playbooks and Terraform apply does not break mounts or duplicate entries.
- **FR-007**: NFS Access Strategy: Rely on Synology "Map all users to admin" to handle unprivileged LXC permission mapping.

### Key Entities

- **NFS Share**: The source storage on Synology (`192.168.1.109:/volume1/homelab_immich`).
- **Host Mount Point**: The directory on Proxmox (`/mnt/nas/homelab_immich`).
- **Container Mount Point**: The directory inside Immich LXC (`/mnt/immich`).

## Success Criteria

1. On Proxmox host: `mount | grep homelab_immich` shows NFS mounted at `/mnt/nas/homelab_immich`.
2. On Proxmox host: can create a file in the mount: `_host_write_test.txt`.
3. In Immich LXC: `/mnt/immich` exists and reflects the NAS content.
4. In Immich LXC: can create a file `_ct_write_test.txt` in `/mnt/immich`.
5. After reboot of host OR remount + restart CT: the mount is still present and writable.
6. Re-running Ansible + Terraform is safe and idempotent.
