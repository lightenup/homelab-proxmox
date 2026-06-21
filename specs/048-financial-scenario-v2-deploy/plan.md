# Implementation Plan: Financial-Scenario v2 Deploy (Stateful)

**Branch**: `048-financial-scenario-v2-deploy` | **Date**: 2026-06-21 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/048-financial-scenario-v2-deploy/spec.md`

## Summary

Upgrade the existing financial-scenario deploy from PFS `0.1.0` (stateless 3-container stack) to
`0.2.2`, which introduces (1) a single-engine topology where `mcp` becomes a stateless HTTP client of
`api`, and (2) a persisted SQLite scenario store on `api`. The deploy must adopt the new topology,
add a durable host bind-mount for the scenario store, and add a backup role + systemd timer that
takes a consistent (WAL-safe) snapshot to the Synology NAS over an in-guest NFS mount — all without
regressing the LAN/tailnet-only posture, the GHCR pull, the GUI-only port model, the image-baked MCP
gate, or the blackbox monitoring contract.

Technical approach: bump `financial_scenario_version` to `0.2.2`; edit the compose template (remove
the `mcp` reference-data mount, add `API_BASE_URL` + `depends_on: api healthy`, add the `api`
`/app/data` bind-mount); add scenario-dir-ensure (never-seed) logic to the `financial_scenario` role;
add `features_mount = "nfs"` to the LXC module call; create a `financial_scenario_backup` role that
mounts the NAS share in-guest and runs an online-backup snapshot with GFS retention, mirroring
`nextcloud_backup`/`immich_backup`.

## Technical Context

**Language/Version**: HCL (Terraform, `telmate/proxmox`), YAML (Ansible 2.x), Jinja2, Bash (backup
script). No application code — pinned GHCR images only.
**Primary Dependencies**: `lxc_service` Terraform module; `geerlingguy.docker` + `community.docker`
Ansible collections; existing `financial_scenario` role; `nextcloud_backup`/`immich_backup` (backup
pattern), `shared_nfs_mount` + jellyfin `features_mount` (in-guest NFS pattern).
**Storage**: SQLite (WAL mode) scenario store at `/app/data/scenarios.db` inside the `api` container,
backed by a host bind-mount `{{ financial_scenario_data_dir }}/scenarios`. Backup destination =
Synology NFS `192.168.1.109:/volume1/homelab_financial_scenario`, mounted in-guest at
`/mnt/financial-scenario/backups`. Reference-data bind-mount carried over from `046`.
**Testing**: `terraform validate` + plan-only; `ansible-playbook --check` / `--syntax-check`;
`scripts/healthcheck/financial-scenario.sh`; manual restore + `sqlite3 PRAGMA integrity_check`
verification (quickstart). No new unit-test surface (declarative IaC).
**Target Platform**: Unprivileged Debian 12 LXC on Proxmox VE; prod IP `192.168.1.217`, lab
`192.168.20.218`.
**Project Type**: Infrastructure (Terraform + Ansible), single repo. No `src/`/`tests/` app layout.
**Performance Goals**: N/A beyond existing blackbox liveness (one human + a few agents).
**Constraints**: LAN/tailnet-only (no Caddy route, no landing card); single published port (GUI
`3000`); MCP gate image-baked; no PVE `/etc/fstab` edit (in-guest NFS only, Spec `023`); never clobber
an existing `scenarios.db`.
**Scale/Scope**: One service LXC; current sizing 2c/2048MB retained (D-003 — confirmed sufficient;
bump only on observed memory pressure).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Spec-Driven Workflow** — PASS. Work is driven from `specs/048-.../spec.md`; tasks will be
  enumerated in `tasks.md`. Backlog item `docs/backlog/047-...` is the originating source; the spec is
  the source of truth.
- **II. Secrets Policy** — PASS. No new secrets. GHCR pull creds already in `group_vars/services/vault.yml`;
  MCP secret stays image-baked (D-004); the NFS share uses host-based export rules (no credential).
- **III. Separation of Concerns** — PASS. Terraform owns only the LXC `features_mount = "nfs"` feature
  flag (existence/capability of the machine, applied host-side by the orchestrator via `pct set`).
  Ansible owns everything inside the guest: the in-guest NFS mount, the compose template, the
  scenario-dir creation, and the backup role/timer.
- **IV. Code Economy (YAGNI)** — PASS (with one deliberate choice, see Complexity Tracking). The
  backup destination is mounted **inside the new backup role** rather than parameterising
  `shared_nfs_mount` for rw — that role is hardcoded read-only and tied to the `SD-003` RO assertion +
  evidence pack; adding rw/RO conditional branching to satisfy a single new rw consumer is more
  indirection than inlining a one-off `ansible.builtin.mount` in the role that needs it.
- **V. Dual-Provisioning Parity** — PASS. `financial-scenario` already exists in the workflow
  dropdowns and `scripts/lab/service-scope-allowlist.json`; the new role runs through the existing
  `ansible/playbooks/financial-scenario.yml` and the TF change through the existing gated pipeline. No
  CI-only or laptop-only step is introduced.

**Result**: PASS. One justified deviation tracked below.

## Project Structure

### Documentation (this feature)

```text
specs/048-financial-scenario-v2-deploy/
├── plan.md              # This file
├── research.md          # Phase 0 — decisions (backup mechanism, mount pattern, sizing)
├── data-model.md        # Phase 1 — entities (scenario store, backup artifact)
├── quickstart.md        # Phase 1 — deploy + upgrade + backup/restore verification
├── contracts/           # Phase 1 — compose topology, systemd units, NFS + backup-archive contracts
│   ├── compose-topology.md
│   └── backup-restore.md
├── checklists/
│   └── requirements.md  # From /speckit.specify
└── tasks.md             # /speckit.tasks (NOT created here)
```

### Source Code (repository root)

```text
terraform/
└── main.tf                                   # EDIT: add features_mount = "nfs" to financial_scenario_lxc

