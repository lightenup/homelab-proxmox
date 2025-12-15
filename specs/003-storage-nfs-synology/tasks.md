# Tasks - Synology NFS Mount on Proxmox Host + Bind Mount into Immich LXC

## Phase 1: Proxmox Host Configuration (Ansible)

- [x] **T001**: Verify Proxmox host (`pve`) connectivity in Ansible inventory. <!-- id: 0 -->
- [x] **T002**: Create new Ansible role `proxmox_mounts` structure. <!-- id: 1 -->
- [x] **T003**: Implement task in `proxmox_mounts` to install `nfs-common`. <!-- id: 2 -->
- [x] **T004**: Implement task in `proxmox_mounts` to ensure mount point `/mnt/nas/homelab_immich` exists. <!-- id: 3 -->
- [x] **T005**: Implement task in `proxmox_mounts` to mount NFS share `192.168.1.109:/volume1/homelab_immich` using `ansible.posix.mount` (fstab, nofail). <!-- id: 4 -->
- [x] **T006**: Add `proxmox_mounts` role to `host_proxmox.yml` playbook. <!-- id: 5 -->
- [x] **T007**: Run Ansible playbook and verify host mount works (STOP POINT: Confirm write access on host). <!-- id: 6 -->

## Phase 2: Container Configuration (Terraform)

- [x] **T008**: Inspect `modules/lxc_service` and add support for `mountpoints` if missing. <!-- id: 7 -->
- [x] **T009**: Update `terraform/main.tf` (or variables) to define the bind mount for the Immich container. <!-- id: 8 -->
- [x] **T010**: Run `terraform plan` and `terraform apply`. <!-- id: 9 -->

## Phase 3: Verification

- [x] **T011**: Verify `/mnt/immich` exists inside Immich LXC and shows NAS content. <!-- id: 10 -->
- [x] **T012**: Verify write access from inside the container (`touch /mnt/immich/_ct_test`). <!-- id: 11 -->
- [x] **T013**: Verify persistence (simulate reboot or remount). <!-- id: 12 -->
