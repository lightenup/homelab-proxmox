# GitHub Copilot Instructions – homelab-proxmox

## Source of truth (Spec-driven workflow)
- Follow `.specify/memory/constitution.md`.
- Baseline overview: `spec.md`.
- Feature work must be driven from `specs/NNN-*/` and must reference that spec’s `tasks.md`.
- Do not implement changes that are not represented in an approved `tasks.md`.
- If a change alters behaviour/architecture, update the relevant spec/docs in the same change.

## Goal
This repo describes my Proxmox homelab, managed as code:

- **Terraform** → Proxmox resources (VMs, LXCs, networks, disks).
- **Ansible** → Proxmox host config + service config inside LXCs.
- **CI/CD** → executed from my laptop for now; later via a self-hosted runner (Raspberry Pi).

Helper/community scripts (e.g. tteck Proxmox scripts) are **reference only**, not part of the runtime.

## Ownership boundaries (do not mix)
- Terraform owns *existence and sizing* of machines (LXCs/VMs) and base provisioning:
  - Files: `terraform/main.tf`, `terraform/modules/**`
- Ansible owns *configuration inside* those machines and on the Proxmox host:
  - Files: `ansible/**`

**Important: do not generate code that mixes these responsibilities.**

## Baseline decisions (locked unless a spec explicitly changes them)

### Provider
- Use the telmate-style provider/resources (`proxmox_lxc`).
- Do not rewrite Terraform to `bpg/proxmox` resources unless a spec explicitly requests a migration.

### Networking
- Core service LXCs (Immich, AdGuard, Home Assistant, reverse proxy) must have **static IPs** + gateway.
- Avoid scattering IP strings across files: define them centrally (variables/locals) and pass into modules.

### Access
- Terraform must inject SSH public keys into LXCs (`ssh_public_keys`) so Ansible can connect without passwords.
- Ansible initially uses `root` for bootstrapping (homelab tradeoff).

### State
- Terraform state is **local** on the runner.
- State must be backed up to Synology after successful apply (via script/workflow). Do not introduce remote state unless explicitly requested.

### Storage
- Immich user data lives on Synology NAS.
- Initial approach: NFS mounts inside the Immich LXC (Ansible-managed).
- No Ceph and no unnecessary storage complexity for v1.

### Exposure / remote access
- Do not expose Proxmox UI publicly on the internet.
- Prefer Tailscale for remote admin.

### Out of scope
- BIOS/UEFI settings (XMP, VT-d toggles, fan curves) are not managed by IaC. Document only.

## Network architecture intent
- Target network is eventually segmented (Management, Services, LAN, IoT, VPN egress).
- LXCs for Immich/AdGuard/HA/Reverse Proxy live in the **Services** network.

## Services
- General model: one LXC per service (Debian stable).
- The authoritative list of services and their responsibilities lives in:
  - `specs/002-core-services-lxc/spec.md`
- Do not assume a service exists unless it is defined in the current spec/tasks.

## Repo layout (navigation)
- `docs/` – architecture and network docs.
- `terraform/` – providers, root module, `modules/lxc_service`.
- `ansible/` – inventories, group vars, roles, playbooks.
- `.github/workflows/` – CI and deploy pipelines.
- `scripts/` – helper scripts (inventory generation, tfstate backup).

## CI/CD expectations
- Pipeline should:
  - Validate/plan Terraform.
  - (Optional) lint Ansible.
  - Apply Terraform then run Ansible.
- Avoid adding destructive automation without clear barriers (e.g. approvals, prevent_destroy).

## Secrets policy (hard rule)
- Never commit secrets: Proxmox tokens, passwords, private keys, Synology creds, Tailscale auth keys.
- Use local `*.tfvars` (gitignored) and/or environment variables for secrets.
- Copilot must not output real secrets; use placeholders and describe where they come from.

