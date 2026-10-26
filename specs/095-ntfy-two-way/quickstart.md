# Quickstart / validation: Two-way ntfy (095)

Runbook-style checks. Each maps to a spec success criterion. Commands assume the tokens are
exported from vault on `pve` or a laptop (constitution V); never paste them into chat or logs.
The LAB rig (10.99.0.10) is reachable only from `pve` (research R-015).

## 0. LAB gate (before any PROD change)

### 0.1 Bring the rig up (research R-015)

Preconditions (research R-016): `bash scripts/ci/python-tests.sh` is green on this branch with
T070 (`test_hermes_env_modes.py`, credential freeze) and T071 (confidence-suite held-rig guard)
in it. The rig runs with production router and Hermes identities; only ntfy is LAB-specific.
Plan to bring it up, run § 0.2 and tear it down (§ 0.3) on the same day.

1. `ntfy` carries the scratch pair: deploy it from this branch through `Prod 1 - LXC Promote` →
   `Prod 2 - LXC Apply`, then run § 1 with `NTFY_HERMES_LAB_TOKEN` set (T067).
2. `gh workflow run lab-rig.yml --ref 095-ntfy-two-way -f action=up`. This clones the tier-2
   template, keeps the VM and probes ntfy and the LLM router from the rig. If either probe fails,
   stop and raise it; do not work around it in this branch.
3. `gh workflow run lab-rig.yml --ref 095-ntfy-two-way -f action=deploy`. The hermes role's LAB-rig
   guard must pass: the rendered `agent.env` holds only the scratch pair.

Laptop path (constitution V; a laptop cannot route to 10.99.x — and separately, before `main`
has ever seen `lab-rig.yml`, GitHub refuses to dispatch it at all, `workflow_dispatch` only
works once a workflow file exists on the default branch, no `--ref` override changes that):
`ssh ci@pve`, `cd ~/homelab-proxmox` (synced copy of the branch), then run the same commands the
workflow runs:

```bash
# Create the stable key FIRST if missing — `rebuild.sh` only reuses PROVISION_SSH_KEY when the
# file already exists; skip this and `pve-lab` silently falls back to an ephemeral key that it
# deletes on exit regardless of --keep, leaving a rig nothing can SSH into (found 2026-10-25).
if [[ ! -f "$HOME/.ssh/lab_rig_ed25519" ]]; then
  ssh-keygen -q -t ed25519 -N '' -C lab-rig-095 -f "$HOME/.ssh/lab_rig_ed25519"
fi
export PROVISION_SSH_KEY=$HOME/.ssh/lab_rig_ed25519
export ANSIBLE_VAULT_PASSWORD_FILE=/var/lib/homelab-proxmox/vault/.ansible_vault_pass
ANSIBLE_VAULT_PASSWORD="$(cat "$ANSIBLE_VAULT_PASSWORD_FILE")" \
  ARTIFACT_ROOT=/var/lib/homelab-proxmox/artifacts \
  scripts/lab/pve-lab run --profile hypervisor-control-plane --keep          # up
(cd ansible && ansible-playbook -i inventories/lab/hosts.yml playbooks/hermes_lab_rig.yml \
  --private-key "$PROVISION_SSH_KEY" -e deploy_environment=lab)            # deploy
scripts/lab/pve-lab status                                                # status
scripts/lab/pve-lab down                                                  # down
```

While the rig is up, `proxmox-apply.yml` and the confidence-suite job of `Prod 1 - LXC Promote`
refuse to run (the harness would destroy the rig).

### 0.2 Gate steps

On the LAB rig, deployed with the scratch pair (spec FR-011): the agent reads `hermes-lab-in` and
writes `hermes-lab` with the `hermes_lab` credential. Run `docker` commands on the rig
(`ssh -i ~/.ssh/lab_rig_ed25519 ansible@10.99.0.10` from `pve`). On the phone, subscribe to
`hermes-lab` for the duration of the test and send from `hermes-lab-in`. Research R-014 predicts every result below
from the v0.21.6 source; this run confirms it on the deployed image.

Use **flagged** commands only. A plain `rm` of one file inside the agent's home (`/opt/data/...`)
is not flagged upstream: the detector folds the home prefix to `~` before matching, so it runs
with no prompt (research R-014, LAB finding 2026-10-26). Recursive deletes, `chmod 777`, and
deletes outside the home (`/tmp`, `/etc`) are flagged. Before each step, create the scratch
directory on the rig:
`sudo docker exec -u hermes hermes_agent mkdir -p /opt/data/scratchdir && sudo docker exec -u hermes hermes_agent touch /opt/data/scratchdir/a`.

1. Send `run: rm -r /opt/data/scratchdir`. Expect a text approval prompt listing once, session
   (pattern), always (permanent), deny and the deadline (R-001, R-014).
2. Reply `/approve`. The directory is gone. Recreate it and repeat with `/deny`, then with no reply
   for the timeout: the directory remains each time.
