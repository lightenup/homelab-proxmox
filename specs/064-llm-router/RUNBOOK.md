# `064-llm-router` — command-by-command

Execute from the **Linux laptop** unless a step says otherwise. Branch
`064-llm-router-handoff` is already checked out there.

Two steps run elsewhere and are called out explicitly: **§1 on the new Mac** — written as a
self-contained brief to hand to an agent there — and **§2 on `pve` over SSH**.

Verified before writing: none of this branch's changed files touch a protected
path (`.specify/**`, `adapter/**`, `scripts/lab/**`, `mkdir/**`), so **no
`allow-protected-path-changes` label is needed** on the PR.

---

## Revision 2026-09-15 — read this before executing

**§1 and §2 are not prerequisites for the LAB deploy, and §4's gate does not apply
to it.** LAB is `192.168.20.219`; the Mac is on `192.168.1.0/24`; mDNS is multicast
and does not cross subnets. LAB cannot reach the local tier by any configuration, so
the local tier is deployed configured-and-unreachable by decision, not by accident.
Rationale and the PROD consequence: [`deploy-plan.md`](./deploy-plan.md) § *LAB and
the local tier*.

**Design change 2026-09-15, LANDED in config:** the metered tiers (OpenRouter, Anthropic)
have been dropped and the local tier re-chained through the **Mac's own LiteLLM** on `:4000`
rather than oMLX on `:8000`. SC-001 is withdrawn — the Mac becomes a dependency, and the
gateway fails clean when it is away. The alias mapping, `spec.md`, the doctor and §1 are all
rewritten for this; the anchor is [`amendment-drop-metered-tiers.md`](./amendment-drop-metered-tiers.md).

**§1 on the Mac is now DONE (2026-09-16):** LiteLLM is rebound to `0.0.0.0:4000` and the
LXC's virtual key (`mac_litellm_key`) is minted — see §1's status banner and the amendment.
**The remaining live steps are: §3 the vault** (`mac_litellm_key` in, the three metered keys
out) **then §5 the LAB deploy.** If the Mac has been restarted since 2026-09-16, run §1's
*"Resume after a Mac restart"* block first to bring Docker + oMLX back and re-verify the LAN
path.

**The only hard prerequisite for LAB is §3, the vault** — and it is two keys shorter
than the table below was first written for: the tailscaled sidecar has been removed, so
`tailscale_authkey` is not needed, and the metered tiers are gone, so neither
`openrouter_api_key` nor `anthropic_api_key` is consumed any more. The local tier's key is
now `mac_litellm_key`, not `omlx_api_key`.

Four role bugs were fixed on 2026-09-15 that would each have failed this deploy —
the preflight FR-013 assertion still required `.ts.net`, `OMLX_API_KEY` was never
passed to the container, `HTTP_PROXY` still diverted the backend leg through the
Tailscale sidecar, and the doctor's residency check could not fail. Fixed and
fault-injected; the runbook below is otherwise unchanged.

Two things it still says that are now wrong are marked inline below.

---

## 0 · Laptop — confirm you have the right tree

```bash
cd ~/path/to/homelab-proxmox
git rev-parse --abbrev-ref HEAD                 # 064-llm-router-handoff
git log --oneline -2
#   5469240 fix(llm-router)!: land the oMLX amendment in the role, drop the tailscaled sidecar
#   1b24518 docs(064): command-by-command runbook for the LAB deploy

./scripts/healthcheck/llm-router-doctor.py --list
#   alias hermes-fast        -> [local]  fallback=None
#   alias hermes-balanced    -> [local]  fallback=None
#   alias hermes-deep        -> [local]  fallback=None

./scripts/healthcheck/llm-router-doctor.py --layer config
#   expect 5/5
```

If `--layer config` is not 5/5, stop — the tree is wrong.

---

## 1 · NEW MAC — expose the LiteLLM gateway  *(brief for an agent on the Mac)*

