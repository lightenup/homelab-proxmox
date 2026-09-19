# Deploy plan — who does what, and where

> **Revision 2026-09-15 — read first.** The local tier no longer talks to oMLX
> directly; it chains through the **Mac's own LiteLLM** on `:4000`, and the metered
> tiers (OpenRouter, Anthropic) are dropped. oMLX returns to `127.0.0.1:8000`. Where
> this file says "expose oMLX on `0.0.0.0:8000`", read "expose the Mac's LiteLLM on
> `0.0.0.0:4000`, keep oMLX on `127.0.0.1`"; where it names `omlx_api_key`,
> `openrouter_api_key` or `anthropic_api_key`, read the single `mac_litellm_key`; and
> where it relies on SC-001 fallback ("every alias must still answer"), note SC-001 is
> **withdrawn** — with no fallback the aliases now **fail clean**. Anchor:
> [`amendment-drop-metered-tiers.md`](./amendment-drop-metered-tiers.md). The
> machine-by-machine commands live in [`RUNBOOK.md`](./RUNBOOK.md), which is already
> rewritten for this; the sections below are kept for the four-machine model and the
> IPs.

**Revised 2026-09-14.** Supersedes the "Deploying from the Linux laptop" section
of [`HANDOFF.md`](./HANDOFF.md), which assumed the old Mac and an interactive
Tailscale login that Zscaler now blocks.

## The four machines

| machine | managed | Zscaler | role |
|---|---|---|---|
| **new Mac** `xmjdvvw39y2t` | EY | **yes** | runs oMLX, the local tier. LAN only. |
| old Mac | EY | yes | **being returned — out of the design** |
| **Linux laptop** | private | **no** | control plane: browser auth, `git push`, `gh`, ansible |
| **`pve`** `192.168.1.112` | — | — | Proxmox host, headless, SSH from the LAN |

**The rule that produces this split:** Zscaler blocks Tailscale *and* GitHub
pushes on both Macs, and does not touch LAN traffic. So anything needing a
browser against `login.tailscale.com`, or a `git push`, belongs on the Linux
laptop. Anything on the home LAN can happen from either.

---

## A · New Mac — expose oMLX to the LAN

One blocker. oMLX binds `127.0.0.1:8000`, so the LXC cannot reach it.

```
oMLX settings → server.host: 0.0.0.0 → restart the server
```

```bash
lsof -nP -iTCP:8000 -sTCP:LISTEN          # must be *:8000, NOT 127.0.0.1:8000
```

Both aliased models must be **pinned resident** (FR-016) — already done
2026-09-14 via `is_pinned` in the model settings payload. Confirm after any
restart:

```bash
curl -s localhost:8000/admin/api/models | python3 -c \
  "import json,sys;[print(m['id'],m['loaded'],m['pinned']) for m in json.load(sys.stdin)['models'] if m['loaded']]"
```

`Qwen3.8-27B-8bit` and `Qwen3.8-27B-oQ4e-mtp` must both show loaded **and**
pinned. An unpinned model can be evicted, and the resulting cold load trips the
gateway timeout into a *false* fallback — the gateway reports the Mac down when
it is merely slow.

**Nothing else happens on this machine.** No deploy, no Tailscale, no push.

---

## B · Linux laptop — authenticate `pve` onto the tailnet

> **Promoted to a PROD prerequisite 2026-09-15.** The LXC's tailscaled sidecar has been
> removed (FR-017 withdrawn), so this subnet route is now the only tailnet path to the
> gateway. FR-008's tailnet clause is unsatisfied until this is done. It still does not
> gate the LAB deploy.

`pve` is **deauthenticated but retains its config**: `tailscale status` reports
`Logged out` while `debug prefs` reports `"LoggedOut": false`. That is why
`tailscale up` validated flags instead of offering a fresh login, and why it
refused to drop `--advertise-tags=tag:proxmox`.

**Do not drop that tag.** `docs/tailscale/policy.hujson` auto-approves the
subnet route *only* for tagged devices:

```
"192.168.1.0/24": ["tag:proxmox"]      // auto-approve
"tag:proxmox": ["group:admins"]        // ownership
```

Untagged, the advertised route sits pending in the admin console and the subnet
router silently does nothing.

### Preferred: auth key, no browser

Tagged nodes need either an auth key carrying the tag, or an interactive login
by a member of `group:admins`. The key path is repeatable and is what the LXC
sidecar already uses.

