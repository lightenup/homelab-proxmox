# Backlog: the gated pipeline's "LAB" stage deploys to the production address space

**Status**: Backlog — found during the `064-llm-router` deploy, 2026-09-19. Not fixed.
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
