# Quickstart: validating the isolated lab (067)

This is a run guide that proves the feature end to end. Contracts:
[pve-service-deploy-lab](./contracts/pve-service-deploy-lab.md),
[lab-network](./contracts/lab-network.md), [state-drift-metrics](./contracts/state-drift-metrics.md),
[lab-run-evidence](./contracts/lab-run-evidence.md).

## Prerequisites

- The feature branch has been merged, or checked out on `pve` as `/home/ci/homelab-proxmox`.
- Root Ansible applied by the operator from the laptop (password SSH as root):
  `ansible-playbook playbooks/lab_setup.yml --tags lab-network` (nftables isolation) and
  `playbooks/host_proxmox.yml --tags state-drift` (timer, backup paths).
- `ssh pve` works as `ci`. The vault password and token are available as in `AGENTS.md`.

## M. One-time state migration (FR-013, supervised; operator present)

> Done on 2026-10-30 (T021). `migrate-state-067` and its test were deleted in T066; recover them from git
> history (`b7273dc`) if a rerun is ever needed. The dated backup `/home/ci/state-backup-067-20261030` on `pve` is kept
> for 30 days (until 2026-11-29); remove it by hand after that.

```bash
ssh pve
cd ~/homelab-proxmox/scripts/lab
./migrate-state-067 --dry-run        # prints the 12 sources (symlinks resolved) and targets
./migrate-state-067                  # copy-first; stops at the first plan that is not "No changes"
```

Expected: `12/12 No changes`, then `old layout removed`. Check:

```bash
ls /var/lib/homelab-proxmox/state            # prod  lab   (no 'services')
ls /mnt/nas/homelab_ci/infra_state 2>&1      # No such file or directory
ls /home/ci/state-backup-067-*/   # 12 dated copies
sudo systemctl start proxmox-config-backup.service   # then the manifest lists state/prod/<svc> x12
```

Then, for each service, `pve-service-deploy plan --environment prod --service <svc>` → `No changes`
(SC-005).

**Observed run (T021, 2026-10-30)**: `migrate-state-067` planned all 12 services against
`state/prod/<svc>` with `No changes`, then `--remove-old-layout` removed `state/services` and
`infra_state/{lab,prod}`. **Defect found:** the dated backup `state-backup-067-<date>` was never
written (`/var/lib/homelab-proxmox` is root-owned, so `ci` got `Permission denied`) and the script
carried on, because `set -e` is off inside a function called with `||`. Result: no pre-migration
copy exists. The new states are proven by the 12 clean plans (each holds one `proxmox_lxc`), and
`/home/ci/state-backup-067-20261030/` was taken right after as a copy of `state/prod`. Fixed in the
script (`run` now exits on a failed step) with a regression test. Lesson: a one-off that deletes
must prove its backup exists before it deletes.

## 1. A LAB run leaves production untouched (US1, SC-001/002)

Start "Prod 1 - LXC Promote" for `ntfy` (or, from a laptop, run the same command over SSH, as in
section 4). Then check:

- The LAB job is named "LAB rehearsal (isolated)" and passes.
- The evidence contains `reports/lab/fingerprint.before.json` and `after.json`, has no
  `fingerprint.diff.txt`, and `teardown.json` shows `ok: true`.
- `copy.json` shows `lab-ntfy` at `10.99.0.222`.
- Afterwards, on `pve`: `sudo pct list | grep lab-` is empty, and `ls state/lab lab-scratch` shows
  only `.lock`.

Repeat for the large and the infrastructure services: `hermes` (time, SC-004),
`reverse_proxy` and `monitoring` (FR-011 switches), and `immich` (mounts → scratch).

## 2. Failure paths still clean up (US1 scenarios 2–3)

- **Failed health check**: run LAB on a branch where the service's health path is wrong. The run
  fails, and teardown still removes the copy.
- **Aborted run**: cancel the workflow during "Ansible". `lab-<svc>` may remain. Start any LAB run
  and confirm that `sweep.json` lists it and it is gone. Alternatively, wait for 06:30 and check
  `latest.json` (`lab_leftover`, swept).
- **Capacity**: on `pve`, run with `LAB_MEMORY_MARGIN_MIB=999999` (test-only override). The run
  refuses with both figures.

## 3. Isolation (FR-007/008, SC-003)

```bash
sudo nft list table inet lab_isolation
jq . <evidence>/reports/lab/isolation.json     # every LAN target ok:true (unreachable), internet ok:true
```

During a run, from `pve`, also run `sudo pct exec <lab vmid> -- timeout 3 bash -c '</dev/tcp/192.168.1.216/80'`.
It must fail.

**Observed run (T007, 2026-10-30)**: operator ran `lab_setup.yml --tags lab-network -k`
(`ok=6 changed=5 failed=0`). `nft list table inet lab_isolation` showed the intended rules, each
chain **twice** (PR A loaded the file with `nft -f`, which appends). Fixed in PR B: the file now
starts with `table …` / `delete table …` so a load replaces the table. Re-run the same command
once after PR B merges and check each rule appears once.