On the **Linux laptop**, at `login.tailscale.com` → Settings → Keys, generate a
key with **`tag:proxmox` attached**. Then, on `pve`:

```bash
sudo tailscale up --authkey=tskey-auth-... \
  --accept-routes --advertise-routes=192.168.1.0/24 --advertise-tags=tag:proxmox
```

### Fallback: interactive

The URL `tailscale up` prints is **not tied to the machine that ran it** — paste
it into a browser on the Linux laptop and it authenticates `pve`. It expires, so
re-run `tailscale up` to get a fresh one if it lapses.

### Verify, on `pve`

```bash
tailscale status | head -3                        # a 100.x address, not "Logged out"
sudo tailscale debug prefs | grep -i advertise    # tag and route survived
```

Then in the admin console confirm the route shows **approved**, not pending. If
it is pending, the tag did not apply.

---

## C · Linux laptop — vault, verify, deploy

Needs `gh` authenticated, `ansible`, the vault password file, SSH to `pve`.
Not behind Zscaler, so plain `git push` and `gh pr create` work — none of
`AGENTS.md`'s workarounds apply here.

**C1 — secrets.**

```bash
ansible-vault edit ansible/group_vars/services/vault.yml
```

| key | note |
|---|---|
| `litellm_master_key` | **must** start `sk-` |
| `llm_router_client_hermes_key` | **must** start `sk-` |
| `llm_router_canary_key` | **must** start `sk-` |
| `mac_litellm_key` | the local tier's key — a virtual key the Mac's LiteLLM mints for the LXC (§1). `sk-` prefix. **Replaces** `omlx_api_key`. |
| `litellm_db_password` | |

~~`omlx_api_key`, `openrouter_api_key`, `anthropic_api_key`~~ — **withdrawn 2026-09-15**.
The gateway no longer talks to oMLX directly and the metered tiers are gone, so nothing
consumes these. Drop them.

~~`tailscale_authkey`~~ — **withdrawn 2026-09-15** along with the sidecar it served.
No consumer remains anywhere in the repo.

```bash
echo "sk-$(openssl rand -hex 24)"     # for the three sk- keys
```

**C2 — verify before deploying.**

```bash
./scripts/healthcheck/llm-router-doctor.py --layer config          # expect 5/5
ssh root@192.168.1.112 "curl -s -m5 http://xmjdvvw39y2t.local:4000/health/liveliness"
```

The second is the one that matters: it proves `pve` resolves the Mac's mDNS name
*and* reaches the Mac's **LiteLLM** (oMLX stays on `127.0.0.1:8000` — do not probe
it). If it fails, step A is not done or avahi is not resolving `.local` from the LXC
subnet.

**C3 — deploy.**

```bash
gh workflow run lxc-deploy-lab.yml --ref main -f service=llm-router -f apply=false
gh workflow run lxc-deploy-lab.yml --ref main -f service=llm-router -f apply=true
```

LAB lands on `192.168.20.219`; PROD on `192.168.1.220`.

**C4 — verify the deploy.**

```bash
export LLM_ROUTER_CANARY_KEY="sk-..."
./scripts/healthcheck/llm-router-doctor.py --base-url http://192.168.20.219:4000
```

---

## D · Linux laptop — fault-inject

All green is the starting point, not the finish.
[`doctor-fault-injection.md`](./doctor-fault-injection.md) has the plan; **steps
1–4 now target oMLX rather than Ollama**, so the mechanics differ — stop the oMLX
server rather than quitting Ollama.app, unpin a model rather than unsetting
`OLLAMA_KEEP_ALIVE`. Update that file as you go.

`T026` is gone from the risk list: there is no `ollama_chat` path and no proxy
hop on the backend leg. `T034`/`T035` stand and remain the most likely to bite —
a stopped oMLX refuses fast, an absent Mac can hang to timeout, and that
difference is the one LiteLLM's routing-pool defect shows up in.

---

## LAB and the local tier — deferred deliberately (2026-09-15)

**LAB cannot reach the local tier, and this is not a defect to fix before deploying.**

`docs/naming-and-mdns.md` states the constraint: mDNS is multicast and does not cross
subnet boundaries. LAB is `192.168.20.219`; the Mac is on `192.168.1.0/24`. No container
or LXC-side fix changes that — the multicast never arrives. PROD at `192.168.1.220` shares
the Mac's subnet and does not have this problem.

