# Findings Log

**Feature**: 032-audit-rebuild-readiness
**Date**: 2026-02-05

| ID | Category | Severity | Description | Evidence | Related Items | Status |
| --- | --- | --- | --- | --- | --- | --- |
| FND-001 | incomplete | medium | PVE host NFS mount role exists but is not wired into host playbook; rebuild automation may miss host mounts. | ansible/roles/proxmox_mounts/tasks/main.yml; ansible/playbooks/host_proxmox.yml | INV-007, INV-008 | open |
| FND-002 | rebuild-gap | high | PVE host mount for `/mnt/nas/photo` (used by Immich mp1) appears unmanaged by Ansible role; rebuild could miss this mount. | runtime inventory (mounts); ansible/roles/proxmox_mounts/tasks/main.yml | INV-009, INV-011 | open |
| FND-003 | anti-pattern | medium | Terraform example uses host-path mountpoints for Jellyfin (`/mnt/nas/video`), which conflicts with shared-media policy unless explicitly approved. | terraform/environments/prod.tfvars.example; specs/023-hardning-lxc-gated-deploy/spec.md | INV-003 | open |
