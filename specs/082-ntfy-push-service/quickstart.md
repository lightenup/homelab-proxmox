# Quickstart: validating ntfy (082)

These are runnable checks that prove the feature end to end. On **LAB**, run § 1, § 2 (against the
service's direct address) and § 6. On **PROD**, run all sections. § 3 is PROD only because monitoring
deploys through the prod promote path and the LAB monitoring gate refuses by design (`065`
precedent, backlog `072`). § 4–5 need the real phone.
Expected outcomes refer to [data-model.md](./data-model.md) and the [contracts](./contracts/).

**As run on 2026-10-17** (results in `tasks.md` and `drills/`): every step went through the
pipeline or over HTTP. The Linux dev box has **no SSH to the LXCs**, so `amtool` was replaced by
Alertmanager's v2 API and `docker stop` by a Proxmox shutdown. Both alternatives are given below.

## 0. Prerequisites

- Vault (`ansible/group_vars/services/vault.yml`) holds the six `ntfy_*` secrets (research R-012).
  To generate them:
  - Owner hash: `docker run --rm -it binwiederhier/ntfy:v2.28.0 user hash`. Enter the owner
    password, which then lives only in the password manager.
  - Publisher hashes: the same command with a random password that is thrown away afterwards.
  - Tokens: `docker run --rm binwiederhier/ntfy:v2.28.0 token generate`, three times.
- Load the three tokens into the shell for § 2–5 without printing them:

  ```bash
  eval "$(ansible-vault view --vault-password-file ansible/.vault-pass.txt ansible/group_vars/services/vault.yml \
    | python3 -c 'import sys,yaml,shlex;d=yaml.safe_load(sys.stdin);[print(f"export NTFY_{k[5:-6].upper()}_TOKEN={shlex.quote(d[k])}") for k in d if k.startswith("ntfy_") and k.endswith("_token")]')"
  ```

- `ntfy_enabled: true` is not yet set in `group_vars/monitoring/vars.yml`. It is enabled only in
  § 3, after ntfy is up.

## 1. Deploy and static checks

```bash
# Non-destructive first (constitution: plan-only validation)
scripts/lab/pve-service-deploy plan --environment lab --service ntfy   # creates exactly module.ntfy_lxc
ansible-playbook ansible/playbooks/ntfy.yml --check --diff
# Then the real deploy, via the pipeline dropdown or the same command locally (constitution V)
```

The pipeline sequence that was used:

```bash
gh workflow run lxc-deploy-lab.yml   --ref <branch> -f service=ntfy -f apply=false   # plan
gh workflow run lxc-deploy-lab.yml   --ref <branch> -f service=ntfy -f apply=true    # LAB
gh workflow run lxc-promote-lab.yml  --ref <branch> -f service=ntfy
gh workflow run lxc-promote-prod.yml --ref <branch> -f ref=<branch> -f service=ntfy
gh workflow run lxc-apply-prod.yml   --ref <branch> -f promotion_run_id=<promote run id> -f confirm_apply_prod=deploy-prod
gh workflow run lxc-deploy-lab.yml   --ref <branch> -f service=reverse_proxy -f apply=true  # Caddy route + card
```

LAB and PROD share one address space (backlog `067`), so the LAB apply already creates the live
container, and the PROD plan reports "No changes". Caddy obtains the `ntfy.hus-sky.no`
certificate by DNS-01 within about 75 s of the route appearing. Until then TLS fails with
"internal error".

Expected: the LXC exists at `ntfy_ip`, and `curl -s http://<ntfy_ip>/v1/health` returns
`{"healthy":true}`. Run the role a second time and it reports **no changes** (the hashes are stable,
R-012).

FR-004 invariant: `grep -E 'upstream|firebase|web-push' /opt/ntfy/server.yml` on the LXC returns
nothing. Preflight enforces this as well.

## 2. Access matrix (SC-002)

Run the scripted check, `scripts/healthcheck/ntfy-acl-check.sh`. It reads the tokens from
the environment and exits non-zero on any cell that differs from data-model § Access entry:

```bash
NTFY_URL=https://ntfy.hus-sky.no \
NTFY_OWNER_TOKEN=… NTFY_ALERTMANAGER_TOKEN=… NTFY_HERMES_TOKEN=… \
  scripts/healthcheck/ntfy-acl-check.sh
```

Expected: 20/20 cells match. Allowed writes go to a throwaway message and are visible in the
owner's read.

## 3. Alertmanager path

0. Template first, before enabling (T033):
   `NTFY_URL=https://ntfy.hus-sky.no specs/082-ntfy-push-service/drills/send-payloads.sh`
   should report 0 failures.
1. Set `ntfy_enabled: true` and deploy monitoring **through the prod path only**:
   `lxc-promote-prod` with `-f service=monitoring -f allow_override_failed_lab_gate=true`, then
   `lxc-apply-prod`. The LAB half refuses by design ("Refusing to deploy monitoring") and the
   override carries the chain on (backlog `072`). Compare `/api/v1/targets` and `/api/v1/rules`
   before and after: expect +4 targets and +1 rule group (`ntfy_alerts`), with nothing lost.
2. Render with the flag off and confirm the diff is empty (gate check, contracts/alertmanager-webhook.md).
3. Fire synthetic alerts with `amtool alert add` on the monitoring LXC, or without SSH by POSTing
   to `http://<monitoring>:9093/api/v2/alerts` with an `endsAt` two minutes out. Send one per row of
   data-model § Alert → notification mapping, then resolve them. Expected: titles and priorities
   exactly as in the table, and every alert also arrives on Pushover.
4. Size limit (R-004): add 10 alerts that share an `alertname` and carry long descriptions.
   Expected: one notification with 10 summary lines, and no 413 in the ntfy logs
   (`docker logs ntfy`).

## 4. Phone (PROD, US-3, SC-001, SC-005)

Follow `docs/runbooks/ntfy-phone-setup.md`, including the switch to WebSockets. Then:

1. With Wi-Fi off and Tailscale on, open `https://ntfy.hus-sky.no/v1/health` in the phone browser.
   Expected: healthy. This confirms tailnet reach to the reverse proxy (R-013).
2. With the app closed, publish to `hermes` with the hermes token. Expected: it arrives within 60 s.
3. Turn Tailscale off, publish, wait 5 min, turn Tailscale on. Expected: the message arrives after
   the reconnect.
4. Leave the phone idle overnight and publish in the morning. Expected: it arrives without the app
   being opened (SC-005).
5. Repeat § 3.3 for each severity on mobile data (SC-001).

## 5. Failure independence (SC-003, R-005 drill)

1. Baseline: fire a critical test alert and note how long Pushover takes to deliver it.
2. Stop ntfy: run `docker stop ntfy` on the LXC, or shut down `ntfy-lxc` in the Proxmox UI. Confirm it is
   down (Caddy returns 502), then fire another critical test alert. Expected: Pushover delivery time
   matches the baseline.
3. Wait at least 5 min. Expected: `NtfyDown` arrives on Pushover, and the front-page card shows
   `down`.
4. Run `docker start ntfy`. Expected: the resolution arrives on Pushover, the card shows `up`, and
   the ntfy copy of the alert arrives once Alertmanager's retries succeed.

If step 2 shows a delay, apply the fallback in research R-005 before closing the feature.

## 6. Rebuild (SC-004)

Destroy and recreate the LXC through the normal lifecycle path, then run the playbook. Expected,
with no manual step: § 2 passes, and a test publish reaches the already-subscribed phone (PROD).

## 7. Trial window (SC-006)

Over 4 weeks, record every alert with its time on Pushover and on ntfy (missed, late, duplicate).
Write the comparison up in `specs/082-ntfy-push-service/trial-report.md` as input to the
"drop Pushover?" decision.
