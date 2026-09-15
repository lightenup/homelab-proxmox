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

**Design change 2026-09-15, pending:** the metered tiers (OpenRouter, Anthropic) are being
dropped and the local tier re-chained through the **Mac's own LiteLLM** on `:4000` rather
than oMLX on `:8000`. SC-001 is withdrawn — the Mac becomes a dependency, and the gateway
fails clean when it is away. §1 is rewritten for this; the alias mapping, `spec.md` and the
doctor are not yet. Do not run §5 onward until that lands.

**The only hard prerequisite for LAB is §3, the vault** — and it is one key shorter
than the table below was written for: the tailscaled sidecar has been removed, so
`tailscale_authkey` is not needed at all.

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
#   0201dcb Repoint 064's local tier to oMLX over the LAN, and replan the deploy
#   32b3db7 docs(llm-router): handoff notes, verified model mapping, environment findings

./scripts/healthcheck/llm-router-doctor.py --list
#   alias hermes-fast        -> [local,aggregator]  fallback=hermes-balanced
#   alias hermes-balanced    -> [local,aggregator]  fallback=hermes-deep
#   alias hermes-deep        -> [frontier]  fallback=None

./scripts/healthcheck/llm-router-doctor.py --layer config
#   expect 5/5
```

If `--layer config` is not 5/5, stop — the tree is wrong.

---

## 1 · NEW MAC — expose the LiteLLM gateway  *(brief for an agent on the Mac)*

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
| `omlx_api_key` | **new** — the local tier's key, from `~/.omlx/settings.json` → `auth.api_key` on the Mac |
| `openrouter_api_key` | |
| `anthropic_api_key` | API key only, never a subscription credential (FR-007) |
| `litellm_db_password` | |

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

ssh root@192.168.1.112 "curl -s -m5 http://xmjdvvw39y2t.local:8000/health"
#   {"status":"healthy",...}
```

> **Wrong for LAB** (revision 2026-09-15). This tests **`pve`'s** resolver — a
> different machine from the LXC, and a different resolver from the Docker container
> that makes the actual call. It can pass while the real path fails. For LAB it is
> moot entirely; treat it as a PROD check, and see `deploy-plan.md` for the
> container-resolution problem it does not cover.

**That second command was written as the gate.** It proves `pve` resolves the Mac's
mDNS name *and* reaches oMLX on the LAN. If it fails:

| symptom | cause |
|---|---|
| connection refused | §1 not done — oMLX still on `127.0.0.1` |
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

**Expect all green *except* the two local-tier checks** (revision 2026-09-15):
`oMLX reachable on the LAN` and `oMLX serves the declared context, resident` both
go red in LAB, correctly — the Mac is unreachable from that subnet.

**`every alias answers right now` must be GREEN.** That is SC-001, it is the point
of the LAB run, and a red there is a real failure of the fallback chain. A red local
tier alongside green aliases is the correct LAB result — fault-injection row 2,
arriving for free.

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
> the local tier is already unreachable, so row 1 is the steady state, row 2 is the
> steady state, and row 3 cannot be staged. Rows 4 and 5 run in LAB today.
> Row 3's check was verified against a simulated oMLX on 2026-09-15 and fails
> correctly on unpinned, evicted, and short-context — it is no longer unfailable.

| # | where | break | expect |
|---|---|---|---|
| 1 | new Mac | stop the oMLX server | `oMLX reachable on the LAN` → **FAIL** |
| 2 | laptop | with oMLX still stopped, re-run the doctor | **every alias still PASSES** ← inverted |
| 3 | new Mac | unpin `Qwen3.8-27B-oQ4e-mtp`, let it evict | `serves the declared context, resident` → **FAIL** |
| 4 | laptop | run the doctor with a budget-less key | `calling key carries a budget` → **FAIL** |
| 5 | laptop | set `enable_pre_call_checks: false`, deploy | that check → **FAIL** |

**#2 is inverted and is the important one.** With oMLX down, every alias must
still answer — that is SC-001 and the fallback working. A red there means the
fallback is broken, not the doctor.

Then **power the Mac fully off** and re-run. That is `T035`, a different failure
mode from a stopped server: a stopped server refuses fast, a vanished host can
hang to timeout. Watch the wall clock; a hang is the result.

Record which checks refused to go red — that is a finding, not a formality.

---

## 8 · Laptop — PR and PROD

```bash
gh pr create --base main --head 064-llm-router-handoff \
  --title "feat(llm-router): oMLX local tier over LAN, revised deploy plan" \
  --body "Repoints 064's local tier from Ollama-over-tailnet to oMLX-over-LAN; the original Mac is being returned. Amends FR-009/013/016/017, adds a behaviour-asserting doctor and a machine-by-machine deploy plan. LAB deployed and fault-injected — see specs/064-llm-router/doctor-fault-injection.md for results."
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