ansible/
├── group_vars/services/vars.yml              # EDIT: bump financial_scenario_version → 0.2.2;
│                                             #       add financial_scenario_backup_* vars
├── playbooks/financial-scenario.yml          # EDIT: add financial_scenario_backup role
└── roles/
    ├── financial_scenario/
    │   ├── tasks/main.yml                     # EDIT: ensure scenarios dir (never seed DB)
    │   └── templates/docker-compose.yml.j2    # EDIT: api /app/data mount; mcp client reconfig
    └── financial_scenario_backup/            # NEW role (mirrors nextcloud_backup/immich_backup)
        ├── tasks/main.yml                     #   in-guest NFS mount + script/service/timer install
        ├── handlers/main.yml                  #   Reload systemd
        └── templates/backup_financial_scenario.sh.j2  # online SQLite snapshot + GFS prune
```

**Structure Decision**: Infrastructure project — no `src/`/`tests/` tree. Changes are localized to the
existing `terraform/main.tf`, the existing `financial_scenario` role + compose template, shared
service vars, the service playbook, and exactly one new role (`financial_scenario_backup`). New role
is justified by separation of concerns and direct precedent (`nextcloud_backup`, `immich_backup`).

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| In-guest NFS mount duplicated in `financial_scenario_backup` instead of reusing `shared_nfs_mount` | The backup destination must be **read-write**; `shared_nfs_mount` is hardcoded `ro` and asserts `SD-003` (RO) into the evidence pack. | Parameterising `shared_nfs_mount` for rw/RO would add conditional assertion + evidence branching to a role with a single existing RO consumer, increasing indirection to serve one new rw consumer. Inlining a one-off `ansible.builtin.mount` (jellyfin-style opts) in the role that needs it is less coupling. Revisit only if a 3rd rw NFS consumer appears. |