> ## ✅ STATUS: DONE on the Mac — 2026-09-16
>
> Both jobs were executed on `XMJDVVW39Y2T` (192.168.1.177) itself. Full write-up:
> [`amendment-drop-metered-tiers.md`](./amendment-drop-metered-tiers.md) § *Executed on
> the Mac*. Summary:
>
> - **Job 1 — LiteLLM rebound to `0.0.0.0:4000`.** It runs via `docker compose` at
>   `~/Development/private/local-llm/proxy`; `docker-compose.yml` line ~45 changed
>   `127.0.0.1:4000:4000` → `0.0.0.0:4000:4000`, `docker compose up -d`. Verified `*:4000`,
>   healthy, answers on loopback **and** the LAN IP; `fast`/`coder`/`reasoner` serve over the
>   LAN. **oMLX stayed on `127.0.0.1:8000`.** macOS firewall untouched (Docker already
>   permitted inbound).
> - **Job 2 — virtual key minted.** `key_alias: homelab-lxc-064-llm-router`, scoped
>   `models: ["local"]`. **This is the vault's `mac_litellm_key`.** The plaintext was handed
>   over out-of-band on 2026-09-16; it is **not recoverable from Postgres** (only its hash is
>   stored). If it was not saved, **re-mint** — see the restart-recovery block below.
>
> ### ⟳ Resume after a Mac restart (do this first when the Mac comes back)
>
> Nothing here auto-starts reliably: **Docker Desktop is not a login item**, and **oMLX is a
> GUI app**. Bring the stack back, then confirm the LAN path, before touching the deploy:
>
> ```bash
> open -a Docker            # wait for the whale icon to settle; containers are unless-stopped
> open -a oMLX              # auto_start_on_launch:true — its server comes up on 127.0.0.1:8000
>
> # once both are up, verify (from the Mac):
> lsof -nP -iTCP:4000 -sTCP:LISTEN                                   # want *:4000
> lsof -nP -iTCP:8000 -sTCP:LISTEN                                   # want 127.0.0.1:8000 (NOT *)
> curl -s -m5 http://192.168.1.177:4000/health/liveliness           # "I'm alive!"
> cd ~/Development/private/local-llm/proxy && set -a && . ./.env && set +a
> for a in fast coder reasoner; do curl -s -m60 http://192.168.1.177:4000/v1/chat/completions \
>   -H "Authorization: Bearer $LITELLM_MASTER_KEY" -H 'Content-Type: application/json' \
>   -d "{\"model\":\"$a\",\"max_tokens\":8,\"messages\":[{\"role\":\"user\",\"content\":\"ok\"}]}" \
>   -o /dev/null -w "$a %{http_code}\n"; done                        # each 200
> ```
>
> Check oMLX re-pinned the aliased models (residency, FR-016) after the cold boot — it drives
> `~/.omlx/model_settings.json`. Confirm `Qwen3.8-27B-8bit` and `Qwen3.8-27B-oQ4e-mtp` are
> loaded in the oMLX UI. *(Note: this cannot be scripted with `OMLX_API_KEY` — `/admin/api/models`
> needs a separate admin credential not in `proxy/.env`; see the amendment's findings.)*
>
> **If the minted key was lost**, re-mint an identical one and re-vault it:
>
> ```bash
> cd ~/Development/private/local-llm/proxy && set -a && . ./.env && set +a
> curl -s -X POST http://127.0.0.1:4000/key/generate -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
>   -H 'Content-Type: application/json' \
>   -d '{"models":["local"],"key_alias":"homelab-lxc-064-llm-router-v2"}' | python3 -m json.tool
> ```
>
> ### ✅ Job 3 — the `.local` name, done 2026-09-19
>
> FR-013 addresses the Mac by its mDNS name, and that name **did not resolve from anywhere
> in the homelab**. The LAN path was always fine (`curl` to `192.168.1.177:4000` answered
> from `pve` throughout); only the name was broken. Cause, measured rather than assumed:
> **the Mac announces its mDNS records but never answers a query** — not multicast, not
> unicast to its own `:5353`. A resolver that hears an announcement caches it and works; a
> resolver with a cold cache can never learn the name. The app firewall already permits
> `mDNSResponder` inbound, so the drop is MDM-enforced stealth mode
> (`/Library/Managed Preferences/com.apple.security.firewall`) or the Zscaler filter —
> corporate controls, not ours to change, and **not needing change**, because announcing is
> the half that already works.
>
> Fixed by keeping the Mac announcing: a LaunchAgent re-registers the real `:4000` service
> every 45 s, and each registration's announcement carries the host `A` record. Full
> write-up, install and verify steps:
> [`mac-mdns-announcer/README.md`](./mac-mdns-announcer/README.md).
>
> ```bash
> launchctl list | grep hermes      # no.hus-sky.hermes-mdns-announce, last exit 0
> ```
>
> Verified from `pve` against a **flushed** avahi cache (a warm cache proves nothing here —
> that is what hid this for so long): resolves in under 2 s, stayed resolved across a 100 s
> poll, and §4's gate returns HTTP 200 by name. Two role changes go with it, both landed:
> `mdns_base` in `ansible/playbooks/llm-router.yml`, and `network_mode: host` on the litellm
> container — Docker's embedded DNS never consults host NSS, so `libnss-mdns` on the LXC is
> invisible to a bridge-network container.
>
> **What's left after this** is off-Mac: §3 (vault `mac_litellm_key`, drop the metered keys)
> then §5 (LAB deploy). The rest of §1 below is the original brief, kept for provenance.

---

> **Supersedes the old §1** (expose oMLX on `0.0.0.0`). Design changed 2026-09-15: the
> homelab gateway now chains to **this Mac's LiteLLM**, not to oMLX directly. **oMLX must
> stay on `127.0.0.1:8000` — do not expose it.**

---

**Copy everything below to an agent running on `xmjdvvw39y2t` (192.168.1.177).**

You are on a Mac that runs LiteLLM in front of local models (oMLX). A gateway LXC in the
homelab needs to reach this LiteLLM over the LAN. It currently binds `127.0.0.1:4000`
(confirmed by `lsof`), so it is unreachable. Two jobs: rebind it, and report its config.

**Job 1 — bind LiteLLM to `0.0.0.0:4000`.** Find how it is launched, then change that one thing:

```bash
lsof -nP -iTCP:4000 -sTCP:LISTEN
ps aux | grep -i litellm | grep -v grep
launchctl list 2>/dev/null | grep -i litellm
```

| launched via | change |
|---|---|
| `litellm --host 127.0.0.1` | `--host 0.0.0.0` |
| `docker compose` | `ports:` → `"4000:4000"`, not `"127.0.0.1:4000:4000"` |
| a `host:` key in the LiteLLM config | set it to `0.0.0.0` |
| launchd plist | edit the `ProgramArguments` host flag, then `launchctl kickstart -k` the service |

Restart, then verify — **both** lines must pass:

```bash
lsof -nP -iTCP:4000 -sTCP:LISTEN            # want *:4000, NOT 127.0.0.1:4000
curl -s -m5 http://192.168.1.177:4000/health/liveliness   # must answer from the LAN IP, not just localhost
/usr/libexec/ApplicationFirewall/socketfilterfw --getglobalstate
```

If `lsof` shows `*:4000` but the LAN-IP curl fails, it is the macOS firewall — allow the
LiteLLM binary inbound, do not disable the firewall.

**Do NOT** expose oMLX. Leave `:8000` on `127.0.0.1`. Only LiteLLM talks to it.

**Job 2 — report these back**, so the homelab side can map its aliases onto yours:

```bash
KEY=<a LiteLLM key on this host>
curl -s localhost:4000/v1/models -H "Authorization: Bearer $KEY"
curl -s localhost:4000/model/info -H "Authorization: Bearer $KEY"
```

Report:
1. Every **alias name** served (the doc on file says `coder`, `reasoner`, `fast`, `diagram` —
   confirm and correct), and the model + profile behind each. One is believed to be a
   long-context profile, possibly named `Long` — name it exactly.
2. Which alias is the **long-context / highest-reasoning** one. It will back `hermes-deep`.
3. `router_settings` — `fallbacks`, `context_window_fallbacks`, `enable_pre_call_checks`.
4. The declared `context_window` / `max_input_tokens` per alias, if set.
5. **Whether you can mint a virtual key** for the LXC (`POST /key/generate`), rather than
   sharing the master key. Preferred: a virtual key scoped to the aliases above. Report the
   key out-of-band, not in a shared transcript.

Do not change any model, alias, fallback or budget setting on this host. Job 1 is the only
edit. Everything else is read-and-report.

---

## 2 · `pve` — authenticate onto the tailnet

> **Not required for the LAB deploy, but now REQUIRED before PROD** (revision
> 2026-09-15). The local tier is LAN-addressed, so no backend leg crosses the
> tailnet and nothing here gates the LAB run. But with the LXC's tailscaled sidecar
> removed, `pve`'s subnet route is the *only* tailnet path to the gateway — so this
> step is now the whole of FR-008's tailnet reach, not a redundant second path.
> FR-008 is unsatisfied over the tailnet until it is done. See FR-017 (withdrawn).

### 2a · Laptop — generate a tagged auth key

Browser → `login.tailscale.com` → **Settings → Keys → Generate auth key**

- **Reusable**: no (one-shot is fine for `pve`)
- **Ephemeral**: **no** — `pve` is a permanent node
- **Tags**: **`tag:proxmox`** ← without this the subnet route will not auto-approve

Copy the `tskey-auth-…` value.

### 2b · `pve` over SSH

```bash
ssh ci@192.168.1.112

sudo tailscale up --authkey=tskey-auth-XXXXXXXX \
  --accept-routes \
  --advertise-routes=192.168.1.0/24 \
  --advertise-tags=tag:proxmox
```

All four flags are required together. `tailscale up` refuses to silently drop
non-default flags, which is what stopped the earlier attempt — and correctly, because
`docs/tailscale/policy.hujson` auto-approves `192.168.1.0/24` **only** for
`tag:proxmox`. Untagged, the route sits pending in the console and the subnet
router does nothing while appearing fine.

### 2c · `pve` — verify

```bash
tailscale status | head -3                        # a 100.x address, not "Logged out"
sudo tailscale debug prefs | grep -iA2 -e Advertise
ip route | grep 192.168.1
```

Then in the admin console: **Machines → pve → Route settings** — `192.168.1.0/24`
must read **approved**, not pending. Pending means the tag did not apply.

---

## 3 · Laptop — vault secrets

```bash
ansible-vault edit ansible/group_vars/services/vault.yml
```

| key | note |
|---|---|
| `litellm_master_key` | `sk-` prefix **required** |
| `llm_router_client_hermes_key` | `sk-` prefix **required** |
| `llm_router_canary_key` | `sk-` prefix **required** |
| `mac_litellm_key` | **the local tier's key** — a virtual key the Mac's LiteLLM mints for the LXC (§1, `POST /key/generate`), scoped to `fast`/`coder`/`reasoner`. `sk-` prefix. Replaces `omlx_api_key`. |
| `litellm_db_password` | |

> ~~`omlx_api_key`~~, ~~`openrouter_api_key`~~, ~~`anthropic_api_key`~~ — **no longer
> consumed** (2026-09-15). The gateway no longer talks to oMLX directly, and the metered
> tiers are gone, so no deployment names any of these. Drop them from the vault. See
> [`amendment-drop-metered-tiers.md`](./amendment-drop-metered-tiers.md).
>
> ~~`tailscale_authkey`~~ — **no longer needed** (2026-09-15). The LXC's tailscaled
> sidecar was removed; nothing in the repo consumes this variable any more. Do not
> generate one.

```bash
for i in 1 2 3; do echo "sk-$(openssl rand -hex 24)"; done
```

LiteLLM rejects keys without `sk-`. Confirmed by testing during 064.

```bash
git add ansible/group_vars/services/vault.yml
git commit -m "chore(064): populate llm-router vault secrets"
git push                                   # plain push works here, no Zscaler
```

---

## 4 · Laptop — preflight, the check that matters

```bash
./scripts/healthcheck/llm-router-doctor.py --layer config    # 5/5

ssh root@192.168.1.112 "curl -s -m5 http://xmjdvvw39y2t.local:4000/health/liveliness"
#   HTTP 200 from the Mac's LiteLLM (oMLX stays on 127.0.0.1:8000, do not probe it)
```

> **Passes as of 2026-09-19** — `"I'm alive!"`, HTTP 200, by name, once the Mac's mDNS
> announcer is running (§1 Job 3). It was failing before that, and the failure was the
> name, not the path.
>
> **Still the wrong gate for LAB** (revision 2026-09-15). This tests **`pve`'s**
> resolver — a different machine from the LXC, and a different resolver from the Docker
> container that makes the actual call. For LAB it is moot entirely: mDNS does not cross
> into `192.168.20.0/24`. Treat it as a PROD check. The container half of the problem is
> now closed rather than open — `network_mode: host` plus `mdns_base` puts the container
> on the LXC's own resolver, so on PROD this check and the real path finally test the
> same thing.

**That second command was written as the gate.** It proves `pve` resolves the Mac's
mDNS name *and* reaches the Mac's **LiteLLM** on the LAN (not oMLX — that stays on
`127.0.0.1`). If it fails:

