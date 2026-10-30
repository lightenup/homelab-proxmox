# Runbook: state drift (067)

`state-drift-check.timer` runs `scripts/lab/state-drift-check` on `pve` every night at 06:30, as
`ci`. It compares the containers on the host with the vmids in `state/prod/*/terraform.tfstate`,
and sweeps leftover lab copies. Alerts: `StateDriftContainers`, `StateDriftCheckStale`,
`StateDriftCheckAbsent` (phone).

## Read the result

```bash
ssh pve 'jq . /var/lib/homelab-proxmox/artifacts/state-drift/latest.json'
ssh pve 'journalctl -u state-drift-check -n 50 --no-pager'
```

`latest.json` lists each finding with its vmid and hostname.

## `StateDriftContainers`, by `kind`

| kind | Meaning | What to do |
|---|---|---|
| `untracked` | A container exists that no production state holds. | If it should be managed: `terraform import -state=/var/lib/homelab-proxmox/state/prod/<svc>/terraform.tfstate <address> pve/lxc/<vmid>`, then a `plan` must show `No changes`. If it is a stray: check it holds nothing, then `sudo pct destroy <vmid>`. If it is kept on purpose: add `<vmid> <reason>` to `scripts/lab/state-drift-ignore.txt`. |
| `double_tracked` | One vmid is in two states. | Decide which service owns it. Remove it from the other with `terraform state rm -state=<that state> <address>` (never `destroy`). |
| `lab_leftover` | A lab copy (`lab-*`, `vmbr99`, `10.99.0.200-254`) survived a lab run. The check already stopped and destroyed it (`swept: true`). | Find why the run did not tear down: `reports/lab/teardown.json` of the last LAB run. If `swept` is `false`, destroy it by hand: `sudo pct stop <vmid>; sudo pct destroy <vmid>`. |

The check never touches a container that does not match the lab-copy identity rule.

## `StateDriftCheckStale` / `StateDriftCheckAbsent`

- Stale: the last completed run is more than 26 hours old. Either it failed (read the journal) or a
  LAB run held `state/lab/.lock` every night. Run it by hand to clear it:
  `sudo systemctl start state-drift-check.service`.
- Absent: nothing was ever collected. Apply `ansible-playbook playbooks/host_proxmox.yml
  --tags state-drift` as root, then start the service once.

## Pre-migration backups

`/home/ci/state-backup-067-*` and `/var/lib/homelab-proxmox/state-backup-067-*` are kept for 30
days after the 067 migration, then removed by hand.