3. Send `/yolo` and `/update`: both refused. Send `/help`: it lists exactly the spec FR-014 set.
   `/compress`, `/retry`, `/undo`, `/usage`, `/title` and `/model` each work.
4. `/approve session` on a scratch `rm -r`; a second `rm -r` (on a fresh scratch directory) runs
   without a prompt; `chmod 777` on a scratch file still prompts; `/new`; `rm -r` prompts again.
5. Ask for two flagged commands in one message. The second prompt appears only after the first is
   answered.
6. `/approve always` on a scratch `rm -r`. `docker logs hermes_agent | grep "via /approve (always)"`
   matches. After `docker restart hermes_agent`, the same `rm` prompts again.
7. Ask for a reply longer than 4096 characters. It arrives split into several notifications, or cut
   with a visible marker (spec US1 AS-4). If it is cut silently, stop and record it in R-014.
8. Check that `/opt/data/logs/gateway.log` on the rig has the four upstream audit lines
   (data-model § Audit lines): `inbound message:`, `via /approve (<scope>)`, `via /deny`, and
   `Slash command /yolo denied` (FR-009, research R-008 revised). That they reach Loki is checked
   at PROD rollout (T020), because the rig runs no Alloy.
9. Block the agent's egress to ntfy for 15 minutes (on the rig, an `iptables -I DOCKER-USER`
   reject rule for the ntfy address; remove it afterwards) and watch
   `docker logs hermes_agent | grep "Stream error"`: record the interval between error lines. If it
   exceeds 5 minutes, widen the `HermesNtfyStreamDown` range window to match.

If any step fails, stop. Slice 1's safety argument depends on all of them.

### 0.3 Tear the rig down

`gh workflow run lab-rig.yml --ref 095-ntfy-two-way -f action=down -f confirm=destroy-lab-rig`,
then `-f action=status` reports no lab VM (T069). Any other `confirm` value fails before anything
is destroyed. Do this the same day as § 0.1, also when § 0.2 fails or stalls; bring the rig up
again later rather than keep it (research R-016).

## 1. ACL matrix (SC-002)

```bash
scripts/healthcheck/ntfy-acl-check.sh   # extended with contracts/acl-matrix.md rows
```

Expect every cell of [contracts/acl-matrix.md](./contracts/acl-matrix.md). The critical cells:
`hermes` → `hermes-in` write = 403; `owner` → `hermes-in` write = 200.

## 2. Phone setup (once)

- In the ntfy app, on the existing `owner` account, subscribe to `hermes-in`, then mute it (your
  own messages need no alert).
- Keep `hermes` subscribed, unmuted.
- (P2) Subscribe to `relay`; `alerts` is already subscribed.

## 3. Chat and approvals (SC-001)

From the phone, on mobile data with Tailscale:

1. On `hermes-in`, send "what is the disk usage of your data dir?". A reply arrives on `hermes`.
2. Ask it to delete a scratch file, then run approve, deny and timeout (900 s). The outcomes match
   §0.
3. Run `/new`. The next message has no prior context.
4. `/approve always` on a scratch `rm`. Within 5 minutes `HermesPermanentApprovalGranted` arrives on
   Pushover. Run `docker restart hermes_agent`; the same `rm` prompts again (spec SC-001).

## 4. Offline gap (SC-003)

```bash
# on the hermes LXC
docker stop hermes_agent
# phone: send "are you there?" on hermes-in
docker start hermes_agent
```

Within 60 s a silent (priority 2) gap notice arrives on `hermes`. The "are you there?" message is
never answered.

## 5. Noise gone (SC-004)

In Grafana Explore (Loki): `{container="hermes_agent"} |= "Stream error"`. Expect zero results for
7 days after rollout.

## 6. Revocation (SC-006)

The phone app signs in with the owner **password**; the vault also holds an owner **token**. Rotate
both: new `ntfy_owner_password_hash` and `ntfy_owner_token` with `ansible-vault edit`, then deploy
`ntfy` once. Publish to `hermes-in` with the old password (`curl -u owner:<old>`) and with the old
token: both must return 403. Then update the phone's account with the new password. The runbook
lists this as the "phone lost" procedure.

## 7. Silence button (SC-005, P2)

1. Fire the test alert. The notification shows "Silence 1h", "Silence until 07:00" and
   "Silence 24h"; tapping the notification opens the alert's dashboard.
2. Press "Silence 1h". Within 30 s a confirmation arrives on `relay`, and exactly one silence
   exists (`amtool silence query`).
3. Publish the same command again by hand (`owner` token) with a past `exp`. The relay replies that
   the button expired, and the silence count is unchanged.
4. Stop the relay and press a button. Nothing confirms (owner sees no reply), and Pushover still
   delivers alerts.
5. Leave the relay stopped: within 10 min `NtfyActionRelayDown` arrives on Pushover. Start it again.
6. Fire the test alert again (the relay forgot it on restart), let it resolve, then press
   "Silence 1h" on its notification: exactly one silence is
   created and confirmed (flapping case, spec US5 AS-2).
