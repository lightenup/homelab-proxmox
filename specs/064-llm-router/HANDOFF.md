# Handoff — `064-llm-router`, 2026-08-30

Written when work moved off the dev Mac (Zscaler blocks Tailscale there) to a Linux laptop.
Start here, then use [`tasks.md`](./tasks.md) and [`quickstart.md`](./quickstart.md).

## Where it stands

**Code complete and merged** — PR [#201](https://github.com/lightenup/homelab-proxmox/pull/201),
merged to `main` as `dcd9f7e`. 35 of 65 tasks done: everything that could be built and validated
without live infrastructure.

**Nothing is deployed.** No LXC exists in LAB or PROD. The remaining 30 tasks are the live deploy
and the acceptance drills.

## What was validated, and how

Not just YAML-parsed — these were exercised properly:

- `ansible-lint` production profile, 0 findings; `yamllint`; repo pre-commit hooks
- `ansible-playbook --syntax-check` on the new playbook **and every existing service playbook**
  (the `node_exporter` change touches all of them via `lxc_base`)
- `terraform validate` + `terraform fmt -check`
- `promtool check rules` — 9 rules, rendered through the real shared `service_alerts.yml.j2`
- `docker compose config` on the rendered compose file
- Templates rendered through **real Ansible**, which caught a genuine bug (`| lower` applied to a
  bool) that YAML parsing alone would have missed
- **The pinned LiteLLM image was run locally against a real Postgres** — this is where the three
  design-changing findings came from (see `research.md` D-105, D-109)

## The three things most likely to bite you

1. **`T026` — the tailnet proxy path is unproven.** Does LiteLLM's httpx honour `HTTP_PROXY` on the
   `ollama_chat` provider path? Expected yes, never tested. If not, fall back to `ALL_PROXY` with
   the SOCKS5 listener (research D-102). Schedule this early — it can change the compose file.
2. **`T034`/`T035` — the downed-backend drills.** These exercise a known upstream LiteLLM
   routing-pool defect against the exact pinned version. `T035` (Mac powered off) is a genuinely
   different failure mode from `T034` (daemon stopped): a stopped daemon refuses fast, a vanished
   tailnet peer can hang to timeout. Both must pass.
3. **Environment state** — see [`quickstart.md`](./quickstart.md) § 0b. Ollama is bound to
   localhost, unwarmed, and serving a 4096 context; `pve`'s Tailscale is logged out. All three
   block or silently degrade the deploy.

## Blocked on you (cannot be derived)

- **The Mac's MagicDNS name** — two `api_base` placeholders in
  `ansible/group_vars/services/vars.yml`. Unreadable from the Mac (Zscaler); read it from the
  Tailscale menu bar or admin console.
- **Vault secrets** — `ansible-vault edit ansible/group_vars/services/vault.yml`:
  `openrouter_api_key`, `anthropic_api_key`, `litellm_master_key`, `litellm_db_password`,
  `tailscale_authkey` (reusable + ephemeral + tagged), `llm_router_client_hermes_key`,
  `llm_router_canary_key`. The three `llm_router_*`/`litellm_master_key` values **must start with
  `sk-`** — LiteLLM rejects keys without that prefix (confirmed by testing).
  Generate: `echo "sk-$(openssl rand -hex 24)"`.

`vault.yml` is tracked and encrypted in git, so editing locally and committing is the correct
flow — `pve` picks it up on checkout.

> **Superseded 2026-09-14 by [`deploy-plan.md`](./deploy-plan.md).** The old Mac is
> being returned, the local tier moved to oMLX over the LAN
> ([`amendment-local-tier-omlx.md`](./amendment-local-tier-omlx.md)), and Zscaler now
> blocks the interactive Tailscale login as well as pushes. The section below is kept
> for its IPs and prerequisites; the machine-by-machine split is in `deploy-plan.md`.

## Deploying from the Linux laptop

Needs: `gh` authenticated, `ansible` + the vault password file, SSH to `pve` (192.168.1.112).
If the laptop is **not** behind Zscaler, plain `git push` and `gh pr create` should just work —
none of the `AGENTS.md` workarounds apply.

LAB lands on `192.168.20.219`, PROD on `192.168.1.220`.

```bash
gh workflow run lxc-deploy-lab.yml --ref main -f service=llm-router -f apply=false
```

## Deliberately not done

- **`docs/backlog/066-prod-inventory-monitoring-gap.md`** — `market-model` and `eurooffice` are
  missing from `ansible/inventories/prod/hosts.yml`, so they are probably unmonitored in prod.
  Found during this work, unrelated to it, filed rather than drive-by fixed.
- **`pve` Tailscale re-login** — needs a browser on a non-Zscaler machine.
- **`T062`** — SC-011 verification needs a week of real operation before it can be checked.
