# Homelab Proxmox Constitution

## Core Principles

### I. Spec-Driven Workflow
All feature work must be driven from `specs/NNN-*/` directories and must reference that spec’s `tasks.md`. The `.specify/memory/constitution.md` and `spec.md` are the sources of truth. Do not implement changes that are not represented in an approved `tasks.md`. If a change alters behaviour/architecture, update the relevant spec/docs in the same change.

### II. Secrets Policy (NON-NEGOTIABLE)
Never commit secrets: Proxmox tokens, passwords, private keys, Synology creds, Tailscale auth keys. Use local `*.tfvars` (gitignored) and/or environment variables for secrets. Copilot must not output real secrets; use placeholders and describe where they come from.

### III. Separation of Concerns
- **Terraform** owns *existence and sizing* of machines (LXCs/VMs) and base provisioning.
- **Ansible** owns *configuration inside* those machines and on the Proxmox host.
**Do not generate code that mixes these responsibilities.**

## Architecture & Boundaries

### Provider Strategy
- Use the `telmate/proxmox` provider (`proxmox_lxc`).
- Do not rewrite Terraform to `bpg/proxmox` resources unless a spec explicitly requests a migration.

### Networking
- Core service LXCs (Immich, AdGuard, Home Assistant, reverse proxy) must have **static IPs** + gateway.
- Avoid scattering IP strings across files: define them centrally (variables/locals) and pass into modules.
- Target network is eventually segmented (Management, Services, LAN, IoT, VPN egress).

### Access Control
- Terraform must inject SSH public keys into LXCs (`ssh_public_keys`) so Ansible can connect without passwords.
- Ansible initially uses `root` for bootstrapping (homelab tradeoff).
- Do not expose Proxmox UI publicly on the internet. Prefer Tailscale for remote admin.

## Baseline Decisions

### State Management
- Terraform state is **local** on the runner.
- State must be backed up to Synology after successful apply (via script/workflow). Do not introduce remote state unless explicitly requested.

### Storage
- Immich user data lives on Synology NAS.
- Initial approach: NFS mounts on Proxmox host, bind-mounted into unprivileged LXCs (Ansible + Terraform managed).
- No Ceph and no unnecessary storage complexity for v1.

### Services Model
- General model: one LXC per service (Debian stable).
- The authoritative list of services and their responsibilities lives in `specs/002-core-services-lxc/spec.md`.
- Do not assume a service exists unless it is defined in the current spec/tasks.

## Workflow & Process

### CI/CD Expectations
- Pipeline should: Validate/plan Terraform -> (Optional) lint Ansible -> Apply Terraform -> Run Ansible.
- Avoid adding destructive automation without clear barriers (e.g. approvals, prevent_destroy).

### Repo Layout
- `docs/` – architecture and network docs.
- `terraform/` – providers, root module, `modules/lxc_service`.
- `ansible/` – inventories, group vars, roles, playbooks.
- `.github/workflows/` – CI and deploy pipelines.
- `scripts/` – helper scripts.

## Governance
This constitution supersedes all other practices. Amendments require documentation and approval. All PRs and reviews must verify compliance with these principles.

**Version**: 1.0.0 | **Ratified**: 2025-12-15
