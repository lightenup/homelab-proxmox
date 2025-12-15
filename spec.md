# homelab-proxmox — Root Specification

## Purpose

This repository defines a **single-node Proxmox homelab** managed with **Infrastructure as Code**.
The primary goal is to make the system **rebuildable after catastrophic failure** using a repeatable workflow and clear documentation, with AI assistance used in a controlled, spec-driven way.

This `spec.md` is the **Phase 0** (“baseline”) specification for the whole repo.
Feature work is specified in `specs/NNN-*/`.

---

## Goals

1. **Rebuildability**
   - Be able to rebuild the homelab from scratch with:
     - a fresh Proxmox install
     - this git repo
     - a runner machine (laptop for now; later a Pi/CI runner)
   - Minimise manual steps and document the unavoidable ones.

2. **Clear ownership boundaries**
   - Terraform owns **Proxmox resources**.
   - Ansible owns **configuration** (host + in-container).

3. **Stability over novelty**
   - Prefer conservative, well-known approaches over clever ones.
   - Avoid premature complexity.

4. **Secure-by-default for a homelab**
   - No public exposure of Proxmox UI.
   - Remote access via Tailscale.
   - No secrets committed to git.

---

## Non-goals

- Multi-node clustering (for now).
- Ceph (for now).
- Publicly exposing Proxmox UI or services directly to the internet.
- Automating BIOS/UEFI configuration as IaC.

---

## Current baseline constraints

- **Proxmox VE**: 9.1.1 (installed manually via ISO).
- **Topology**: single node.
- **Router**: current router has limited DNS features; mDNS is acceptable temporarily.
- **Storage**: user data resides on Synology NAS.
- **Runner**: IaC executed from laptop initially.

---

## Target architecture (high level)

### Compute
- One Proxmox node running:
  - one LXC per service (baseline: Immich, AdGuard, Home Assistant, reverse proxy)

### Network
- Initially: flat LAN.
- Planned future: segmented networks (management/services/IoT) once router/firewall supports it.
- Core services must have **stable IPs** (no DHCP for core services).

### Storage
- Container root disks live on Proxmox storage pool.
- Immich user data lives on Synology NAS.
- Initial approach: NFS mounts inside the Immich LXC (managed by Ansible).

### Access
- Local admin via LAN IP.
- Remote admin via Tailscale (preferred).
- SSH access is key-based.

---

## Tooling and “source of truth”

### Terraform (infrastructure existence)
Terraform creates and manages:
- LXCs (and later VMs if needed)
- static IP configuration for core services
- injection of SSH public keys for initial access

Provider baseline:
- telmate-style provider pattern using `proxmox_lxc` resources (until a spec says otherwise).

### Ansible (configuration + day-2 operations)
Ansible configures:
- host patching / repositories
- in-container packages and configuration
- NFS mounts
- service setup (Immich, AdGuard, HA, reverse proxy)

### Documentation
- `docs/` contains baseline architecture + future network plan.
- `specs/` contains scoped feature specs with `spec.md`, `plan.md`, `tasks.md`.

---

## Acceptance criteria (“done means”)

This repo is considered healthy when:

1. **Terraform**
   - `terraform fmt -recursive` passes
   - `terraform validate` passes
   - `terraform plan` is readable and predictable
   - `terraform apply` can create/update core service LXCs reproducibly

2. **Ansible**
   - Can configure the Proxmox host (repos + patching baseline) successfully
   - Can configure service LXCs successfully
   - Playbooks are idempotent for steady-state runs

3. **Core services**
   - Each service LXC has a stable, documented IP
   - SSH access works via injected keys
   - Basic service reachability checks succeed (DNS/HTTP endpoints as relevant)

4. **Operational safety**
   - No secrets committed to git
   - The repo documents unavoidable manual steps (e.g. BIOS toggles, Proxmox ISO install)

---

## Operational conventions

- Work is driven by the constitution in `.specify/memory/constitution.md`.
- Feature work happens through `specs/NNN-*/` folders.
- Any change that breaks baseline decisions requires a spec and explicit human approval.

---

## Open questions (tracked in feature specs)

- Router/firewall upgrade path and VLAN rollout plan.
- Whether to move from “NFS in guest” to Proxmox-level mount/bind mounts later.
- Whether/when to migrate provider dialect (telmate → bpg).

---

