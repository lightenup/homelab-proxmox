# Quickstart: Service Landing Page at hus-sky.no

How to deploy and verify the landing page. Assumes the reverse-proxy and monitoring LXCs already
exist (features `039-https-services`, `042-monitoring-tier-c`).

## Prerequisites

- Ansible control able to reach the `services` group (laptop or CI). Vaults present
  (`group_vars/services/vault.yml`, `group_vars/monitoring/vault.yml`) or env-injected.
- Domeneshop API creds available to Caddy (already configured via systemd drop-in).

## One-time manual step — apex DNS (FR-011)

The wildcard `*.hus-sky.no` does **not** cover the bare apex. Add a **public DNS A record at
Domeneshop**: `hus-sky.no → 192.168.1.211`, parallel to the existing wildcard. DNS is public-only and
resolves to the LAN IP for both LAN and Tailscale clients (per `docs/network-layout.md`; split-horizon
not used).

Verify before deploying: `dig +short hus-sky.no` returns `192.168.1.211` from both a LAN client and a
Tailscale client.

## Deploy

A single `site.yml` run applies both halves in the correct order. `site.yml` already imports
`services.yml` (which includes `reverse_proxy.yml`, tagged `reverse_proxy`) **before** `monitoring.yml`
(tagged `monitoring`), so the reverse proxy regenerates routes + the landing page first, then
monitoring regenerates the blackbox targets — both from the same `caddy_services` source. Scope the
run to just these two roles with tags so unrelated services (Immich, Nextcloud, …) are not redeployed:

```bash
# from the ansible/ directory (ansible.cfg lives there — sets roles_path + inventory).
# Running from repo root does NOT load ansible.cfg, so roles like proxmox_host won't be found.
cd ansible
ansible-playbook playbooks/site.yml --tags reverse_proxy,monitoring
```

> A full `ansible-playbook site.yml` (no tags) also works and is what a full-stack deploy runs; the
> `--tags reverse_proxy,monitoring` form is the scoped path for a landing-page / `caddy_services`
> change. `import_playbook` tags propagate to every play in the imported playbooks, so the tag filter
> runs exactly the reverse-proxy and monitoring plays and skips host/backup/healthcheck.

CI parity: the same `site.yml` invocation runs from GitHub Actions with no new dropdown (no new service).

### Pre-flight checks (non-destructive, per constitution)

```bash
# from the ansible/ directory (see Deploy note above)
ansible-playbook playbooks/site.yml --tags reverse_proxy,monitoring --syntax-check
ansible-playbook playbooks/site.yml --tags reverse_proxy,monitoring --check --diff
# Caddy config validation runs inside the role (caddy validate). If editing workflows:
act -l
```

## Verify (maps to Success Criteria)

1. **SC-001** — Browse `https://hus-sky.no` on the LAN: valid Let's Encrypt cert, no warnings, one
   card per enabled user-facing service (Immich, Jellyfin, Nextcloud, Grafana).
2. **SC-002** — Click each card → lands on the correct `https://<service>.hus-sky.no`.
3. **SC-005** — All running ⇒ every card "up". `docker stop` one service's backend (or stop the
   LXC), wait ~30s (blackbox interval) + refresh ⇒ that card "down".
   (No redeploy needed — health updates client-side via `/api/status` polling.)
4. **SC-006** — Stop Prometheus (`monitoring` LXC) ⇒ `https://hus-sky.no` still renders all
   cards/links; indicators show "unknown", page does not blank.
5. **SC-007** — `curl -s 'https://hus-sky.no/api/status?query=node_load1' | jq .data.result[0].metric`
   ⇒ shows `probe_success` instances, NOT `node_load1` (pinned query enforced).
6. **SC-003** — Add a temporary entry to `caddy_services`, run the single tagged `site.yml` ⇒ new
   route + blackbox target + card appear. Remove it, redeploy ⇒ all three gone.
7. **SC-004** — Repo search confirms single source of truth:
   ```bash
   rg -n 'blackbox_https_targets:\s*$' ansible/group_vars/monitoring/vars.yml   # should be a generated expr, not a literal list
   ls ansible/roles/reverse_proxy/templates/*.caddy.j2                          # only service.caddy.j2 + apex.caddy.j2 remain
   ```
8. **SC-008** — Re-run the same tagged `site.yml` from a GitHub Actions dispatch; same result as laptop.

## Rollback

The change is config-only and idempotent. To roll back, revert the branch and re-run
`site.yml --tags reverse_proxy,monitoring`; Caddy and Prometheus reload to the previous generated
config. No data is touched.