| symptom | cause |
|---|---|
| connection refused | §1 not done — the Mac's LiteLLM still on `127.0.0.1:4000` |
| name not resolved | avahi not resolving `.local` from `pve` — try the Mac's IP to isolate |
| timeout | Mac asleep, or off the LAN |

Do not deploy until this returns healthy.

---

## 5 · Laptop — deploy to LAB

Plan first. The workflow checks out whatever `--ref` you dispatch, so it runs
this branch without merging.

```bash
gh workflow run lxc-deploy-lab.yml \
  --ref 064-llm-router-handoff \
  -f service=llm-router -f apply=false

gh run watch $(gh run list --workflow=lxc-deploy-lab.yml --limit=1 --json databaseId --jq '.[0].databaseId')
```

Read the plan. If it shows **replace** or **destroy**, stop and understand why
before continuing.

```bash
gh workflow run lxc-deploy-lab.yml \
  --ref 064-llm-router-handoff \
  -f service=llm-router -f apply=true

gh run watch $(gh run list --workflow=lxc-deploy-lab.yml --limit=1 --json databaseId --jq '.[0].databaseId')
```

LAB lands on **`192.168.20.219`**.

---

## 6 · Laptop — verify the deploy

```bash
export LLM_ROUTER_CANARY_KEY="sk-..."          # the canary key from §3

./scripts/healthcheck/llm-router-doctor.py \
  --base-url http://192.168.20.219:4000 \
  --json /tmp/doctor-lab.json
```

