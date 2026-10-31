# Backlog: one clear Terraform state location per service

**Status**: **DELIVERED 2026-10-31** inside [`specs/067-isolated-lab/`](../../specs/067-isolated-lab/). Folded into [`067`](./067-lab-prod-same-address-space.md) (decision 5, 2026-10-30): a real lab
needs separate state per environment, so the state layout is done as part of that spec. The backup gap
below is already fixed (PR #295). Raised 2026-10-28 during the Home Assistant deploy (PR #293).
**Scope**: every service's Terraform state on `pve` and on the NAS. Related: [`067`](./067-lab-prod-same-address-space.md),
[`068`](./068-lifecycle-verify-terraform-state.md).

## What is there today

Measured on `pve` on 2026-10-28.

`pve-service-deploy` resolves state through `scripts/lab/lib/state.sh`. The pipeline does not set
`USE_NAS_STATE`, so it takes the legacy branch and uses
`/var/lib/homelab-proxmox/state/services/<svc>/terraform.tfstate` for **both** `lab` and `prod`.
What that path actually is depends on the service:

| Service | `/var/lib/homelab-proxmox/state/services/<svc>` |
| --- | --- |
| homeassistant, immich, jellyfin, monitoring, reverse_proxy | symlink to `/mnt/nas/homelab_ci/infra_state/lab/<svc>` (created 2026-02-09 by `setup-state-symlinks.yml`) |
| eurooffice, financial-scenario, hermes, llm-router, market-model, nextcloud, ntfy | a plain directory on `pve`'s root disk |

And:

- `/mnt/nas/homelab_ci/infra_state/prod/{immich,monitoring,reverse_proxy}` exist and have been
  **empty since 2026-02-09**. Nothing writes there.
- The older monolithic root (`terraform/main.tf`, `terraform/outputs.tf`) still declares
  `homeassistant_lxc`, `immich_lxc`, `reverse_proxy_lxc` and others, next to the per-service roots
  the pipeline uses. `068` is one consequence (`inventory update` reads the default state).
- **No state at all** tracked VMID 104 `homeassistant`, which had run for months. Nothing noticed.
  The pipeline then created a second container with the same IP (see `067`'s 2026-10-28 update).

## Why it matters

- **The names lie.** Production state lives under a folder called `lab/` for five services, and the
  folder called `prod/` is empty. Anyone restoring or debugging state goes to the wrong place first.
- **Seven states have no backup.** The PVE config backup (`proxmox-config-backup.sh.j2`) copies
  `/mnt/nas/homelab_ci/infra_state/*` and the old repo `terraform/terraform.tfstate`, nothing under
  `/var/lib/homelab-proxmox/state`. So the states of eurooffice, financial-scenario, hermes,
  llm-router, market-model, nextcloud and ntfy exist only on `pve`'s root disk (checked
  2026-10-28). Losing that disk means re-importing seven containers by hand. **Do this part
  first**, even before the rest of this item: it is a backup gap, not a tidiness problem.
  **Fixed 2026-10-28 (PR #295)**: the PVE config backup now collects the plain directories under
  `/var/lib/homelab-proxmox/state/services` into `iac-artifacts/local-state/` (they pass its
  plaintext-secret scan; checked on `pve` before the change). Live since 2026-10-28:
  `backup_proxmox.yml` was applied on `pve`, and a manual run logged "Collecting local Terraform
  state" and grew the manifest from 22 to 39 files (the 15 local state files plus homeassistant's
  new NAS state); the archive passed the script's decrypt and structure checks.
- **Untracked containers are invisible.** Terraform cannot warn about a container it does not know,
  and nothing else compares `pct list` with the states. The new create-time guard
  (`scripts/lab/lib/ct_conflicts.sh`) only fires when a plan *creates* something.

## Proposed direction

1. **Inventory first.** For every CT on `pve`, find which state file tracks it (exactly one). Script
   it so it can be rerun: `pct list` against `terraform state list`/`show` for each state path.
   Today's expectation: every CT tracked once, now that 104 is gone. Record the result here.
2. **Pick one location per service**, named for what it is. Since LAB and PROD share state today, a
   neutral `infra_state/services/<svc>/` on the NAS (with `pve`'s local copy only as a cache, or not
   at all) is more honest than either `lab/` or `prod/`. If `067` direction 1 (a real lab) goes
   ahead, split into `infra_state/{lab,prod}/<svc>` at that point, not before.
3. **Migrate with backups**: copy every `terraform.tfstate` (and `.backup`) to a dated folder first,
   move one service at a time, run a plan for it afterwards and expect `No changes`.
4. **Remove the leftovers**: the `lab/` symlinks, the empty `prod/` folders, `USE_NAS_STATE`'s legacy
   branch once nothing uses it, and the per-service resources in the monolithic root (or the root
   itself) after `068` is fixed.
5. **Keep it true**: a nightly check (the healthcheck automation or a `nightly-deeper-verification`
   step) that fails when a CT on `pve` is tracked by zero or more than one state, so the next
   VMID 104 is found in a day, not by accident.

## Open questions

- Should the state be locked during a deploy? Two concurrent deploys of the same service are already
  prevented by workflow `concurrency`, but `lxc-lifecycle.yml` and manual runs are not.
