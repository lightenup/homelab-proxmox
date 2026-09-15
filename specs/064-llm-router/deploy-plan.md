# Deploy plan — who does what, and where

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
| `omlx_api_key` | the local tier's key — **new**, replaces nothing |
| `openrouter_api_key` | |
| `anthropic_api_key` | API key, never a subscription credential (FR-007) |
| `litellm_db_password` | |

~~`tailscale_authkey`~~ — **withdrawn 2026-09-15** along with the sidecar it served.
No consumer remains anywhere in the repo.

```bash
echo "sk-$(openssl rand -hex 24)"     # for the three sk- keys
```

**C2 — verify before deploying.**

```bash
./scripts/healthcheck/llm-router-doctor.py --layer config          # expect 5/5
ssh root@192.168.1.112 "curl -s -m5 http://xmjdvvw39y2t.local:8000/health"
```

The second is the one that matters: it proves `pve` resolves the Mac's mDNS name
*and* reaches oMLX. If it fails, step A is not done or avahi is not resolving
`.local` from the LXC subnet.

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
| **not a blocker** | § A (oMLX on `0.0.0.0`) — LAB cannot reach it regardless |
| **not a blocker** | § B (`pve` tailnet auth) — the local tier is LAN-addressed; the tailnet carries no backend leg |
| **still required** | § C1 (vault secrets) — the only hard prerequisite |
| **expected red** | the doctor's two local-tier checks, `oMLX reachable` and `serves the declared context, resident` |
| **must be green** | `every alias answers right now` — this is SC-001 and the whole point of the run |

A red local tier with green aliases is the **correct** LAB result. Read it as the
fault-injection table's row 2 arriving for free rather than as a failed deploy.

### Still open for PROD

Resolving `.local` from inside the container is unsolved and blocks the local tier in PROD.
The candidates are `network_mode: host` on the litellm container (the host's glibc NSS, and
so `libnss-mdns`, then applies), or a real DNS record once a resolver exists. Decide before
promoting; nothing in the LAB run depends on it.

---

## What changed from `HANDOFF.md`

| then | now |
|---|---|
| Ollama on the old Mac, over the tailnet | oMLX on the new Mac, over the LAN |
| MagicDNS placeholder, unreadable behind Zscaler | mDNS `.local`, resolved on the LAN |
| `T026` — unproven `HTTP_PROXY` on `ollama_chat` | **dissolved** |
| `OLLAMA_KEEP_ALIVE=-1` | `is_pinned` on both aliased models |
| deploy "from the Linux laptop" | **everything needing a browser or a push** is on the Linux laptop |