**Expect the two local-tier checks to go RED in LAB** (revision 2026-09-15):
`Mac LiteLLM reachable on the LAN` and `every alias maps onto a live Mac role alias`
both fail from LAB's subnet, correctly — the Mac is on `192.168.1.0/24` and mDNS does
not cross into `192.168.20.0/24`.

**SC-001 is WITHDRAWN, so the aliases will ALSO fail clean in LAB.** With the metered
tiers gone there is no fallback: the Mac is the only backend, and from LAB it is
unreachable, so each `alias answers` gateway check returns a **prompt error naming the
unreachable backend, not a hang**. That failing-clean-within-the-health-interval *is*
the property to confirm in LAB — a hang is the only real failure. The full alias-serving
proof now belongs to PROD, which shares the Mac's subnet.

What must still be GREEN in LAB: the whole **config** layer and the gateway's own
`endpoint answers` liveness. Those prove the deploy itself is sound independent of the Mac.

Also run the existing liveness check — it answers a different
question and is what the pipeline gates on:

```bash
./scripts/healthcheck/llm-router.sh --profile lan
```

---

## 7 · Fault-inject — the step that makes the doctor trustworthy

Full detail in [`doctor-fault-injection.md`](./doctor-fault-injection.md).
**Green is the starting point, not the finish.** Restore after each.