There is a second wall, which applies to PROD too: `libnss-mdns` is a glibc NSS module, and
the litellm **container** resolves through Docker's embedded DNS at `127.0.0.11`, which
never consults host NSS. Installing `mdns_base` on the LXC therefore does not make `.local`
resolvable inside the container. Note that `ansible/playbooks/llm-router.yml` does not
include `mdns_base` at all today.

**The decision: deploy LAB with the local tier configured and unreachable.** The options
considered were an AdGuard DNS rewrite (AdGuard is not deployed and not in use — ruled out),
a compose `extra_hosts` entry pinning the Mac's IP (reintroduces the literal IP FR-013
exists to prevent), and this. LAB-without-the-Mac is a faithful rehearsal of the state
SC-001 is written about: the Mac is *supposed* to be absent, and every alias must still
answer. That is the property most worth proving, and LAB proves it for free.

### What this means for the LAB run

| | |
|---|---|
| **not a blocker** | § A (the Mac's LiteLLM on `0.0.0.0:4000`) — LAB cannot reach it regardless |
| **not a blocker** | § B (`pve` tailnet auth) — the local tier is LAN-addressed; the tailnet carries no backend leg |
| **still required** | § C1 (vault secrets) — the only hard prerequisite |
| **expected red** | the doctor's two local-tier checks, `Mac LiteLLM reachable` and `every alias maps onto a live Mac role alias` |
| **expected red, and correct** | the gateway `alias answers` checks — SC-001 is withdrawn, there is no fallback, so from LAB each alias **fails clean** (an error naming the unreachable backend, never a hang) |
| **must be green** | the whole **config** layer and the gateway's own `endpoint answers` liveness — these prove the deploy is sound independent of the Mac |

A red local tier — and red, fail-clean aliases — with a green config layer and green
gateway liveness is the **correct** LAB result. The full alias-serving proof belongs to
PROD, which shares the Mac's subnet. Read a *hang* on any alias, not a red, as the only
real LAB failure.

### Still open for PROD — CLOSED 2026-09-19

Resolving `.local` from inside the container was unsolved and blocking the local tier in
PROD. Both halves are now fixed, and the first half was not the one this section expected:

1. **The name did not resolve anywhere in the homelab, container or not.** The Mac
   announces its mDNS records but never answers a query, so only a resolver that had
   recently overheard an announcement could resolve it. Fixed on the Mac with a LaunchAgent
   that re-announces every 45 s — no firewall or MDM change needed, because announcing is
   the half that already worked. See
   [`mac-mdns-announcer/README.md`](./mac-mdns-announcer/README.md).
2. **The container half did NOT take either candidate listed here.** `network_mode: host`
   was tried first and does not work: it shares the network namespace, not the filesystem,
   so the container keeps its own `nsswitch.conf` (`hosts: files dns`) and its own NSS
   libraries, with no `libnss-mdns`. Measured on the LXC 2026-09-19 — by IP the container
   reached the Mac (HTTP 200), by name it raised `gaierror`, which surfaced as HTTP 500
   "Connection error" on every alias. A local resolver cannot fix it either: this Mac never
   *answers* an mDNS query, so only avahi's cache on the LXC knows the mapping.

   What works: `mdns_base` gives the LXC a resolver that does know the name, the role
   resolves it there at deploy time, and the result is passed to the container as
   `extra_hosts`. The `api_base` stays a name, no IP literal enters the repo, and the
   address is rediscovered on every deploy. Residual risk is an IP change between deploys —
   the gateway then fails clean against a stale address and the doctor catches it; a DHCP
   reservation for the Mac removes it. litellm stays on the bridge network with its normal
   published port, and Postgres is not published at all.

Verified from `pve` against a flushed avahi cache: `getent hosts xmjdvvw39y2t.local` →
`192.168.1.177`, and `curl http://xmjdvvw39y2t.local:4000/health/liveliness` → HTTP 200.
LAB is unaffected either way — mDNS still does not cross subnets.

---

## What changed from `HANDOFF.md`

| then | now |
|---|---|
| Ollama on the old Mac, over the tailnet | oMLX on the new Mac, over the LAN |
| MagicDNS placeholder, unreadable behind Zscaler | mDNS `.local`, resolved on the LAN |
| `T026` — unproven `HTTP_PROXY` on `ollama_chat` | **dissolved** |
| `OLLAMA_KEEP_ALIVE=-1` | `is_pinned` on both aliased models |
| deploy "from the Linux laptop" | **everything needing a browser or a push** is on the Linux laptop |
