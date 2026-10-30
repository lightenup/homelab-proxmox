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
ls /var/lib/homelab-proxmox/state-backup-067-*/   # 12 dated copies
sudo systemctl start proxmox-config-backup.service   # then the manifest lists state/prod/<svc> x12
```

Then, for each service, `pve-service-deploy plan --environment prod --service <svc>` → `No changes`
(SC-005).

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

## 7. Removed workflows and lifecycle (FR-018/020)

- `.github/workflows/lxc-deploy-lab.yml` and `lxc-promote-lab.yml` are gone, and
  `pytest python/tests/guardrails -k removed_lab_workflows` passes.
- Lifecycle `environment=lab, action=delete` fails at once with the "no standing lab copy" message.
  `environment=lab, action=add|change` runs the rehearsal.
- `act -l` lists the workflows, and `act -n -W .github/workflows/lxc-promote-prod.yml workflow_dispatch` parses.