> **Rows 1–3 need the Mac and therefore need PROD** (revision 2026-09-15). In LAB
> the local tier is already unreachable, so row 1 is the steady state and row 2 is the
> steady state. Rows 4 and 5 run in LAB today. Row 3 (residency/pinning) can no longer
> be observed from here at all — oMLX is behind `127.0.0.1` on the Mac — so it moved to
> the **Mac side of §1** and is verified there, not by this doctor.

| # | where | break | expect |
|---|---|---|---|
| 1 | new Mac | stop the Mac's LiteLLM | `Mac LiteLLM reachable on the LAN` → **FAIL** |
| 2 | laptop | with the Mac's LiteLLM still stopped, re-run the doctor | **every alias FAILS CLEAN** — an error naming the backend, never a hang ← inverted |
| 3 | new Mac | (on the Mac) unpin `Qwen3.8-27B-oQ4e-mtp`, let it evict | Mac-side residency check in §1 → **FAIL** |
| 4 | laptop | run the doctor with a budget-less key | `calling key carries a budget` → **FAIL** |
| 5 | laptop | set `enable_pre_call_checks: false`, deploy | that check → **FAIL** |

**#2 is inverted and is the important one.** With the Mac's LiteLLM down, every alias
must **fail clean** — a prompt error attributing the failure to the unreachable backend,
returned within the health-check interval. A *hang* there is the real failure (SC-008,
rephrased); a clean error is the pass. SC-001's old "must still answer" expectation is
withdrawn — there is nothing left to fall back to.

