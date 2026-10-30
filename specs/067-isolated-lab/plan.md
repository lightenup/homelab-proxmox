# Implementation Plan: Real isolated lab for the gated pipeline

**Branch**: `067-isolated-lab` | **Date**: 2026-10-30 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/067-isolated-lab/spec.md`

## Summary

Today the LAB stage deploys the real production container (same host, bridge, address and state),
so "LAB then PROD" is a production change followed by a no-op. This feature keeps the
`pve-service-deploy` CLI and makes `--environment lab` an **ephemeral rehearsal**. It sweeps
leftovers, fingerprints production, derives lab tfvars from prod (`vmbr99`, `10.99.0.N`, `lab-`
hostname, scratch dirs instead of NAS shares) and plans against a temporary lab state. It checks
6 GB of memory headroom, creates the lab copy, runs the normal playbook with lab address overrides
and per-service switches (no ACME/DNS, no Tailscale, no alert receivers, no backups), probes
isolation, health-checks the lab address, tears everything down and fingerprints production again.
Any difference fails the run.

An nftables table installed by root Ansible blocks `vmbr99` from every private range. State moves
in one supervised step to honest local paths, `state/{prod,lab}/<svc>`, with prod backed up
nightly. A nightly timer reports untracked, double-tracked and leftover containers as metrics on
the existing phone-alert path. The two standalone LAB workflows are removed. The lifecycle
workflow's `lab` target becomes the rehearsal (and `delete` is refused). The PROD plan shows the
real change.

## Technical Context

**Language/Version**: Bash (`pve-service-deploy` and `scripts/lab/lib/*`), HCL (Terraform ≥ 1.5.7,
`telmate/proxmox` 2.9.11), YAML (Ansible 2.19 on `pve`), Jinja2, GitHub Actions YAML, nftables,
Prometheus rule YAML; tests in Python 3.11 (pytest + PyYAML) and Bash. No new language.

**Primary Dependencies**: the existing `pve-service-deploy` and its libs (`state.sh`, `tfvars.sh`,
`ct_conflicts.sh`, `evidence.sh`), `modules/lxc_service`, the `healthcheck.py` and `node_exporter`
textfile collector, `monitoring_stack` (`backup_alerts.yml.j2`), `proxmox_backup`, and
`lab_setup.yml` (`vmbr99`).

**Storage**: Terraform state as local files on `pve`: `/var/lib/homelab-proxmox/state/prod/<svc>`
(durable, in the nightly PVE config backup) and `state/lab/<svc>` (one run only). Scratch dirs
are under `/var/lib/homelab-proxmox/lab-scratch/<run_id>/`. The NAS `infra_state` tree is retired.

**Testing**: pytest guardrails (`python/tests/guardrails/`) for templates, workflows, removed
references, lab overrides coverage and lab switches. Bash unit tests in the existing style for the
lib functions (fingerprint diff, lab-copy identity rule, tfvars mirroring, capacity math), using fake
`pct`/`/proc/meminfo` fixtures. `act -l` / `act -n` for workflows. End-to-end runs per
[quickstart.md](./quickstart.md). Mutation gate (`task mutmut:gate`) for any Python touched.

**Target Platform**: the single Proxmox VE host `pve` (Debian 12 based), with the self-hosted runner
reaching it as `ci`; the developer laptop over SSH (constitution V).

**Project Type**: infrastructure-as-code repository (deploy orchestrator, Terraform roots, Ansible
roles, CI workflows).

**Performance Goals**: a LAB run adds at most the fresh-deploy cost. That is about 100 s for the
LXC, plus the image pull at about 27 MB/s, plus teardown of about 20 s. Worst case hermes is about
15 minutes (SC-004). The nightly check finishes in under 1 minute.

**Constraints**: production must not change during a LAB run (FR-021, proved per run). At most one
lab copy, and ≥ 6 GB host `MemAvailable` must remain (FR-004). `ci` has no sudo for `nft`, so the
isolation rules are root-Ansible only. Single runner: mutation jobs and promotions serialise.
Prod secrets are used in lab (FR-010), so the internet-facing switches are mandatory (FR-011).

**Scale/Scope**: 12 services, 12 prod states, 1 host, 1 lab copy at a time. About 15 files changed
in `scripts/lab/`, 12 service roots (one variable each), about 8 Ansible roles/playbooks,
4 workflows (2 deleted) and the docs.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Assessment | Status |
|---|---|---|
| I. Spec-Driven Workflow | spec, clarifications, plan; `tasks.md` follows. Docs updated in the same changes (FR-018) | ✅ |
| II. Secrets Policy | no secrets committed. The lab tfvars are derived at runtime into a 0600 temp file, and only a redacted copy goes to evidence (as `lib/tfvars.sh` does today). Prod secrets in lab are an owner decision (FR-010), limited by FR-011 and R-004 | ✅ |
| III. Separation of Concerns | Terraform: lab copy existence (same roots, lab tfvars). Ansible: config in copies, nftables and the timer on the host. The orchestrator only sequences them and runs Tier-2 `pct` for teardown fallback, scratch dirs and probes | ✅ |
| IV. Code Economy | No new module or role. One new variable per root (`hostname_prefix`, two consumers: lab and prod). New files only where separation needs them: `lib/fingerprint.sh`, `state-drift-check`, a one-off `migrate-state-067` deleted after use, and `lab-overrides.yml`. Removes 2 workflows, 3 lab tfvars files, `USE_NAS_STATE` and the NAS state tree, `migrate-state-to-nas.sh` and 10 combined-root modules. Net code should shrink | ✅ |
| V. Dual-Provisioning Parity | the lab path stays in `pve-service-deploy`, with the same CLI from the laptop over SSH. Host-only pieces (nftables, timer) are documented with the laptop equivalent (R-014) | ✅ |
| Token tiers | Tier 1 for Terraform plan, apply and destroy. Tier 2 (`sudo pct`, `mkdir`, `chown`) for scratch dirs, teardown fallback and probes. Tier 3 unused | ✅ |
| Tier-2 enforcement text ("rejects host paths outside `/mnt/nas/`") | lab uses a **narrower** rule: only `lab-scratch/`, and `/mnt/nas/` denied. The text is amended in Phase 2 (before the lab path's code) → Complexity Tracking | ⚠️ justified, amended first |
| State Management (local on PVE, backed up to Synology) | today's layout breaks it (5 states on the NAS). After migration it complies fully | ✅ (improves) |
| CI/CD: no destructive automation without barriers | automatic teardown destroys containers. Barriers: the destroy guard (lab state may only hold `lab-*` on `vmbr99` in `10.99.0.200–254`), the three-attribute sweep rule, `pct` only (never `qm`), and the fingerprint proving production unchanged | ✅ |
| Networking: IPs defined centrally | lab IPs are derived from `service_ips` by rule, not written out. `lab-overrides.yml` repeats the `*_ip` keys with lab values, and a test enforces full coverage | ✅ |
| Local workflow testing (`act`) | required for the 3 changed workflows | ✅ planned |

**Gate result**: PASS, with one justified amendment (below). Re-checked after Phase 1 design: no
change. The contracts add no module, role or new privilege.

## Project Structure

### Documentation (this feature)

```text
specs/067-isolated-lab/
├── spec.md
├── plan.md                    # this file
├── research.md                # R-001 … R-015
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── pve-service-deploy-lab.md
│   ├── lab-network.md
│   ├── state-drift-metrics.md
│   └── lab-run-evidence.md
├── checklists/requirements.md
└── tasks.md                   # /speckit-tasks
```

### Source Code (repository root)

```text
scripts/lab/                               # protected path → label allow-protected-path-changes
├── pve-service-deploy                     # lab path: lock, sweep, fingerprint, capacity, isolation probe, teardown trap;
│                                          #   env-aware bind-mount policy; vmbr99 invariant on plans
├── lib/state.sh                           # state/<env>/<svc>; USE_NAS_STATE + legacy root removed
├── lib/tfvars.sh                          # derive lab tfvars from prod.tfvars (mirror IPs, vmbr99, prefix, scratch mounts)
├── lib/fingerprint.sh                     # NEW: prod_fingerprint, fingerprint_diff
├── lib/ct_conflicts.sh                    # reused (ct_inventory); lab-copy identity helper added
├── state-drift-check                      # NEW: nightly check + textfile metrics
├── state-drift-ignore.txt                 # NEW: empty at ship
├── migrate-state-067                      # NEW, one-off; deleted in the clean-up change
├── migrate-state-to-nas.sh                # DELETED
└── validate-existing-state.sh, guardrails.sh, lib/rebuild.sh   # drop USE_NAS_STATE

terraform/
├── services/<12>/main.tf, variables.tf    # hostname = "${var.hostname_prefix}<name>"
├── main.tf                                # 10 obsolete module blocks removed (state rm, no destroy)
└── environments/lab.tfvars.{template,example}   # DELETED (derived at runtime)

ansible/
├── inventories/lab/hosts.yml              # + 12 services at 10.99.0.N under `services`
├── inventories/lab/lab-overrides.yml      # NEW: deploy_environment + every *_ip → lab
├── playbooks/lab_setup.yml                # + nftables table lab_isolation (tag lab-network)
├── playbooks/host_proxmox.yml             # + state-drift timer (tag state-drift)
├── playbooks/{6 with service_backup}.yml  # service_backup skipped when deploy_environment == lab
├── roles/reverse_proxy/                   # lab: local_certs, no acme_dns, no domeneshop.env
├── roles/llm_router/                      # lab: no tailscale sidecar
├── roles/monitoring_stack/templates/      # alertmanager lab: null receiver only;
│                                          #   backup_alerts.yml.j2 + StateDrift* rules
└── roles/proxmox_backup/                  # collect state/prod; NAS infra_state collector removed

.github/workflows/
├── lxc-promote-prod.yml                   # "LAB rehearsal (isolated)", 90-min timeout, gate wording
├── lxc-lifecycle.yml                      # lab: add/change → rehearsal; delete refused
├── lxc-deploy-lab.yml                     # DELETED
└── lxc-promote-lab.yml                    # DELETED

python/tests/guardrails/                   # new: removed-workflow refs, lab overrides coverage,
                                           #   lab switches for internet credentials, StateDrift rules,
                                           #   lab_isolation template, vmbr99 invariant
docs/, README.md, AGENTS.md, docs/runbooks/   # LAB = isolated rehearsal; 2026-10-28 warnings replaced
.specify/memory/constitution.md            # one-line Tier-2 enforcement amendment (protected path)
```

**Structure Decision**: Extend the existing orchestrator and roles in place. There is no new
service, module or role. The only new executables are the drift check, the fingerprint lib and the
one-off migration, each required by a single FR (FR-014, FR-021, FR-013).

## Delivery slices (input to `/speckit-tasks`)

Ordered so that production is never in a half-migrated state:

1. **Isolation first** (no behaviour change): nftables table, isolation probe, lab-rig check (R-004),
   and the constitution's Tier-2 enforcement amendment. The amendment lands before any code
   allows a lab bind-mount prefix (analysis D1).
2. **State migration** (supervised, one session): new `state.sh` layout, `migrate-state-067`, backup
   paths, combined-root clean-up (R-003, R-012). The pipeline still deploys prod as before, now
   from `state/prod`.
3. **Ephemeral lab path**: `hostname_prefix`, lab tfvars derivation, scratch mounts, bind-mount
   policy, lock and sweep, capacity, fingerprint, Ansible overrides, FR-011 switches,
   `service_backup` gate, teardown (R-001/2/5/6/7/9/10/11).
4. **Pipeline**: `lxc-promote-prod` wording and timeout, lifecycle lab target, delete the two
   workflows and their references (R-013).
5. **Drift check**: script, timer, metrics, alerts (R-008).
6. **Docs and clean-up**: runbooks, AGENTS/README, delete
   `migrate-state-067`.

Every slice touching `scripts/lab/**` or `.specify/**` needs the `allow-protected-path-changes`
label at PR creation, with the operator's approval.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| Constitution Tier-2 enforcement text names only `/mnt/nas/` as the allowed bind-mount prefix | lab copies need empty scratch dirs instead of NAS shares (FR-006). The lab rule is stricter: only `lab-scratch/` is allowed, and `/mnt/nas/` is denied | Using a NAS share for lab scratch breaks FR-006 (lab must not touch any NAS share). Skipping mounts in lab breaks the roles' mount-present checks and differs from production |