**Re-check (2026-10-31, `nft list table inet lab_isolation` on `pve`)**: each chain and rule now appears
once. `forward`: established/related accepted; `vmbr99` to `10.99.0.0/24` accepted; the two rig VMs
(10.99.0.10/.11) may reach only `192.168.1.211:443` and `192.168.1.220:4000`; everything else from `vmbr99` to
`lan_private` (`10.0.0.0/8`, `100.64.0.0/10`, `172.16.0.0/12`, `192.168.0.0/16`) is dropped. `input`:
established/related accepted, every other packet from `vmbr99` to the host is dropped. Internet traffic is not
in `lan_private`, so it stays open. Because `100.64.0.0/10` (the tailnet) is dropped, a guest cannot use the
host's Tailscale resolver `100.100.100.100`, which is why guests need an explicit public nameserver (#308).

## 4. Laptop parity (US4, SC-008)

From the laptop, run the same `pve-service-deploy apply --environment lab --service ntfy` over SSH
(vault password and token on stdin, as the workflow does). The result and evidence files match
section 1.

## 5. PROD stage is real (US3, SC-007)

Change the ntfy configuration (for example a comment in its compose template) and promote it:

- After the LAB job, the production container does not have the change.
- "Plan (PROD)" shows the change against `state/prod/ntfy`.
- After approval and `lxc-apply-prod`, the production container has it.
- A LAB failure blocks PROD unless `allow_override_failed_lab_gate=true`.

## 6. Drift check (US2, SC-006)

```bash
sudo systemctl start state-drift-check.service
jq . /var/lib/homelab-proxmox/artifacts/state-drift/latest.json      # all lists empty
curl -s localhost:9100/metrics | grep homelab_state_drift
```

Negative test: create a container that no state tracks (`sudo pct create 199 … --hostname drift-test`
on `vmbr99`, no `lab-` prefix). Run the check. `untracked` lists VMID 199, and Prometheus fires
`StateDriftContainers`. Destroy 199 afterwards.

**Observed run (T027, 2026-10-30)**: `monitoring` was deployed with `pve-service-deploy apply
--environment prod` directly on `pve` (plan exit 0, so no Terraform change; the pipeline's LAB
stage was unusable between PR B and PR D, see below). promtool validated the rules, Prometheus
reloaded, and `StateDriftContainers`, `StateDriftCheckStale`, `StateDriftCheckAbsent` were loaded
with all 61 scrape targets up. Clean run: `latest.json` `ok: true`, all three kinds 0, timestamp
metric present, timer enabled (next 06:30). Negative test: CT 199 `drift-test` on `vmbr99`
(no `lab-` prefix) was reported `untracked`, **not destroyed**, and `StateDriftContainers{kind="untracked"}`
fired; after `pct destroy 199` the next run was clean again.

**Note**: between PR B and PR D the pipeline's LAB stage reads the now-empty `state/lab/<svc>`
with `lab.tfvars` (prod IPs); the duplicate-container guard is what stops it. Do not dispatch
`lxc-promote-prod` until PR D.

## 7. Removed workflows and lifecycle (FR-018/020)

- `.github/workflows/lxc-deploy-lab.yml` and `lxc-promote-lab.yml` are gone, and
  `pytest python/tests/guardrails -k removed_lab_workflows` passes.
- Lifecycle `environment=lab, action=delete` fails at once with the "no standing lab copy" message.
  `environment=lab, action=add|change` runs the rehearsal.
- `act -l` lists the workflows, and `act -n -W .github/workflows/lxc-promote-prod.yml workflow_dispatch` parses.

## T052 record (2026-10-30, `pve`, as `ci`)

`apply --environment lab` for six services, each ending with a clean host (12 production containers, empty
`lab-scratch`, no lab state), `teardown.json` ok, and no fingerprint diff:

| Service | Result | Duration |
|---|---|---|
| ntfy | pass | 214 s |
| reverse_proxy | pass | 216 s |
| monitoring | pass | 420 s |
| immich | pass | 482 s |
| homeassistant | pass | 346 s |
| hermes | first run failed (egress probe of absent peers); pass after the lab skip | 740 s / ~600 s |

Hermes' skipped probes are recorded in `reports/lab/skipped-checks.txt`. A second run while the lock was
held refused with exit 1 and left the other run untouched.

## T059 record (2026-10-30/31, pipeline, `ntfy`)

Promotion 1 of 5 for SC-007. Marker: a rendered YAML comment `# T059 promotion rehearsal` in the ntfy compose
template.

| Step | Run | Result |
|---|---|---|
| Promote `067-t059-ntfy-change`, suite forced on | 41138655454 | LAB rehearsal pass, suite pass, `lab_gate_failed=false`, `sha_all_ok=true` |
| Production before apply | | marker count 0 |
| `lxc-apply-prod` | 41174279772 | success; production marker count 1 |
| Promote `067-t059-ntfy-bad-health` (418 health path) | 41134375265 | LAB `ok=false` (health check failed after 180 s), `lab_gate_failed=true`, copy destroyed, `lab-scratch` empty |
| `lxc-apply-prod` for that run, no override | 41174541673 | refused at "Enforce override semantics": "LAB deploy and/or confidence suite failed; override not enabled." The sync and apply steps were skipped. |

