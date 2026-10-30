# Backlog: the gated pipeline's "LAB" stage deploys to the production address space

**Status**: Ready for spec — found during the `064-llm-router` deploy, 2026-09-19. Direction 2
(honest labels) partly done 2026-10-28; direction 1 (a real isolated lab) decided 2026-10-30, see
[Decisions for the spec](#decisions-for-the-spec-2026-10-30). Absorbs [`096`](./096-terraform-state-layout.md).
**Scope**: every service, not just `064`.

## The gap

`lxc-deploy-lab.yml` reads as a rehearsal: plan, apply, verify, *then* promote to PROD. For
per-service LXC deploys it is not one. `scripts/lab/pve-service-deploy` resolves tfvars from
`TFVARS_DIR=/var/lib/homelab-proxmox/tfvars`, rendered from
`terraform/environments/${ENVIRONMENT}.tfvars.template` — and the two templates are
**byte-identical apart from one comment and one immich mountpoint**:

```
$ diff terraform/environments/lab.tfvars.template terraform/environments/prod.tfvars.template
1c1
< # CI template — real non-secret values. Do not copy for local use; see lab.tfvars.example instead.
---
> # CI template — real non-secret values. Do not copy for local use; see prod.tfvars.example instead.
23a24,28
>     external_photo = { ... }        # an immich mountpoint
```

Both put `proxmox_node = "pve"`, `services_bridge = "vmbr0"`, `network_gateway = "192.168.1.1"` and
the real production `service_ips`. So a LAB apply creates the **real LXC at its production address
on the production bridge**. The LAB and PROD stages of the pipeline build the same thing in the same
place; "lab" is a gating stage, not an environment.

`terraform/environments/lab.tfvars` — the file that *does* describe a separate `192.168.20.0/24`
network — is a fallback the pipeline never reaches, because `TFVARS_DIR` takes precedence.

## Why it matters

- **A "LAB deploy" is a production change.** During `064` this was verified rather than inferred:
  the plan showed `ip = "192.168.1.220/24"`, `target_node = "pve"`, and the apply created the live
  service. Nothing warns you.
- **PROD promotion is close to a no-op** for the resource, which makes the gate weaker than it
  looks: the thing it is gating already happened.
- **It silently invalidated a feature's design reasoning.** `064` planned around LAB being unable to
  reach the Mac's subnet, and documented expected-red checks on that basis. All of it was wrong,
  and wrong in the *safe* direction only by luck.

## The other half: the inventories are NOT the same

Confusingly, the mirror image holds for Ansible. `pve-service-deploy` layers
`ansible/inventories/${ENVIRONMENT}/hosts.yml` when deploying `monitoring`, and there the two
environments differ completely — the lab inventory has **one host** (`lab-pve-01`) and no services.
So a lab-path monitoring deploy renders an empty scrape config and no alert rules, for every
service, while appearing to succeed. Found the same day, by deploying monitoring on the lab path and
getting nothing.

So: **addresses are shared, inventories are not.** Either alone is manageable; together they mean
"which environment am I deploying to" has two different answers depending on which tool is reading.

## Possible directions

Not a recommendation — this needs a decision about what the pipeline is *for*:

1. **Make LAB real.** Give the lab template its own addressing on `vmbr99`/`10.99.0.0/24` (the
   bridge exists; it currently serves the nested VM rebuild rig). Highest fidelity, most work, and
   it needs somewhere for the LXCs to actually run.
2. **Make LAB honestly a gate.** Keep one address space, rename the stages so nobody reads "lab" as
   "safe", and drop the expectation that PROD promotion is a second deployment.
3. **Leave it, document it loudly.** Cheapest. The trap stays, but stops being a surprise.

Whichever way, the inventory asymmetry should be fixed alongside — a monitoring deploy that
silently renders nothing is a failure mode with no signal at all.

## First step

Confirm the blast radius before changing anything: for each service in the dropdown, diff what a
lab plan and a prod plan would create. If they are identical for every service, this is a naming and
documentation problem. If they differ for some, the pipeline has two behaviours and that is worth
knowing before picking a direction.

## Update 2026-10-28: the state is shared too, and it caused a duplicate IP

Found while deploying Home Assistant (PR #293).

**It is not only the addresses.** `USE_NAS_STATE` is unset in the pipeline, so
`scripts/lab/lib/state.sh` returns the legacy path `/var/lib/homelab-proxmox/state/services/<svc>`
for **both** environments. LAB and PROD read and write the same `terraform.tfstate`. That is why the
PROD apply is close to a no-op: by the time it runs, LAB has already recorded the resource. (The
state layout itself is [`096`](./096-terraform-state-layout.md).)

**What it cost.** VMID 104 `homeassistant` (192.168.1.212) existed but no state tracked it. The
homeassistant state was empty, so the LAB plan created VMID 112 on `pve` with the same IP, and both
started at boot. The plan was correctly flagged non-destructive (it only created). The duplicate
name check in `pve-service-deploy` should have stopped it, but it read the name from the `Lock`
column of `pct list` and so had never matched anything.

**Done (direction 2, partly):**

- `pve-service-deploy` refuses a plan that creates an LXC whose hostname or IP is already used by
  any container on the host (`scripts/lab/lib/ct_conflicts.sh`, in plan and apply, fails closed if
  `pct` returns nothing; tests in `python/tests/guardrails/test_ct_conflict_guard.py`). It replaces
  the broken name check.
- The LAB jobs are named `Plan (LAB, prod host)` / `Apply (LAB, changes prod)`, the three workflows
  carry a header note, and `AGENTS.md`, `docs/architecture/019` and the golden-paths runbook say that
  a LAB apply changes production.

**Still open: direction 1, a real isolated lab.** Feature-sized. It needs at least:

1. A lab tfvars on `vmbr99`/`10.99.0.0/24` (or another isolated range) with its own service IPs,
   and somewhere for those LXCs to run without crowding production (`pve` capacity, or the nested
   `lab-pve-01`).
2. Separate Terraform state per environment (depends on [`096`](./096-terraform-state-layout.md)).
3. Lab-side reachability: DNS names, a lab Caddy (or direct access), and certificates, otherwise
   every Caddy-routed healthcheck and blackbox probe fails or, worse, probes production.
4. Lab NAS mounts that cannot touch production data (a separate share prefix), and backups switched
   off or pointed elsewhere.
5. A lab inventory with a `services` group, so the 072 monitoring guard has something real to
   render, and a lab monitoring target that does not alert the phone.
6. A decision on secrets: a lab vault, or prod secrets on lab hosts (which defeats part of the point).

Until then, treat every LAB apply as a production change.

## Decisions for the spec (2026-10-30)

Owner decisions taken with the facts below; the spec (`specs/067-*`) starts from these.

**Facts on `pve` (2026-10-30):** 31 GB RAM, about 20 GB available, 8 cores, 12 running service LXCs
(36 GB memory configured, about 11 GB actually used). `vmbr99` exists as `10.99.0.1/24` and is
NAT'ed out of `vmbr0` (`/etc/network/interfaces`), which today lets `10.99.0.0/24` reach the whole
production LAN. On that range, only `.1` (gateway), `.10` (`lab-pve-01`) and `.11` are in use.

| # | Question | Decision |
|---|---|---|
| 1 | Where lab LXCs run | On `pve`, on `vmbr99` / `10.99.0.0/24`. Not the nested `lab-pve-01`, not a second host. |
| 2 | Lifecycle | **Ephemeral per run.** The LAB stage creates the service's lab LXC, deploys, verifies and destroys it. At most one lab LXC exists at a time (single runner). |
| 3 | Secrets | **Prod vault, accepted risk.** Lab deploys use the production vault. Mitigated by 2 (minutes of lifetime) and 6 (no LAN reach). Existing PROD-only gates stay in force (for example the Home Assistant MCP token is `enabled` only when `hermes_agent_operational`, 095 R-016 addendum). |
| 4 | Scope | **All services at once**: every service in the pipeline dropdowns gets a real lab path in this feature. |
| 5 | State (absorbs `096`) | One state location per service **per environment**, honestly named (for example `infra_state/{lab,prod}/<svc>`), with backups. Migrate the existing states (copy first, one service at a time, `No changes` after), remove the `lab/` symlinks, the empty `prod/` folders and the legacy `USE_NAS_STATE` branch, and add the nightly "every CT on `pve` tracked by exactly one state" check from `096`. |
| 6 | Isolation | **Internet only, LAN blocked.** A firewall on `pve` lets `10.99.0.0/24` reach the internet (image pulls, apt) and its gateway, and nothing on `192.168.1.0/24` beyond exceptions the spec lists and justifies (DNS, if needed). Lab copies therefore cannot use prod services (LLM router, ntfy, NAS); checks that depend on them are skipped in lab and listed per service. |
| 7 | Verification | **Direct-IP checks only.** LAB healthchecks hit the lab LXC's `10.99.0.x` address from `pve`. No lab Caddy, DNS or certificates. Caddy-routed and blackbox checks are skipped in lab and must never probe production. |
| 8 | NAS mounts | **Local scratch directories.** In lab, each mountpoint is backed by an empty per-run directory on `pve`'s local disk instead of the NAS share, removed with the LXC. |
| 9 | Monitoring and backups | **Neither** for lab LXCs: no Prometheus scrape, no blackbox probe, no backup timer, no phone alert. The LAB stage's own checks are the verification. |
| 10 | Lab IPs | **Mirror the last octet**: `192.168.1.212` becomes `10.99.0.212`. Today's services sit at `.211`–`.222`, clear of the rig. |

**Measured cost of 2 (lab apply, per run):**
- Today a re-apply takes about 30 s–2 min, the median of the run records in
  `/var/lib/homelab-proxmox/artifacts/service-deploy-runs`.
- A fresh LXC costs about 100 s fixed, measured on the first Home Assistant deploy on 2026-10-28:
  create 8 s, bootstrap about 20 s, base and node_exporter about 40 s, Docker 25 s.
- Image pulls run at about 27 MB/s (3.5 GB pulled and started in 130 s).
- Expected per run: +1–3 min for small services (ntfy, jellyfin, reverse_proxy,
  financial-scenario, market-model), +4–6 min for nextcloud, homeassistant, llm-router, monitoring
  and immich, about +6.5 min for eurooffice (7.2 GB), and about +9 min for hermes (12.1 GB of
  images; Prod 1 goes from about 4 to about 13 min).
- A pull-through image cache on `pve` is the lever if this hurts; not in scope unless the spec
  finds it necessary.

**Consequences the spec must handle:**
- The PROD stage becomes a real deployment again, not a near no-op, because lab and prod no longer
  share an LXC or a state.
- A lab LXC starts empty every run: app checks run on fresh data, and restores and migrations of
  real data are not exercised in lab.
- The lab inventory (`inventories/lab/hosts.yml`) needs a `services` group with the lab
  addresses, so the 072 monitoring guard and the playbooks have real lab targets. Rendering
  monitoring config in lab must still never touch production (072).
- Constitution V (dual-provisioning parity): the lab path must also run from a laptop.
- Duplicate-CT guard (`ct_conflicts.sh`): lab LXCs must not trip it against prod, and must not
  slip past it against a leftover lab LXC from an aborted run.
- Cleanup of an aborted run (runner killed mid-run): the next run, or a scheduled job, removes
  stale lab LXCs and scratch directories.
