# Data Model: Real isolated lab (067)

These are the entities from the spec's *Key Entities*, with their concrete form on the `pve` host.
Decisions are referenced as R-NNN ([research.md](./research.md)).

## Service

| Field | Source | Notes |
|---|---|---|
| `name` | `scripts/lab/service-scope-allowlist.json`, workflow dropdowns | 12 today |
| `prod_ip` | `service_ips[<name>]` in `prod.tfvars` | `192.168.1.N/24` |
| `lab_ip` | derived: `10.99.0.N/24` (R-002) | must not be `.1`, `.10`, `.11`; must be in `.200`–`.254` |
| `hostname` | `terraform/services/<name>/main.tf` | prod: as today; lab: `lab-<hostname>` (R-001) |
| `memory_mib` | the service root (`memory =`) | read from the plan JSON for the capacity check (R-007) |
| `mounts` | `service_mountpoints[<name>]` | prod: `/mnt/nas/...`; lab: scratch dir (R-005) |
| `lab_switches` | R-011 table | required when the service holds an internet credential |

## Lab copy

A `proxmox_lxc` that exists only during a LAB run.

| Field | Value |
|---|---|
| hostname | `lab-<hostname>` |
| `net0` | `bridge=vmbr99`, `ip=10.99.0.N/24`, `gw=10.99.0.1` |
| VMID | allocated by Proxmox, recorded in the lab state and in `reports/lab/copy.json` |
| storage | rootfs on `local-lvm`; bind mounts only from `lab-scratch/<run_id>/` |
| monitoring/backup | none (FR-009) |

**Identity rule (sweeper and destroy guard)**: hostname `^lab-` AND `net0` bridge `vmbr99` AND an
address in `10.99.0.200`–`10.99.0.254`. All three must hold.

**Lifecycle**:

```text
(absent) ─sweep+lock─▶ planned ─capacity ok─▶ created ─ansible─▶ configured ─isolation+health─▶ verified
    ▲                     │ capacity fail          │ fail             │ fail                     │
    └──────────── teardown (EXIT trap: destroy → pct destroy fallback → rm scratch, rm lab state) ◀┘
aborted run: copy left as-is ─▶ removed by the next run's pre-run sweep or by the nightly sweep
```

## State (per service, per environment)

| Env | Path | Lifetime | Backed up |
|---|---|---|---|
| prod | `/var/lib/homelab-proxmox/state/prod/<svc>/terraform.tfstate` | durable | yes, nightly PVE config backup |
| lab | `/var/lib/homelab-proxmox/state/lab/<svc>/terraform.tfstate` | one LAB run | no; removed in teardown |

- Owner `ci`, mode `0600`, directories `0700`.
- `state/lab/.lock` is the lab run lock (`flock`) (R-007).
- **Invariant**: a prod state never contains a resource on `vmbr99`, and a lab state never contains
  one off it. `pve-service-deploy` asserts this on every plan.
- Removed by the migration: `state/services/`, `/mnt/nas/homelab_ci/infra_state/`, the 10
  combined-root modules (R-012).

## Scratch storage

`/var/lib/homelab-proxmox/lab-scratch/<run_id>/<mount-key>/`, owner `100000:100000`, created empty
for each run and removed in teardown or by the sweep. Prefix allowlisted for lab only (R-005).

## Isolation exception

| Field | Notes |
|---|---|
| `destination` | single IP:port on a private range |
| `source` | lab-copy range or lab-rig host |
| `reason` | why the lab copy cannot work without it |

The list is in [contracts/lab-network.md](./contracts/lab-network.md). **It is empty at plan time.**

## Production fingerprint (R-009)

```json
{
  "schema_version": "1.0.0",
  "taken_at": "2026-10-30T12:00:00Z",
  "phase": "before|after",
  "states": {"ntfy": "sha256:…", "…": "…"},
  "tfvars_prod": "sha256:…",
  "containers": [
    {"vmid": 109, "hostname": "ntfy", "status": "running",
     "net": ["net0: name=eth0,bridge=vmbr0,…,ip=192.168.1.222/24"], "config_sha256": "…",
     "workload": ["<docker id> <created> ntfy"]}
  ]
}
```

`workload` is the sorted `docker ps -a --no-trunc` identity of the application containers
(`["none"]` without Docker; `["unreadable"]` if `pct exec` fails, which also fails the comparison).

Comparison: `states`, `tfvars_prod` and the `containers` set (by VMID, including `workload`) must
be equal. The
difference is written to `fingerprint.diff.txt`.

## LAB run result

These are the existing evidence pack (`service-deploy-runs/lab-<svc>-<sha>-<ts>/`) plus the new
`reports/lab/` files (see [contracts/lab-run-evidence.md](./contracts/lab-run-evidence.md)). The
run passes only if every one of these holds: capacity ok, apply ok, isolation ok, health ok,
teardown ok, fingerprint equal. Its pass or fail feeds `lab_gate_failed` in `lxc-promote-prod.yml`.

## Drift report (R-008)

`/var/lib/homelab-proxmox/artifacts/state-drift/latest.json`:

```json
{"run_at": "…", "ok": true,
 "untracked": [{"vmid": 104, "hostname": "homeassistant"}],
 "double_tracked": [{"vmid": 112, "states": ["homeassistant", "immich"]}],
 "lab_leftover": [{"vmid": 130, "hostname": "lab-ntfy", "swept": true}]}
```

The metrics are in [contracts/state-drift-metrics.md](./contracts/state-drift-metrics.md).
