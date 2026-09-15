# `064-llm-router` — command-by-command

Execute from the **Linux laptop** unless a step says otherwise. Branch
`064-llm-router-handoff` is already checked out there.

Two steps run elsewhere and are called out explicitly: **§1 on the new Mac**, and
**§2 on `pve` over SSH**.

Verified before writing: none of this branch's changed files touch a protected
path (`.specify/**`, `adapter/**`, `scripts/lab/**`, `mkdir/**`), so **no
`allow-protected-path-changes` label is needed** on the PR.

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

## 1 · NEW MAC — expose oMLX (prerequisite, not optional)

**Run on `xmjdvvw39y2t`, not the laptop.** Everything after §4 fails without it.

In the oMLX UI: **Settings → Server → Host** → `0.0.0.0`, restart the server.

```bash
lsof -nP -iTCP:8000 -sTCP:LISTEN
#   want:  *:8000            (LISTEN)
#   wrong: 127.0.0.1:8000    (LISTEN)

curl -s localhost:8000/admin/api/models \
  | python3 -c "import json,sys;[print(f\"{m['id']:26} loaded={m['loaded']} pinned={m['pinned']}\") for m in json.load(sys.stdin)['models'] if m['loaded']]"
#   Qwen3.8-27B-8bit           loaded=True pinned=True
#   Qwen3.8-27B-oQ4e-mtp       loaded=True pinned=True
```

Both **must** be `pinned=True`. An unpinned model can be evicted; the cold load
that follows trips the gateway timeout into a *false* fallback (FR-016).

---

## 2 · `pve` — authenticate onto the tailnet

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
| `tailscale_authkey` | **reusable + ephemeral + tagged** — for the LXC sidecar, a *different* key from §2a |

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

**That second command is the gate.** It proves `pve` resolves the Mac's mDNS name
*and* reaches oMLX on the LAN. If it fails:

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

Expect all green. Also run the existing liveness check — it answers a different
question and is what the pipeline gates on:

```bash
./scripts/healthcheck/llm-router.sh --profile lan
```

---

## 7 · Fault-inject — the step that makes the doctor trustworthy

Full detail in [`doctor-fault-injection.md`](./doctor-fault-injection.md).
**Green is the starting point, not the finish.** Restore after each.

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
