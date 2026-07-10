# Quickstart: Euro-Office Document Server Deploy

Deploy + verify runbook. Runs identically locally and in CI (Constitution V). PVE has unrestricted
GitHub access; the Mac's push block does not affect deploys.

## Prerequisites
- Nextcloud on **34** (NC ≥ 33) — dependency delivered (`060-nextcloud-upgrade-33-34`).
- Vault (`ansible/group_vars/services/vault.yml`) has `ghcr_pull_username`, `ghcr_pull_token`, and a
  new `eurooffice_jwt_secret` (≥32 chars).
- ~4 GB free PVE RAM.

## 1. Land config (files changed)
Terraform: `services/eurooffice/`, `main.tf` module (4/4096/15, nesting), `service_ips["eurooffice"]`
in lab + prod tfvars. Ansible: `roles/eurooffice/*`, `playbooks/eurooffice.yml`, `host_vars/
eurooffice.yml`, `group_vars/services/vars.yml` (version pin + ip/port + `caddy_services` entry),
`vault.yml` (jwt secret), `roles/reverse_proxy/templates/service.caddy.j2` (optional timeout), and
`roles/nextcloud` (connector occ tasks). Workflows: add `eurooffice` to the three `service` dropdowns.

## 2. Provision + deploy the document server (gated pipeline)
```bash
# Plan-only first (non-destructive gate). eurooffice is defined on the 192.168.1.x network
# (prod + *.tfvars.template), mirroring market-model — not the divergent 192.168.20.x lab.tfvars.
scripts/lab/pve-service-deploy --service eurooffice --env prod            # plan
scripts/lab/pve-service-deploy --service eurooffice --env prod --apply    # plan+apply
```
Or GitHub Actions: **lxc-deploy-lab** → service `eurooffice`, apply=true; promote via
**lxc-promote-lab** / **lxc-promote-prod**.

Expected: Terraform creates `eurooffice-lxc`; `docker compose` reports the container `Up (healthy)`;
post-apply `GET /healthcheck` → 200; gate green (SC-003).

## 3. Wire Nextcloud connector
Re-run the nextcloud playbook so the `eurooffice` connector is installed/enabled/configured:
```bash
scripts/lab/pve-service-deploy --service nextcloud --env prod --apply
```
Expected: `occ app:list` shows `eurooffice` enabled, no `richdocuments*` (SC-006).

Then deploy monitoring so the new blackbox target/alert register:
```bash
scripts/lab/pve-service-deploy --service monitoring --env prod --apply
```

## 4. Verify (acceptance)
1. **Route** — `curl -I https://eurooffice.hus-sky.no/healthcheck` → 200 over TLS (SC-004).
2. **Editing** — in Nextcloud Files, create a `.docx` from `+`, type, close, reopen → content
   persists; open in a second session → live co-edit; admin connector test passes (SC-001/002).
3. **WebSocket** — browser dev-tools show the editor's `wss://` connection established (SC-004).
4. **Security posture** — confirm `EXAMPLE_ENABLED=false`, `JWT_ENABLED=true`, image pinned
   (`docker inspect` / compose file), jwt secret ≥32 and identical both sides (SC-005).
5. **Monitoring** — blackbox `eurooffice` liveness probe green (SC-007).

## Rollback
`caddy_services` entry `enabled: false` (route torn down by the reconcile step) and
`occ app:disable eurooffice`; destroy the LXC via Terraform if abandoning. Documents are untouched
(they live in Nextcloud).
