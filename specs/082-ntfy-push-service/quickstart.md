# Quickstart: validating ntfy (082)

These are runnable checks that prove the feature end to end. On **LAB**, run § 1, § 2 (against the
service's direct address) and § 6. On **PROD**, run all sections. § 3 is PROD only because monitoring
deploys through the prod promote path and the LAB monitoring gate refuses by design (`065`
precedent, backlog `072`). § 4–5 need the real phone.
Expected outcomes refer to [data-model.md](./data-model.md) and the [contracts](./contracts/).

## 0. Prerequisites

- Vault (`ansible/group_vars/services/vault.yml`) holds the six `ntfy_*` secrets (research R-012).
  To generate them:
  - Owner hash: `docker run --rm -it binwiederhier/ntfy:v2.28.0 user hash`. Enter the owner
    password, which then lives only in the password manager.
  - Publisher hashes: the same command with a random password that is thrown away afterwards.
  - Tokens: `docker run --rm binwiederhier/ntfy:v2.28.0 token generate`, three times.
- `ntfy_enabled: true` is not yet set in `group_vars/monitoring/vars.yml`. It is enabled only in
  § 3, after ntfy is up.

## 1. Deploy and static checks

```bash
# Non-destructive first (constitution: plan-only validation)
scripts/lab/pve-service-deploy plan --environment lab --service ntfy   # creates exactly module.ntfy_lxc
ansible-playbook ansible/playbooks/ntfy.yml --check --diff
# Then the real deploy, via the pipeline dropdown or the same command locally (constitution V)
```

Expected: the LXC exists at `ntfy_ip`, and `curl -s http://<ntfy_ip>/v1/health` returns
`{"healthy":true}`. Run the role a second time and it reports **no changes** (the hashes are stable,
R-012).

FR-004 invariant: `grep -E 'upstream|firebase|web-push' /opt/ntfy/server.yml` on the LXC returns
nothing. Preflight enforces this as well.

## 2. Access matrix (SC-002)

Run the scripted check, `scripts/healthcheck/ntfy-acl-check.sh` (planned). It reads the tokens from
the environment and exits non-zero on any cell that differs from data-model § Access entry:

```bash
NTFY_URL=https://ntfy.hus-sky.no \
NTFY_OWNER_TOKEN=… NTFY_ALERTMANAGER_TOKEN=… NTFY_HERMES_TOKEN=… \
  scripts/healthcheck/ntfy-acl-check.sh
```

Expected: 20/20 cells match. Allowed writes go to a throwaway message and are visible in the
owner's read.

## 3. Alertmanager path

1. Set `ntfy_enabled: true` and run `ansible-playbook ansible/playbooks/monitoring.yml`.
2. Render with the flag off and confirm the diff is empty (gate check, contracts/alertmanager-webhook.md).
3. Fire synthetic alerts from the monitoring LXC with `amtool alert add`, one per row of
   data-model § Alert → notification mapping, then resolve them. Expected: titles and priorities
   exactly as in the table, and every alert also arrives on Pushover.
4. Size limit (R-004): add 10 alerts that share an `alertname` and carry long descriptions.
   Expected: one notification with 10 summary lines, and no 413 in the ntfy logs
   (`docker logs ntfy`).

## 4. Phone (PROD, US-3, SC-001, SC-005)

Follow `docs/runbooks/ntfy-phone-setup.md` (planned). Then:

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
2. Run `docker stop ntfy`, then fire another critical test alert. Expected: Pushover delivery time
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
