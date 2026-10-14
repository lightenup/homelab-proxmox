# Backlog: move the real LAN topology out of the repo before it goes public

**Status**: Backlog — raised 2026-10-14 during the pre-flight for making the repo public. Not started.
**Scope**: live config (inventory, `group_vars`, `host_vars`, tfvars templates, service
`variables.tf` defaults). Docs and specs are a separate, cosmetic pass.

## The gap

The real `192.168.1.0/24` addresses are on ~1,025 lines in 236 tracked files. Most are prose in
`specs/` and `docs/`, but the pipeline reads the live ones straight from the checkout on `pve`:

- `ansible/inventories/prod/hosts.yml` — every `ansible_host`
- `ansible/group_vars/{monitoring,proxmox_hosts,services}/vars.yml`
- `ansible/host_vars/{llm-router,market-model}.yml`
- `terraform/environments/{lab,prod}.tfvars.template` — `network_gateway`, `service_ips`
- `terraform/services/*/variables.tf` — IP defaults in 12 services

Removing them from the tree means the pipeline must get them from somewhere else, so this is a
pipeline change, not a find-and-replace.

## Why it matters (and why only a little)

- The addresses are RFC1918 behind NAT and cannot be reached from the internet. Publishing them
  is reconnaissance detail, not a credential.
- **Git history keeps every value regardless.** This item only stops new exposure and makes
  topology a deploy-time input. It does not un-publish anything. Rewriting history is out of scope
  (decided 2026-10-14: emails and history stay as is).

## Shape of a fix (to be specced)

- One private source of truth on `pve` — e.g. `/var/lib/homelab-proxmox/topology.yml`, alongside
  the existing `TFVARS_DIR=/var/lib/homelab-proxmox/tfvars` — rendered into the inventory and tfvars
  at deploy time.
- Repo keeps `*.example` files with documentation-range addresses (`192.0.2.0/24`, RFC 5737).
- Service `variables.tf` lose IP defaults; a missing value fails the plan instead of silently
  falling back.
- Watch [`067`](./067-lab-prod-same-address-space.md): the LAB and PROD templates are already
  near-identical, so the same change could give LAB its own address space.

## Related

- Pre-flight hardening done on 2026-10-14: `mutation.yml` no longer runs fork PRs on the
  self-hosted runner.
