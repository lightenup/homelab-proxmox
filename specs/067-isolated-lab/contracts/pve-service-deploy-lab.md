# Contract: `pve-service-deploy` with `--environment lab`

The CLI does not change. `--environment lab` changes meaning: it becomes an ephemeral, isolated
rehearsal. The pipeline (`lxc-promote-prod.yml`, `lxc-lifecycle.yml`) and a laptop over SSH call it
the same way (FR-019).

```text
pve-service-deploy plan  --environment lab --service <svc>
pve-service-deploy apply --environment lab --service <svc> [--from-plan-run-id <id>]
pve-service-deploy {plan,apply} --environment prod --service <svc>     # unchanged CLI
```

## Environment inputs (unchanged)

`TFVARS_DIR`, `ARTIFACT_ROOT`, `ARTIFACT_RUNS_DIR`, `VAULT_ID`, `ANSIBLE_VAULT_PASSWORD_FILE`,
`TF_VAR_proxmox_api_token_*`, `GIT_SHA`/`GIT_REF`. `USE_NAS_STATE` and `STATE_PATH_DEFAULT_ROOT` are
**removed**. The state root is fixed at `/var/lib/homelab-proxmox/state/<env>/`. A `STATE_ROOT`
override exists for tests only.

## `apply --environment lab`: ordered steps

| # | Step | Fails the run when | Evidence |
|---|---|---|---|
| 1 | Acquire `state/lab/.lock` (non-blocking `flock`) | lock held | `events.jsonl` |
| 2 | Pre-run sweep (lab-copy identity rule) | a sweep destroy fails | `reports/lab/sweep.json` |
| 3 | Fingerprint production | cannot read a prod state or `pct` | `reports/lab/fingerprint.before.json` |
| 4 | Derive lab tfvars from `prod.tfvars` | prod tfvars missing or invalid | `reports/lab-tfvars/` (redacted) |
| 5 | Create scratch dirs for the service's mounts | `mkdir`/`chown` fails | `reports/lab/scratch.json` |
| 6 | `terraform plan` with `-state=state/lab/<svc>/…` | plan error; any resource off `vmbr99`; guards (CT conflicts, bind-mount policy for lab, scope) deny | existing plan reports |
| 7 | Capacity check: `MemAvailable − memory ≥ 6144 MiB` | below margin (message gives both figures) | `reports/lab/capacity.json` |
| 8 | `terraform apply` → lab copy (after-apply `backup_tfstate.sh` is skipped for lab) | apply error | existing apply reports, `reports/lab/copy.json` |
| 8b | Inventory guard: every `ansible_host` in the layered lab inventory is in `10.99.0.0/24` | any host outside it | `reports/lab/inventory-guard.txt` |
| 9 | Ansible: `-i inventories/lab/hosts.yml -i inventories/generated/hosts.yml -e @inventories/lab/lab-overrides.yml -e deploy_environment=lab` | playbook fails | existing |
| 10 | Isolation probe from inside the lab copy (`pct exec`) | any production target reachable, or the internet unreachable | `reports/lab/isolation.json` |
| 11 | Health check at the lab address (`healthcheck.py`, lab profile) | unhealthy after the existing retry window | `reports/healthcheck/` |
| 12 | Teardown (`EXIT` trap; also runs after steps 6–11 fail) | destroy guard refuses; container still present afterwards | `reports/lab/teardown.json` |
| 13 | Fingerprint production again and compare | any difference | `fingerprint.after.json`, `fingerprint.diff.txt` |
| 14 | Release lock, write summary | — | `reports/apply/summary.txt` (`status=success|failed`, `reason=`) |

Steps 12–14 always run, even when an earlier step failed. The exit code is non-zero if any step
failed. `reason` names the first failure.

## `plan --environment lab`

Steps 1–7 and then 12 (the plan creates nothing, so teardown only removes the scratch dirs and the
lab state). Used by `lxc-lifecycle.yml` for its plan job.

## `--environment prod`

Plan and apply against `state/prod/<svc>`. Behaviour is unchanged apart from the state path. The
bind-mount policy still allows only `/mnt/nas/`. A plan that contains a resource on `vmbr99` is
refused.

## Refusals (stable messages, asserted by tests)

- `lab: another LAB run holds /var/lib/homelab-proxmox/state/lab/.lock`
- `lab copy needs <M> MiB; host has <A> MiB available; at least 6144 MiB must stay free`
- `refusing to destroy: lab state <path> contains a resource that is not a lab copy (<address>)`
- `bind-mount policy (lab): <volume> is not under /var/lib/homelab-proxmox/lab-scratch/`
- `production changed during LAB run; see reports/lab/fingerprint.diff.txt`
- `lab isolation broken: <ip>:<port> reachable from lab copy`
- `lab inventory resolves <host> to <ip>, outside 10.99.0.0/24`
