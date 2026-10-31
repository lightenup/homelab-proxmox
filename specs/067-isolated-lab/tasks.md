# Tasks: Real isolated lab for the gated pipeline

**Input**: Design documents from `specs/067-isolated-lab/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md),
[data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)

**Tests**: Included. The constitution's *Test-Driven Changes* requires validation for new
functionality, and the plan names the guardrail and Bash-lib tests. Each test task comes before
the code it covers and must fail first.

**Organization**: Grouped by user story. **US2 (state) runs before US1 (lab copies)**. Both are
P1, and the spec says the lab "cannot exist while lab and production share one state".

**Protected paths**: every PR that touches `scripts/lab/**` or `.specify/**` needs the
`allow-protected-path-changes` label at creation, approved by the operator.

**Production safety rules for the implementer**:

- Never run `--environment lab` with the *old* code after the `vmbr99` changes. Never run `prod`
  with the *new* `state.sh` before T021 has migrated the states. The duplicate-CT guard would
  stop it, but don't rely on that.
- Never `terraform destroy` against `state/prod`. Removing combined-root resources is `state rm`
  only.
- Root-on-`pve` Ansible is run **by the operator** (`ci` has no `nft` sudo). Hand them the exact
  command.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US1–US4 from spec.md

---

## Phase 1: Setup

**Purpose**: Confirm the facts the plan left open, before any change.

- [X] T001 Locate the combined-root Terraform state for `terraform/main.tf`: check `proxmox-apply.yml`, `scripts/backup_tfstate.sh`, `/var/lib/homelab-proxmox/state*` and `/mnt/nas/homelab_ci/` on `pve` (read-only, via `ssh pve`). List its resources with `terraform state list -state=<path>`. Record the path and the 10 `module.*_lxc` addresses in `specs/067-isolated-lab/research.md` under R-012 (replace "confirmed at the start of implementation").
- [X] T002 [P] Check that the lab-rig VMs (`.10`, `.11` on `vmbr99`) need no LAN destination: read `.github/workflows/lab-rig.yml`, `ansible/playbooks/lab_setup.yml`, `lab_tier2_pve.yml`, `lab_bootstrap.yml` and `hermes_lab_rig.yml`, and list every `192.168.*`/LAN host they contact. Record the result in R-004 of `specs/067-isolated-lab/research.md`. If any is needed, add a source-scoped row (`10.99.0.10`, `10.99.0.11` only) to the exception table in `specs/067-isolated-lab/contracts/lab-network.md`.
- [X] T003 [P] Inventory every reference to `lxc-deploy-lab`, `lxc-promote-lab`, `USE_NAS_STATE`, `infra_state`, `state/services`, `lab.tfvars` and "changes prod" outside `specs/` (`grep -rn` across `.github/ scripts/ ansible/ python/ docs/ README.md AGENTS.md CLAUDE.md`). Save the list to `specs/067-isolated-lab/refs-to-remove.txt`. It is the checklist for T057 and T062, and is deleted in T066.

---

## Phase 2: Foundational (blocking)

**Purpose**: The isolation boundary and the lab-copy identity. Neither changes production behaviour.

**⚠️ CRITICAL**: US1 cannot start until this phase is done and the operator has applied T007.

- [X] T004 [P] Write `python/tests/guardrails/test_lab_isolation.py`. It asserts that the rendered `ansible/playbooks/templates/lab-isolation.nft.j2` (or wherever T005 puts it) defines `table inet lab_isolation` with the forward chain `iifname "vmbr99" ct state established,related accept`, `ip daddr 10.99.0.0/24 accept`, and `ip daddr @lan_private drop`, where `lan_private` = `{ 10.0.0.0/8, 100.64.0.0/10, 172.16.0.0/12, 192.168.0.0/16 }`, and the input chain `iifname "vmbr99"` established-accept, then drop. It also asserts that the `vmbr99` stanza loads it on `post-up` and deletes it on `post-down`. It must fail now.
- [X] T005 Add the nftables table to `ansible/playbooks/lab_setup.yml` (the `LAB NETWORK` block, new tag `lab-network`). Render `/etc/nftables.d/lab-isolation.nft` from a template beside the playbook, exactly per `contracts/lab-network.md`. Add `post-up nft -f /etc/nftables.d/lab-isolation.nft` and `post-down nft delete table inet lab_isolation` to the `vmbr99` stanza. If the table is already loaded, load it idempotently (`nft -f` after `nft delete table … || true`). T004 passes.
- [X] T006 [P] Write `python/tests/guardrails/test_lab_identity.py` for the new helper `is_lab_copy` (T008), driving it with fake `sudo`/`pct` the way `test_ct_conflict_guard.py` does. It is true only when hostname `^lab-`, **and** `net0` `bridge=vmbr99`, **and** IP in `10.99.0.200`–`10.99.0.254` all hold. Cases: `lab-ntfy`/`vmbr99`/`.222` → true; `lab-ntfy`/`vmbr0` → false; `ntfy`/`vmbr99`/`.222` → false; `lab-x`/`vmbr99`/`.10` → false. It must fail now.
- [X] T007 Hand the operator the command `cd ansible && ansible-playbook playbooks/lab_setup.yml -i inventories/prod/hosts.yml --tags lab-network -k` (root password SSH to `pve`). Then verify read-only with `ssh pve 'sudo -n nft list table inet lab_isolation'`. If `ci` can't run that, ask the operator to paste the output. Record it in `specs/067-isolated-lab/quickstart.md` §3 as the first observed run.
- [X] T008 Add `is_lab_copy <vmid>` and `list_lab_copies` (prints `<vmid>\t<hostname>\t<ip>` for every match) to `scripts/lab/lib/ct_conflicts.sh`, reusing `ct_inventory` and adding the bridge from the `net0` line. T006 passes.
- [X] T009 [P] Add `variable "hostname_prefix" { type = string, default = "" }` to each `terraform/services/<svc>/variables.tf` (12 services), and change `hostname = "<name>"` to `hostname = "${var.hostname_prefix}<name>"` in each `terraform/services/<svc>/main.tf`. Keep `reverse_proxy` as `"${var.hostname_prefix}proxy"`. `terraform validate` per root. A prod plan must stay `No changes` (prefix empty). Check that later in T021.

- [X] T010 Amend `.specify/memory/constitution.md` Token Privilege Tiers → *Enforcement*: the orchestrator bind-mount allowlist rejects host paths outside `/mnt/nas/` for prod, and for lab allows only `/var/lib/homelab-proxmox/lab-scratch/` and rejects `/mnt/nas/` (067). Bump the constitution version per its Governance section. This is a protected path, so the label needs approval. It lands in PR A, before any code allows a lab bind-mount prefix (analysis D1), as a separate, explicit constitution update.

**Checkpoint**: The isolation is live on `pve`, the lab-copy identity is testable, the roots accept a prefix, and the constitution allows the lab scratch prefix.

---

## Phase 3: User Story 2 — Lab and production each have their own state (Priority: P1)

**Goal**: One honest, local, backed-up production state per service; a lab state root that exists
only during runs; the old layout gone the same day; a nightly report of untracked containers.

**Independent Test**: [quickstart.md](./quickstart.md) §M and §6. All 12 services show
`No changes` against `state/prod`. `state/services` and `infra_state` are gone. The backup
manifest lists 12 prod states. A deliberately untracked CT appears in `latest.json` and fires
`StateDriftContainers`.

### Tests for User Story 2

- [X] T011 [P] [US2] Write `python/tests/guardrails/test_state_layout.py`. Sourcing `scripts/lab/lib/state.sh` with `STATE_ROOT=<tmp>`: `resolve_state_root prod` → `<tmp>/prod`; `get_service_state_path lab ntfy` → `<tmp>/lab/ntfy/terraform.tfstate`; an unknown env fails. A repo grep of `scripts/ ansible/ .github/` finds no `USE_NAS_STATE`, no `infra_state` and no `state/services`. It must fail now.
- [X] T012 [P] [US2] Extend `python/tests/guardrails/test_pve_backup_local_state.py`. The backup collects `state/prod/<svc>/terraform.tfstate`, it does **not** collect `state/lab/`, and the NAS `infra_state` collector is gone. Replace `test_copies_plain_state_dirs_and_skips_nas_symlinks` with a test of the new layout. It must fail now.
- [X] T013 [P] [US2] Write `python/tests/guardrails/test_migrate_state_067.py`. It drives `scripts/lab/migrate-state-067` with a fake tree: 7 dirs and 5 symlinks into a fake `infra_state/lab`, and a fake `pve-service-deploy` that exits 0 (`No changes`) or 2. It asserts: dated copies are made first, symlinks are resolved, the script stops at the first service whose plan exits ≠ 0, services already done stay in `state/prod`, the old layout is removed only after 12/12, and `--dry-run` changes nothing. It must fail now.

### Implementation for User Story 2

- [X] T014 [US2] Rewrite `scripts/lab/lib/state.sh`. `resolve_state_root <env>` → `${STATE_ROOT:-/var/lib/homelab-proxmox/state}/<env>` for `lab|prod` only. Remove the `USE_NAS_STATE` branch and the legacy root. Keep `get_service_state_path` and `verify_state_access`, and make `get_inventory_path` local. T011 passes (lib part).
- [X] T015 [US2] In `scripts/lab/pve-service-deploy` `ensure_state_path`, use `get_service_state_path "${ENVIRONMENT}" "${SERVICE}"`. Remove `STATE_PATH_DEFAULT_ROOT` and the `state/services` default. Keep `SEED_STATE_FROM_REPO` prod-only. Create the directory as `0700` `ci`.
- [X] T016 [P] [US2] Remove `USE_NAS_STATE`/`infra_state` handling from `scripts/lab/validate-existing-state.sh`, `scripts/lab/guardrails.sh` and `scripts/lab/lib/rebuild.sh`, pointing each at `state/prod/<svc>`. Delete `scripts/lab/migrate-state-to-nas.sh`.
- [X] T017 [P] [US2] Repurpose `ansible/roles/proxmox_state_dirs/tasks/main.yml` to create `/var/lib/homelab-proxmox/state/{prod,lab}` (`0700`, `ci`) and `/var/lib/homelab-proxmox/lab-scratch` (`0711`, owned by `ci` since PR C: `ci` has no sudo `rm`, so the sweep does `sudo chown -R` then `rm -rf`), with no NAS paths. Delete `ansible/roles/proxmox_state_symlinks/` and `ansible/playbooks/setup-state-symlinks.yml`. Update `ansible/playbooks/setup-state-dirs.yml` if its comments name the NAS.
- [X] T018 [US2] In `ansible/roles/proxmox_backup/defaults/main.yml`, set `proxmox_backup_local_state_root` to `/var/lib/homelab-proxmox/state/prod`. In `templates/proxmox-config-backup.sh.j2`, remove the NAS `infra_state` collector (around line 185) and the symlink-skipping branch, and collect `${LOCAL_STATE_ROOT}/*/terraform.tfstate*` through the existing secret scan. T012 passes.
- [X] T019 [US2] Write `scripts/lab/migrate-state-067` (Bash, `set -euo pipefail`, run as `ci` on `pve`, `--dry-run` flag) per R-012:
  - Order: ntfy, market-model, financial-scenario, eurooffice, llm-router, jellyfin, homeassistant, nextcloud, immich, hermes, monitoring, reverse_proxy.
  - For each service:
    1. `cp -L` the old state into `/var/lib/homelab-proxmox/state-backup-067-$(date +%Y%m%d)/<svc>/`.
    2. Install it into `state/prod/<svc>/terraform.tfstate` (`0600`).
    3. Run `pve-service-deploy plan --environment prod --service <svc>` (credentials from the caller's env, as the workflow passes them).
    4. Require exit 0 and `No changes`; stop otherwise.
  - After 12/12: remove `state/services/`, `/mnt/nas/homelab_ci/infra_state/lab` and `/mnt/nas/homelab_ci/infra_state/prod` (`rm -rf` only after printing the list and requiring the `--remove-old-layout` flag).
  - Print a summary line `12/12 No changes`.

  T013 passes.
- [X] T020 [US2] Remove the 10 `module "*_lxc"` blocks (and their now-unused variables or outputs) from `terraform/main.tf` and the related files in `terraform/`. (Dropped the `--remove-combined-root-modules` state-rm step: T001 found no combined-root state, so there is nothing to remove.) `terraform validate` in `terraform/`.
- [X] T021 [US2] **Supervised migration session (operator present; pause promotions and confirm no mutation job holds the runner)**:
  1. Merge the US2 PR. The pipeline must not run until step 4.
  2. Have the operator run `ansible-playbook playbooks/setup-state-dirs.yml` and `playbooks/backup_proxmox.yml` (root).
  3. On `pve` as `ci`, run `./migrate-state-067 --dry-run`, then `./migrate-state-067`, then `--remove-old-layout`, then `--remove-combined-root-modules`.
  4. Trigger `proxmox-config-backup.service` and check that the manifest lists `state/prod/<svc>` ×12.

  Record the outputs in `specs/067-isolated-lab/quickstart.md` §M (observed run, date).
- [X] T022 [P] [US2] Write `python/tests/guardrails/test_state_drift.py` for `scripts/lab/state-drift-check`, with fake `pct`, a fake `state/prod` and a temp textfile dir. Cases:
  - a CT in no state → `homelab_state_drift_containers{kind="untracked"} 1` and its VMID/hostname in `latest.json`;
  - a VMID in two states → `double_tracked` 1;
  - a lab copy (identity rule) → swept and `lab_leftover` 1;
  - an ignore-list entry → not counted;
  - the lock held → exit 0 and the timestamp unchanged;
  - the textfile written atomically (temp + rename).

  The metric names are exactly `homelab_state_drift_containers` (labels `kind` = `untracked` | `double_tracked` | `lab_leftover`) and `homelab_state_drift_last_success_timestamp_seconds`. It must fail now.
- [X] T023 [US2] Write `scripts/lab/state-drift-check` per `contracts/state-drift-metrics.md`:
  - take a non-blocking `flock` on `state/lab/.lock`;
  - sweep lab copies with `list_lab_copies` + `pct stop`/`pct destroy`, and remove stale `lab-scratch/*` and `state/lab/*/`;
  - read `vmid` from every `proxmox_lxc` in `state/prod/*/terraform.tfstate` with `jq`;
  - compare with `ct_inventory`, skipping VMIDs in `scripts/lab/state-drift-ignore.txt`;
  - write `/var/lib/homelab-proxmox/artifacts/state-drift/latest.json` and `${TEXTFILE_DIR:-/var/lib/node_exporter/textfile_collector}/state_drift.prom`.

  Create an empty `scripts/lab/state-drift-ignore.txt` with a header comment (`<vmid> <reason>`). T022 passes.
- [X] T024 [US2] Add the systemd units `state-drift-check.service` (User=`ci`, `ExecStart=/home/ci/homelab-proxmox/scripts/lab/state-drift-check`) and `state-drift-check.timer` (`OnCalendar=*-*-* 06:30:00`, `Persistent=true`) to the role that owns host units for `pve` (`ansible/roles/proxmox_host`, tag `state-drift`). Wire it into `ansible/playbooks/host_proxmox.yml`. Make sure `ci` can write the textfile (group or ACL on `node_exporter_textfile_directory`).
- [X] T025 [P] [US2] Extend `python/tests/guardrails/test_alerting_path.py` (or the test that covers `backup_alerts.yml.j2`) to assert `StateDriftContainers` (`max by (kind) (homelab_state_drift_containers) > 0`, for 0m), `StateDriftCheckStale` (`time() - homelab_state_drift_last_success_timestamp_seconds > 26 * 3600`, for 15m) and `StateDriftCheckAbsent` (`absent(...)`, for 26h), all with the same severity/receiver labels as the backup-staleness alerts and present only when `deploy_environment != 'lab'`. It must fail now.
- [X] T026 [US2] Add the three rules to `ansible/roles/monitoring_stack/templates/backup_alerts.yml.j2`, with annotations pointing to `journalctl -u state-drift-check` and `latest.json`. T025 passes. Run `promtool check rules` through the existing `validate_alerts.yml` path.
- [X] T027 [US2] After the merge: the operator applies `host_proxmox.yml --tags state-drift`. Promote `monitoring` with the new rules (an explicit operator "promote monitoring to prod"). Run `sudo systemctl start state-drift-check.service` and check `latest.json` has empty lists. Do the negative test from quickstart §6 (a `drift-test` CT on `vmbr99`, no `lab-` prefix), check that the alert fires, then destroy it. Record the results in quickstart §6.

**Checkpoint**: Production state is honest, local and backed up; the drift alert works. US1 can begin.

---

## Phase 4: User Story 1 — A LAB run rehearses a deploy without touching production (Priority: P1) 🎯 MVP

**Goal**: `pve-service-deploy apply --environment lab` creates, configures, checks and destroys a
lab copy on `vmbr99` and proves production is unchanged ([contract](./contracts/pve-service-deploy-lab.md)).

**Independent Test**: [quickstart.md](./quickstart.md) §1–§3 for `ntfy`, then `hermes`,
`reverse_proxy`, `monitoring` and `immich`.

### Tests for User Story 1

- [X] T028 [P] [US1] Write `python/tests/guardrails/test_lab_tfvars.py` for the new `_tfvars_derive_lab <prod.tfvars> <out> <scratch_root>` in `scripts/lab/lib/tfvars.sh`. Given the real `terraform/environments/prod.tfvars.template`, the output has:
  - `services_bridge = "vmbr99"`, `network_gateway = "10.99.0.1"`, `hostname_prefix = "lab-"`;
  - every `service_ips` value `192.168.1.N/24` → `10.99.0.N/24`;
  - every `service_mountpoints.*.*.volume` under `<scratch_root>/`, with `readonly` kept;
  - token/secret placeholders carried over unchanged.

  It fails when any mirrored N is `1`, `10`, `11` or outside `200–254`. It must fail now.
- [X] T029 [P] [US1] Write `python/tests/guardrails/test_prod_fingerprint.py` for `scripts/lab/lib/fingerprint.sh`, with fake `pct` and a fake `state/prod`:
  - `prod_fingerprint` excludes lab copies (identity rule) and strips `lock:`;
  - `fingerprint_diff` reports a changed state checksum, a changed `net0`, a new or missing VMID and a status change;
  - a changed workload identity (a different `docker ps -a --no-trunc` ID or created time inside a prod container) is reported, and a `pct exec` failure records `unreadable` and fails the comparison;
  - identical inputs → exit 0 and no diff file.

  The JSON matches data-model *Production fingerprint* (`schema_version`, `phase`, `states`, `tfvars_prod`, `containers[]` with `workload`). It must fail now.
- [X] T030 [P] [US1] Write `python/tests/guardrails/test_lab_capacity_and_policy.py`:
  - the capacity check refuses when `MemAvailable − memory < 6144 MiB`, with the message `lab copy needs <M> MiB; host has <A> MiB available; at least 6144 MiB must stay free` (fake `/proc/meminfo` via `MEMINFO_PATH`, plan JSON fixture);
  - the bind-mount policy for `lab` denies any `/mnt/nas/` volume and allows only `/var/lib/homelab-proxmox/lab-scratch/`, while `prod` keeps `/mnt/nas/` only;
  - a lab plan with a `proxmox_lxc` off `vmbr99` is refused, and a prod plan with one on `vmbr99` is refused;
  - the destroy guard refuses a lab state that holds a non-lab-copy resource (`refusing to destroy: lab state <path> contains a resource that is not a lab copy (<address>)`).

  It must fail now.
- [X] T031 [P] [US1] Write `python/tests/guardrails/test_lab_overrides.py`:
  - every `<svc>_ip`, `monitoring_host_ip` and `reverse_proxy_ip` key in `ansible/group_vars/services/vars.yml` and `group_vars/all/vars.yml` has an entry in `ansible/inventories/lab/lab-overrides.yml` whose value is `10.99.0.<same last octet>`;
  - `deploy_environment: lab` is set;
  - `ansible/inventories/lab/hosts.yml` lists all 12 services under `services` at the same lab addresses and keeps `lab_inventory: true`.

  It must fail now.
- [X] T032 [P] [US1] Write `python/tests/guardrails/test_lab_switches.py`. First classify **every** vault key matching `*_token`, `*_key`, `*_secret`, `*_password` or `*_api_*` (from `ansible/group_vars/*/vault.yml`, read with the vault password, names only, never values) as `internet`, `lan` or `internal`. Keep the classification as a dict in the test, and fail on any unclassified key so new keys must be classified. Record the `internet` keys in research R-011 (analysis C3). Known so far: `domeneshop_*`, `tailscale_*`, `pushover_*`, `smtp_*`/`alertmanager_smtp_*`, provider API keys in `llm_router`. For every `internet` key, every template under `ansible/roles/**/templates` that references one must sit inside a `deploy_environment` gate or be listed in an allowlist in the test that cites R-011. It also asserts:
  - the reverse proxy in lab renders `local_certs` and no `acme_dns`;
  - llm-router compose in lab has no `tailscale` service;
  - Alertmanager in lab has only the `null` receiver;
  - the 6 playbooks with `service_backup` skip it when `deploy_environment == 'lab'`.

  It must fail now.
- [X] T033 [P] [US1] Write `python/tests/guardrails/test_lab_run_contract.py`. It drives `pve-service-deploy apply --environment lab` in a fake harness (stub `terraform`, `ansible-playbook`, `pct`, `healthcheck.py`; `STATE_ROOT`/`ARTIFACT_ROOT` in tmp) and asserts the step order from the contract. Failure injection at the plan, apply, Ansible, isolation and health steps all still produce `teardown.json` with `ok`, `fingerprint.after.json` and `summary.txt` `status=failed` with the right `reason=`. The lock held → refusal message. A layered lab inventory with any `ansible_host` outside `10.99.0.0/24` → refusal `lab inventory resolves <host> to <ip>, outside 10.99.0.0/24`, before any play runs. `backup_tfstate.sh` is never called for lab, and is still called for prod. It must fail now.

### Implementation for User Story 1

- [X] T034 [US1] Implement `_tfvars_derive_lab` in `scripts/lab/lib/tfvars.sh` (Python helper inline, as the file already does). It writes the derived file `0600` to a temp path and a redacted copy to `reports/lab-tfvars/`, reusing the existing redaction and proof writer. T028 passes.
- [X] T035 [US1] In `scripts/lab/pve-service-deploy` `resolve_tfvars_path`/`_tfvars_provision_and_write_proof`, make `lab` derive from `${TFVARS_DIR}/prod.tfvars` via T034 instead of reading `lab.tfvars`. Delete `terraform/environments/lab.tfvars.template` and `lab.tfvars.example`. Update `scripts/lab/lib/tfvars.sh` comments, and any test fixture that reads them.
- [X] T036 [US1] Create `scripts/lab/lib/fingerprint.sh` with `prod_fingerprint <out.json> <phase>` and `fingerprint_diff <before> <after> <diff.txt>` per R-009 and data-model. Use `list_lab_copies` to exclude lab copies, and `sha256sum` for the states, `prod.tfvars` and `pct config` without `lock:`. Add the workload identity per running prod container: `sudo pct exec <vmid> -- docker ps -a --no-trunc --format '{{.ID}} {{.CreatedAt}} {{.Names}}'`, sorted; `none` without Docker; `unreadable` on failure (R-009, SC-001). T029 passes.
- [X] T037 [US1] In `scripts/lab/pve-service-deploy`, add the lab run lock (`flock -n` on `state/lab/.lock`, fd held for the run, refusal message per contract) and the pre-run sweep (`list_lab_copies` → `pct stop`/`pct destroy`; remove `lab-scratch/*` and `state/lab/*/`; write `reports/lab/sweep.json`). Both run only for `ENVIRONMENT=lab`.
- [X] T038 [US1] In `scripts/lab/pve-service-deploy`, add scratch-dir creation for lab: for each mount key of the service in the derived tfvars, `sudo mkdir -p` and `sudo chown 100000:100000` under `/var/lib/homelab-proxmox/lab-scratch/<RUN_ID>/<key>`, and write `reports/lab/scratch.json`. Make `enforce_bind_mount_policy` and `validate_bind_mount_allowlist` environment-aware: lab allows only `/var/lib/homelab-proxmox/lab-scratch/` and denies `/mnt/nas/`; prod keeps `/mnt/nas/`. Check that `apply_host_path_bind_mounts` works with the scratch paths. **Depends on T010** (the constitution amendment must be merged first).
- [X] T039 [US1] In `scripts/lab/pve-service-deploy` `cmd_plan`, add the `vmbr99` invariant: a lab plan with any `proxmox_lxc` whose `network[].bridge != "vmbr99"` is refused, and a prod plan with any on `vmbr99` is refused. After the plan, run the capacity check (`MemAvailable` from `${MEMINFO_PATH:-/proc/meminfo}`, `memory` from the plan JSON, margin `${LAB_MEMORY_MARGIN_MIB:-6144}`), writing `reports/lab/capacity.json` `{mem_available_mib, copy_memory_mib, margin_mib, ok}`. T030 passes (policy, capacity and invariant parts).
- [X] T040 [US1] In `scripts/lab/pve-service-deploy` `cmd_apply`, add the teardown `EXIT`/`TERM` trap for lab:
- [X] T041 [US1] In `scripts/lab/pve-service-deploy` (around line 1487–1500), skip the after-apply `scripts/backup_tfstate.sh` call for `ENVIRONMENT=lab` (log `state backup: skipped (lab state is temporary, FR-012)` to `reports/apply/state-backup.txt`). Keep it mandatory for prod, now pointing at `state/prod/<svc>` (constitution State Management; research R-003, analysis C2).
  1. the destroy guard (every `proxmox_lxc` in the lab state passes `is_lab_copy` attributes, else the refusal message);
  2. `terraform destroy -auto-approve -state=<lab state>` with the derived tfvars;
  3. fallback `pct stop`/`pct destroy <vmid>`;
  4. `rm -rf` the run's scratch dir and `state/lab/<svc>`;
  5. `reports/lab/teardown.json` `{destroyed_by, vmid, scratch_removed, lab_state_removed, ok}`.

  Write `reports/lab/copy.json` after the apply. The trap also runs on early failures. T030 (destroy guard) passes.
- [X] T042 [US1] Wire the fingerprint into `scripts/lab/pve-service-deploy` for lab: `fingerprint.before.json` after the sweep and before the plan; `fingerprint.after.json` after teardown, inside the trap; a difference → `fingerprint.diff.txt`, `summary.txt` `status=failed reason=fingerprint`, non-zero exit, message `production changed during LAB run; see reports/lab/fingerprint.diff.txt`.
- [X] T043 [US1] Add the isolation probe step to `scripts/lab/pve-service-deploy` after Ansible. Run `sudo pct exec <vmid> -- timeout 3 bash -c '</dev/tcp/<host>/<port>'` against every target in `contracts/lab-network.md` (expected: unreachable for LAN, reachable for `deb.debian.org:443`), write `reports/lab/isolation.json` (`target`, `expected`, `observed`, `ok`), and fail with `lab isolation broken: <ip>:<port> reachable from lab copy`.
- [X] T044 [P] [US1] Create `ansible/inventories/lab/lab-overrides.yml`: `deploy_environment: lab`, every `<svc>_ip`, `monitoring_host_ip` and `reverse_proxy_ip` → `10.99.0.<N>`, with a header citing R-010. Add the 12 services under `services` in `ansible/inventories/lab/hosts.yml` at `10.99.0.<N>` with `ansible_user: root`, keeping the `lab` (lab-rig) group unchanged. T031 passes.
- [X] T045 [US1] In `scripts/lab/pve-service-deploy`, for lab, pass `-i inventories/lab/hosts.yml -i inventories/generated/hosts.yml -e @inventories/lab/lab-overrides.yml -e deploy_environment=lab` to the main play and the bootstrap play. Make sure the existing monitoring-inventory guard (~line 2012–2066) passes for lab now that the lab inventory has 12 service hosts, and that it still refuses a lab inventory with none (FR-017). Before the bootstrap play, add the inventory guard: `ansible-inventory --list` over the same layered sources and overrides; refuse if any host's `ansible_host` is outside `10.99.0.0/24` (message per contract), writing `reports/lab/inventory-guard.txt` (R-010, analysis C1).
- [X] T046 [P] [US1] Reverse proxy lab switch in `ansible/roles/reverse_proxy/templates/Caddyfile.j2` and `ansible/roles/reverse_proxy/tasks/main.yml`: when `deploy_environment == 'lab'`, the global block uses `local_certs` with no `acme_dns`; `domeneshop.env` and the `caddy-domeneshop.conf` drop-in are not rendered; any blackbox or landing step that probes public names is skipped.
- [X] T047 [P] [US1] llm-router lab switch in `ansible/roles/llm_router/templates/docker-compose.yml.j2` (and its tasks, if they wait on Tailscale): no `tailscale` service in lab. Set the lab health target in `ansible/host_vars/llm-router.yml` to the liveness path (no provider calls), following how `healthcheck.py` picks the URL. Use a `healthcheck_lab_path`-style key only if a second consumer exists; otherwise gate in the existing key.
- [X] T048 [P] [US1] Alertmanager lab switch in `ansible/roles/monitoring_stack/templates/alertmanager.yml.j2`: in lab, only the `null` receiver, with the root route and every child route pointing at it.
- [X] T049 [P] [US1] Gate `service_backup` with `when: (deploy_environment | default('prod')) != 'lab'` in `ansible/playbooks/financial-scenario.yml`, `hermes.yml`, `homeassistant.yml`, `immich.yml`, `jellyfin.yml` and `nextcloud.yml` (financial-scenario already has a gate; align it). T032 passes, together with T046–T048.
- [X] T050 [US1] Write `reports/lab/skipped-checks.txt` support: health or role checks that depend on another service or on user data are skipped in lab, with the reason. Start with the cases found while running T052 (for example the hermes → llm-router dependency and the immich/nextcloud data checks). List them in `specs/067-isolated-lab/research.md` R-010.
- [X] T051 [US1] Make `scripts/lab/ci-verify.sh` (offline verification) require, for `environment=lab`, `reports/lab/fingerprint.before.json`, `fingerprint.after.json`, `teardown.json` with `"ok": true`, and no `fingerprint.diff.txt` (`contracts/lab-run-evidence.md`). T033 passes end to end.
- [X] T052 [US1] End-to-end on `pve` (as `ci`, credentials as in `AGENTS.md`): `pve-service-deploy apply --environment lab --service ntfy`, then `hermes`, `reverse_proxy`, `monitoring`, `immich` and `homeassistant`. For each: pass, a clean `pct list | grep lab-`, no fingerprint diff, `isolation.json` all ok. Record the durations against SC-004 (≤ fresh-deploy cost; hermes ≈ 15 min). Also record which inner time limit, if any, the large-image services hit: Ansible `docker_compose_v2`/pull timeouts, role `wait_for`/`until` retries, `pve-service-deploy` waits. Raise any that is too low in the same PR (spec edge case "Large images", analysis U1). Do the failure paths from quickstart §2 (bad health path, cancelled run swept next time, capacity refusal with `LAB_MEMORY_MARGIN_MIB=999999`). Record the results in `specs/067-isolated-lab/quickstart.md` §1–§3.

**Checkpoint**: LAB is an isolated rehearsal from the CLI; production is proved unchanged on every run.

---

## Phase 5: User Story 3 — The PROD stage is a real deployment again (Priority: P2)

**Goal**: The pipeline uses the new lab path; PROD plans show the real change; the standalone LAB
workflows are gone; lifecycle `lab` is the rehearsal.

**Independent Test**: [quickstart.md](./quickstart.md) §5 and §7.

### Tests for User Story 3

- [X] T053 [P] [US3] Write `python/tests/guardrails/test_removed_lab_workflows.py`:
  - `.github/workflows/lxc-deploy-lab.yml` and `lxc-promote-lab.yml` do not exist;
  - no file outside `specs/` references `lxc-deploy-lab`, `lxc-promote-lab`, "LXC Deploy (LAB)" or "LXC Promote (LAB)";
  - no workflow job name contains "changes prod".

  It must fail now.
- [X] T054 [P] [US3] Write `python/tests/guardrails/test_lifecycle_lab_target.py`, parsing `.github/workflows/lxc-lifecycle.yml`:
  - `environment=lab` with `action=delete` fails in the first step with "no standing lab copy exists; LAB is an ephemeral rehearsal (067)";
  - `lab` add/change call `pve-service-deploy … --environment lab`;
  - prod keeps `confirm_*` checks.

  Also assert that `lxc-promote-prod.yml` has the job "LAB rehearsal (isolated)" with `timeout-minutes: 90`. It must fail now.

### Implementation for User Story 3

- [X] T055 [US3] Update `.github/workflows/lxc-promote-prod.yml`:
  - rename the job "Apply (LAB, changes prod)" → "LAB rehearsal (isolated)" and its step "Apply on PVE (LAB)" → "Rehearse on PVE (LAB, isolated)";
  - set `timeout-minutes: 90`;
  - make the summary text say LAB is an isolated rehearsal and the PROD plan is the real change;
  - surface `reason=` from `summary.txt` (fingerprint/isolation/capacity/teardown) in the LAB summary;
  - keep the `lab_gate_failed`/override logic unchanged.

  Remove the 2026-10-28 "changes prod" wording.
- [X] T056 [US3] Update `.github/workflows/lxc-lifecycle.yml` per T054. Add an early step that refuses `lab`+`delete`. For `lab`, drop the confirmations that exist only because lab touched prod, and keep every prod confirmation. Make sure the run-ID capture still matches `lab-<svc>-*`.
- [X] T057 [US3] Delete `.github/workflows/lxc-deploy-lab.yml` and `.github/workflows/lxc-promote-lab.yml`. Update `.github/workflows/lab-integration-tests.yml` and `nightly-deeper-verification.yml` wherever they call, mention or depend on them or on `state/services`, using the T003 list.
- [X] T058 [US3] Validate the workflows locally: `DOCKER_HOST=unix://$HOME/.docker/run/docker.sock act -l` and `act -n -W .github/workflows/lxc-promote-prod.yml workflow_dispatch`, plus the same for `lxc-lifecycle.yml`, `lab-integration-tests.yml` and `nightly-deeper-verification.yml`. Note any `act` limitation in the PR. T053 and T054 pass. *(`act` is not installed on the Linux dev box; workflow YAML parsed and covered by T053/T054 instead.)*
- [X] T059 [US3] Full promotion of `ntfy` with a harmless config change, per quickstart §5. The LAB job passes and production does not have the change. The PROD plan shows it against `state/prod/ntfy`. After the operator's approval and `lxc-apply-prod` (dispatched by the operator), production has it. Then a forced LAB failure (bad health path on a branch) shows that PROD refuses without `allow_override_failed_lab_gate`. Record this in quickstart §5. This counts as promotion 1 of 5 for SC-007.