The Terraform PROD plan shows no change for this promotion, because the marker lives in an Ansible template; the
change reaches production through the apply's Ansible step.

Defects this exercise found and fixed before it could pass cleanly:

- #308: the confidence-suite rig VM inherited Tailscale MagicDNS, which `vmbr99` cannot reach, so cloud-init
  hung (600 s) and the suite failed.
- #309: suite evidence retention globbed `lab-*`, so the isolated-lab runs (`lab-<service>-...`) made it delete
  the suite's own newest pack and CI found no provenance.
- #311: a died step (for example the health check) left no `reason=`; the summary now names it.
- The first test marker was a Jinja comment, which never renders; a rendered comment is required for the
  before/after check to mean anything.

## T061 record (2026-10-31, laptop path, `ntfy`)

`rsync` of the working tree to `ci@pve`, then `ssh ci@pve './pve-service-deploy apply --environment lab --service ntfy'`
(run `lab-ntfy-unknown-20261031-060408`, 3 min 4 s), compared with the pipeline's LAB evidence for
`lxc-promote-prod` run 41138655454.

| Item | Pipeline | Laptop |
|---|---|---|
| `reports/apply/summary.txt` | `status=success`, `terraform_plan_exitcode=2` | identical |
| `reports/lab/*.json` | capacity, copy, fingerprint.before/after, isolation, sweep, teardown, plus `inventory-guard.txt` | the same 8 files |
| JSON key shapes (capacity, copy, fingerprint, isolation, teardown) | | identical |
| `teardown.json` | `ok: true`, scratch and lab state removed | identical |
| fingerprint before/after | only `phase` and `taken_at` differ | same; no `fingerprint.diff.txt` |
| After the run | 0 lab containers, empty `lab-scratch`, 12 production containers | same |

Two file-set differences are expected, not behavioural: CI strips `*.tfplan` before uploading the artifact, and
`ansible-galaxy.txt` is written only when the collections are installed (the CI run did; the laptop run found
them present).

Limits of this check: the laptop run was made from the working tree (the ntfy sources are the same as the
pipeline's commit; only docs differ). The vault password and token were already on `pve`, so the stdin hand-off
documented in `AGENTS.md` was not exercised from the laptop.

## T067 record (2026-10-31)

- `pytest python/tests`: 535 passed (the 6 migration tests were deleted with `migrate-state-067`).
- `scripts/lab/ci-validate-iac.sh`, `scripts/lab/ci-verify.sh <valid fixture>`: pass.
- `pre-commit run --all-files` (yamllint, ansible-lint, json/yaml checks): pass.
- `scripts/ci/terraform-validate.sh` on `pve`: exit 0.
- `task mutmut:gate`: not run; no Python under the mutation scope changed (only tests and docs).

## T021 step 4 record (2026-10-31, backup collects `state/prod`)

The nightly `proxmox-backup.service` run at 2026-10-31 02:03 (journal, read as `ci`): "Collecting local Terraform
state from: /var/lib/homelab-proxmox/state/prod", IaC artifacts 104K, secret scan clean, "Manifest generated: 28
files checksummed", "Backup completed successfully", "Decryption successful". `state/prod` holds 12 service
directories and the collector copies every `terraform.tfstate*` in each. Not directly confirmed: the manifest
listing itself, which sits inside the age-encrypted archive that only root can open. To see it: as root on `pve`,
decrypt the newest `/mnt/nas-backup/proxmox-backup-*.tar.zst.age` with `/root/.age/proxmox-backup.key` and list
`iac-artifacts/local-state/`.

## T068 record: promotion 2 of 5 (2026-10-31, `monitoring`, runner-heartbeat alert rules)

Real change: the `CiRunnerHeartbeatStale` and `CiRunnerHeartbeatAbsent` rules (PR #314) reaching Prometheus.

| Step | Run | Result |
|---|---|---|
| Promote `main` (`1c18cb6`), suite forced on | 41178629827 | LAB rehearsal pass (`ok=138 failed=0`), suite 27/28 pass, `lab_gate_failed=false`, `sha_all_ok=true`, Plan (PROD) pass |
| After the run | | 0 lab containers, empty `lab-scratch`, 12 production containers, no `state/lab` content |
| `lxc-apply-prod` (dispatched by the operator) | 41180066498 | success, Ansible `ok=140 changed=2 failed=0` |
| Prometheus (CT 103) | | both rules loaded; `time() - homelab_ci_runner_last_heartbeat_timestamp_seconds` = 259 s, so neither alert is pending |

The PROD plan carries no Terraform change for this promotion (the rules are an Ansible template); the real
change is visible in the apply's `changed=2` and in the loaded rules. The LAB run had no fingerprint diff
(the `ok` gate requires `status=success`, and the evidence check requires a clean teardown and fingerprint).
