# Quickstart: Financial-Scenario v2 Deploy (Stateful)

Deploy, upgrade-safety, topology, persistence, backup, and posture verification. Runs through the
existing gated pipeline (CI or laptop — dual-provisioning parity).

## Prerequisites

- Synology NFS share `homelab_financial_scenario` created with rw export for `192.168.1.217/32`
  (prod) and `192.168.20.218/32` (lab) — **done by operator 2026-06-21**.
- GHCR pull creds present in `ansible/group_vars/services/vault.yml` (`ghcr_pull_username`,
  `ghcr_pull_token`).

## 0. Apply Terraform (enable in-guest NFS feature)

```bash
# via gated pipeline — sets features_mount = "nfs" on financial_scenario_lxc.
# Image-independent (LXC feature flag only, applied via pct set by the orchestrator).
scripts/lab/pve-service-deploy plan  financial-scenario
scripts/lab/pve-service-deploy apply financial-scenario
```

From the LXC, confirm the share is visible:

```bash
showmount -e 192.168.1.109   # lists /volume1/homelab_financial_scenario
```

## 1. Upgrade-safety drill (SC-001) — do this first on a real upgrade

```bash
# Baseline on 0.1.0 (current), save a scenario via the GUI, then:
#   set financial_scenario_version: "0.2.2" in ansible/group_vars/services/vars.yml
ansible-playbook -i inventories/prod/hosts.yml playbooks/financial-scenario.yml
```

Expect: all three containers `healthy`; GUI 200 on `:3000`; the previously saved scenario still listed
and openable; reference-data edits intact (no re-seed).

## 2. Topology verification (SC-002, SC-003)

```bash
docker inspect financial_scenario_mcp \
  | jq '.[0].Mounts, (.[0].Config.Env[] | select(startswith("API_BASE_URL")))'
# Expect: NO reference_data mount; API_BASE_URL=http://api:8000

docker inspect financial_scenario_api | jq '.[0].Mounts[] | select(.Destination=="/app/data")'
# Expect: bind-mount from {{ financial_scenario_data_dir }}/scenarios

docker compose -f /opt/financial-scenario/docker-compose.yml ps
# Expect: mcp healthy only after api healthy
```

Save a scenario via the gated `/mcp` endpoint over the tailnet → confirm it appears in the GUI
comparison list, badged agent-authored, and opens with freshly computed results.

## 3. Persistence (SC-001)

```bash
ls -l /opt/financial-scenario-data/scenarios/        # scenarios.db (+ -wal/-shm)
docker compose -f /opt/financial-scenario/docker-compose.yml down
docker compose -f /opt/financial-scenario/docker-compose.yml up -d
# Expect: saved scenarios still present.
```

## 4. Backup + restore (SC-004, SC-005)

```bash
sudo systemctl list-timers financial-scenario-backup.timer
sudo systemctl start financial-scenario-backup.service     # trigger now
ls -l /mnt/financial-scenario/backups/                     # financial-scenario-backup-<TS>.tar.gz

# Integrity of the snapshot (no host sqlite3 dependency — run inside the api container):
mkdir -p /tmp/fsr && tar -xzf /mnt/financial-scenario/backups/financial-scenario-backup-*.tar.gz -C /tmp/fsr
DB="$(find /tmp/fsr -name scenarios.db)"
docker cp "$DB" financial_scenario_api:/tmp/verify.db
docker exec financial_scenario_api python -c \
  "import sqlite3; print(sqlite3.connect('/tmp/verify.db').execute('PRAGMA integrity_check').fetchone()[0])"  # → ok
docker exec financial_scenario_api rm -f /tmp/verify.db

# Restore drill: stop stack, cp scenarios.db over a fresh /app/data store, start, confirm listed.
```

Confirm no stray `.backup-snapshot.db` is left under `/opt/financial-scenario-data/scenarios/`.

## 5. Posture unchanged (SC-006)

```bash
docker compose -f /opt/financial-scenario/docker-compose.yml ps --format '{{.Names}}\t{{.Ports}}'
# Expect: only gui publishes 3000; api/mcp internal only.
scripts/healthcheck/financial-scenario.sh --profile lan
# Expect: green; /mcp still requires the shared secret; blackbox probe green.
```

## Pipeline validation (pre-merge)

```bash
terraform -chdir=terraform validate
ansible-playbook -i inventories/prod/hosts.yml playbooks/financial-scenario.yml --syntax-check
# If act + Docker available: act -l  (workflows parse, dropdowns recognise financial-scenario)
```