**Checkpoint**: The pipeline is honest: LAB is a rehearsal and PROD is the deploy.

---

## Phase 6: User Story 4 — The same lab path works from a laptop (Priority: P3)

**Goal**: Constitution V parity for the lab rehearsal (FR-019).

**Independent Test**: [quickstart.md](./quickstart.md) §4.

- [X] T060 [US4] Add an `AGENTS.md` section "Lab rehearsal from a laptop": the exact `ssh pve '… ./pve-service-deploy apply --environment lab --service <svc>'` command, with the vault password and token on stdin as `lxc-promote-prod.yml` passes them, and fetching evidence with `scripts/lab/fetch_evidence_pack.sh --environment lab --run-id <id>`. List the host-only parts (nftables via `lab_setup.yml --tags lab-network`, the drift timer via `host_proxmox.yml --tags state-drift`, both root Ansible from the laptop with `-k`).
- [X] T061 [US4] Run the laptop path for `ntfy` with the same commit as a T052 pipeline-equivalent run. Compare `summary.txt`, the set of `reports/lab/*.json` and `teardown.json`. Record the match in `specs/067-isolated-lab/quickstart.md` §4 (SC-008).

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T062 [P] Update the operator docs from the T003 list: `README.md`, `AGENTS.md`, `docs/operations/backups-proxmox-config.md`, `docs/operations/backups-proxmox-config-restore.md`, `docs/operations/rebuild-orchestrator.md`, `docs/runbooks/rebuild-orchestrator-restore.md`, `docs/runbooks/laptop-nfs-setup.md`, and any pipeline runbook. Make them say: LAB = isolated rehearsal; PROD = real deploy; state lives at `state/{prod,lab}`; the drift alert and how to respond. Replace the 2026-10-28 "a LAB apply changes production" warnings.
- [X] T063 [P] Add a runbook `docs/runbooks/state-drift.md`: what each `kind` means, how to read `latest.json`, and how to resolve each case (import into state, destroy a stray, or add an ignore line with a reason), plus how to clear a stale-check alert.
- [X] T064 [P] Update the memory note that "lab deploy is prod" (`lab-is-prod.md` in the agent memory) once T059 passes, and CLAUDE.md's "Working with Git"-adjacent notes if they mention the LAB workflows.
- [X] T065 Mark backlog `docs/backlog/067-lab-prod-same-address-space.md` and `096-terraform-state-layout.md` as done in `docs/backlog/backlog.md`, with links to this spec.
- [X] T066 Delete `scripts/lab/migrate-state-067`, `python/tests/guardrails/test_migrate_state_067.py` and `specs/067-isolated-lab/refs-to-remove.txt` (one-off, R-012). Keep the dated `state-backup-067-*` on `pve` for 30 days, then remove them by hand (noted in the runbook).
- [X] T067 Run the full guardrail suite (`pytest python/tests/guardrails`), `task` lint, `terraform validate` for all 12 roots and `terraform/`, and `task mutmut:gate` if Python under the mutation scope changed. Fix any failure.
- [ ] T068 Track SC-007 over the next four promotions (2–5): each PROD plan shows the real change and each LAB run has no fingerprint diff. Note them in `specs/067-isolated-lab/quickstart.md` §5.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (T001–T003)**: none. T001 blocks T020; T002 blocks T005; T003 feeds T057 and T062.
- **Foundational (T004–T010)**: T005 → T007 (operator apply). T010 (constitution amendment) blocks T038. T008 is needed by T023 and T036–T040. T009 is needed by T034 and must be merged before T021 (so the migration's prod plans run with the prefix variable present).
- **US2 (T011–T027)**: after Foundational. T014–T020 ship in one PR, and T021 runs right after its merge, **before any other pipeline run**. The drift check (T022–T027) depends on T014 and T008 and can be a second PR.
- **US1 (T028–T052)**: after T021 (the migration is done; prod states at `state/prod`) and T007 (isolation live).
- **US3 (T053–T059)**: after US1. T055 relies on the new `reason=` values (T040–T043).
- **US4 (T060–T061)**: after US1. It can run in parallel with US3.
- **Polish**: after US3.
- **Constitution amendment (T010)**: in PR A; it blocks T038.

### User Story Dependencies

- **US2 → US1 → US3**: this chain is strict (the spec's own dependency: no lab without separate state, and no honest PROD without a lab).
- **US4**: depends only on US1.

### Within Each User Story

Tests first (must fail), then the libraries (`state.sh`, `tfvars.sh`, `fingerprint.sh`,
`ct_conflicts.sh`), then the orchestrator wiring in `pve-service-deploy`, then Ansible and
workflows, then the live run on `pve`.

### Parallel Opportunities

- Setup: T002 ∥ T003.
- Foundational: T004 ∥ T006 ∥ T009.
- US2: T011 ∥ T012 ∥ T013; T016 ∥ T017; T022 ∥ T025.
- US1: T028–T033 all in parallel (separate test files); T044 ∥ T046 ∥ T047 ∥ T048 ∥ T049 (separate role and playbook files). The `pve-service-deploy` tasks T037–T043 and T045 touch one file, so they run sequentially.
- US3: T053 ∥ T054.
- Polish: the docs tasks run in parallel.

---

## Parallel Example: User Story 1

```bash
# Tests (separate files):
T028 test_lab_tfvars.py   T029 test_prod_fingerprint.py   T030 test_lab_capacity_and_policy.py
T031 test_lab_overrides.py  T032 test_lab_switches.py     T033 test_lab_run_contract.py

# Ansible side (separate files):
T044 inventories/lab/{hosts.yml,lab-overrides.yml}
T046 roles/reverse_proxy   T047 roles/llm_router   T048 roles/monitoring_stack   T049 6 playbooks
```

---

## Implementation Strategy

### Suggested PR slices (each one shippable, production never half-migrated)

1. **PR A: isolation + identity + constitution amendment** (T001–T010): no behaviour change; the operator applies `lab-network`.
2. **PR B: state layout + migration** (T011–T021): merge, then the supervised session the same day.
3. **PR C: drift check** (T022–T027).
4. **PR D: ephemeral lab path (MVP)** (T028–T052): the CLI is honest; the workflows still point at it unchanged.
5. **PR E: pipeline** (T053–T059).
6. **PR F: laptop parity + polish** (T060–T068).

PRs A, B, D and F touch `scripts/lab/**` or `.specify/**`, so they need the protected-path label (operator approval).

### MVP

US2's migration (PR B) plus US1 (PR D). After PR D, a LAB run is a rehearsal that proves on its
own that production was untouched. That alone closes the 2026-10-28 failure mode.
