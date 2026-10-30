# Contract: nightly state-drift check (FR-014)

| Item | Value |
|---|---|
| Runner | `scripts/lab/state-drift-check`, systemd `state-drift-check.timer` on `pve`, user `ci` |
| Schedule | `*-*-* 06:30:00` (after the 05:xx backups), `Persistent=true` |
| Lock | `state/lab/.lock`. If a LAB run holds it, the check exits 0 and leaves the timestamp unchanged, so the stale alert covers a check that keeps being skipped |
| Report | `/var/lib/homelab-proxmox/artifacts/state-drift/latest.json` (see data-model) and journal |
| Ignore list | `scripts/lab/state-drift-ignore.txt`: `<vmid> <reason>` per line; empty at ship |

## Metrics (node_exporter textfile `state_drift.prom`, written atomically)

| Metric | Type | Labels | Meaning |
|---|---|---|---|
| `homelab_state_drift_containers` | gauge | `kind` = `untracked` \| `double_tracked` \| `lab_leftover` | count found in the last successful run |
| `homelab_state_drift_last_success_timestamp_seconds` | gauge | — | Unix time of the last run that completed |

## Alerts (added to `backup_alerts.yml.j2`, PROD only like the rest of that file)

| Alert | Expression | For | Severity |
|---|---|---|---|
| `StateDriftContainers` | `max by (kind) (homelab_state_drift_containers) > 0` | 0m | warning (phone) |
| `StateDriftCheckStale` | `time() - homelab_state_drift_last_success_timestamp_seconds > 26 * 3600` | 15m | warning (phone) |
| `StateDriftCheckAbsent` | `absent(homelab_state_drift_last_success_timestamp_seconds)` | 26h | warning (phone) |

The annotations point at `journalctl -u state-drift-check` and `latest.json` for the container
names (FR-014: names come from the check's own output).