Then **power the Mac fully off** and re-run. That is `T035`, a different failure
mode from a stopped server: a stopped LiteLLM refuses fast, a vanished host can
hang to timeout. Watch the wall clock; a hang is the result to catch.

Record which checks refused to go red — that is a finding, not a formality.

---

## 8 · Laptop — PR and PROD

```bash
gh pr create --base main --head 064-llm-router-handoff \
  --title "feat(llm-router): chain local tier through the Mac's LiteLLM, drop metered tiers" \
  --body "Re-chains 064's local tier from oMLX-direct to the Mac's own LiteLLM on :4000, and drops the metered tiers (OpenRouter, Anthropic). oMLX returns to 127.0.0.1. Withdraws SC-001/FR-004 (no fallback; fail clean), makes FR-010's spend half and SC-012 inert. Amends FR-014/016 and SC-008. Anchor: specs/064-llm-router/amendment-drop-metered-tiers.md. LAB deployed and fault-injected — see specs/064-llm-router/doctor-fault-injection.md for results."
```

No `allow-protected-path-changes` label needed — verified, nothing in this branch
touches a protected glob.

After merge, PROD lands on **`192.168.1.220`** via the promote workflow. Re-run §6
against that address.

---

## Removed from the old plan

| was | why |
|---|---|
| Ollama setup on the old Mac | that Mac is being returned |
| MagicDNS placeholder fill | replaced by mDNS `.local` |
| `T026` — `HTTP_PROXY` on `ollama_chat` | no `ollama_chat` path, no proxy hop on the backend leg |
| interactive Tailscale login from a Mac | Zscaler blocks it; tagged auth key from the laptop instead |
