# Backlog: `lifecycle:verify` looks for Terraform state where the deploy does not put it

**Status**: Backlog — isolated 2026-09-19 while fixing the lifecycle workflow. Not fixed.
**Blast radius**: every `lxc-lifecycle.yml` run reports failure, whatever the apply did.

## Symptom

```
task: [lifecycle:verify] python3 -m homelab_proxmox_orchestrator.ops_cli inventory update
inventory:update failed: terraform output failed
task: Failed to run task "lifecycle:verify": exit status 2
```

The step runs `if: always()`, so a clean apply still ends with a red run. Two *other* bugs in the
same verification chain were fixed the same day — an argparse `REMAINDER` rejection and a missing
vault password — and this is what was underneath them.

## Cause

`inventory.py` runs:

```python
["terraform", "-chdir=terraform", "output", "-json", "ansible_inventory"]
```

Neither the directory nor the state location matches how the pipeline actually deploys:

| | deploy (`pve-service-deploy`) | `inventory update` |
|---|---|---|
| root | `terraform/services/<service>/` | `terraform/` |
| state | explicit `-state="${state_path}"`, from `get_service_state_path` | terraform's default |

Confirmed on `pve` — both roots answer the same way, because the state is not where either lookup
expects it:

```
$ terraform -chdir=terraform          output -json ansible_inventory
Error: Output "ansible_inventory" not found
$ terraform -chdir=terraform/services/monitoring output -json ansible_inventory
Error: Output "ansible_inventory" not found
```

The deploy path works because it passes the state file explicitly. `inventory update` never learned
that convention, so it reads an empty or unrelated state and fails.

Note this is **not** what generates the working inventory: `pve-service-deploy` writes
`ansible/inventories/generated/hosts.yml` itself (with a state-JSON fallback if the output is
missing). So there are two implementations of "derive the inventory from Terraform", and only one of
them is correct — the other is wired into the verification gate.

## Why it was not fixed here

The state-path convention lives in `get_service_state_path` / `ensure_state_path` inside
`scripts/lab/pve-service-deploy`, which is a **protected path**. Teaching `inventory.py` the same
convention would mean duplicating that logic into a second implementation — which is the exact drift
that produced this bug. Deciding between the options below is the work, and it should be a
deliberate change with the protected-path label, not a drive-by.

## Options

1. **Make `lifecycle:verify` call the deploy script's inventory generation** rather than
   reimplementing it. One source of truth; requires touching the protected script or exposing a
   sub-command from it.
2. **Extract the state-path convention** somewhere both the bash and the Python side read — a small
   shared file or an env contract.
3. **Drop `inventory update` from `lifecycle:verify`** if the generated inventory is already written
   by the apply (it is). The verification would then check the *result* rather than regenerate it,
   which is arguably what a verification step should do anyway.

Option 3 is the smallest and may be the most correct: the step currently re-derives state as a way
of checking drift, and ends up asserting its own ability to read Terraform rather than anything
about the deploy.

## Verify before fixing

Run `lxc-lifecycle.yml` for any service and confirm the run is red with a green apply — that is the
whole bug. After a fix, the same run should be green end to end.
