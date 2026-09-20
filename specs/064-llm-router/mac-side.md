# The Mac side, as it now stands

The homelab gateway's only backend is this Mac. Four processes cooperate to make that
work, and the arrangement is not obvious from any one of them — each has its own README
written when it was *added*, so the resting state is nowhere. This is that page.

Everything here was verified running on 2026-09-20.

## The four processes

| # | process | binds | lifetime | why it exists |
|---|---|---|---|---|
| 1 | **oMLX** | `127.0.0.1:8000` | GUI app, login session | the inference engine. Holds both aliased models resident (`is_pinned`). |
| 2 | **LiteLLM** | `127.0.0.1:4000` | Docker Desktop, login session | the Mac's own gateway. Maps role names onto oMLX profiles, enforces keys. |
| 3 | **mDNS announcer** | — (multicast out) | LaunchAgent, `StartInterval 45` | keeps `xmjdvvw39y2t.local` resolvable from the LAN. |
| 4 | **TLS terminator** | **`0.0.0.0:4443`** | LaunchAgent, `KeepAlive` | the only LAN-exposed process. Relays to `127.0.0.1:4000`. |

**Exactly one of the four listens on the LAN, and it is the encrypted one.** That is
tighter than the arrangement FR-016 originally described, where LiteLLM itself bound
`0.0.0.0:4000` and the leg carrying `mac_litellm_key` crossed the LAN in the clear.

Confirm the bindings in one go — any deviation here is a misconfiguration, not a variant:

```bash
lsof -nP -iTCP:4443 -sTCP:LISTEN     # *:4443           Python, the terminator
lsof -nP -iTCP:4000 -sTCP:LISTEN     # 127.0.0.1:4000   Docker, LiteLLM
lsof -nP -iTCP:8000 -sTCP:LISTEN     # 127.0.0.1:8000   python3, oMLX
launchctl list | grep hermes         # both agents, last exit 0
```

## The request path

```
Hermes  ──►  gateway LXC 192.168.1.220:4000        LiteLLM, virtual keys, budgets
                │                                   alias: hermes-fast|balanced|deep
                │  https, cert-verified
                ▼
        terminator  xmjdvvw39y2t.local:4443        TLS ends here
                │
                │  loopback
                ▼
             LiteLLM  127.0.0.1:4000               alias: fast|coder|reasoner
                │                                   key: mac_litellm_key
                │  loopback
                ▼
                oMLX  127.0.0.1:8000               Qwen3.8-27B-8bit / -oQ4e-mtp
```

Both hops are LiteLLM, and that is deliberate rather than redundant: the gateway owns
*who may call and how much they may spend*, the Mac owns *which model answers*. Retiering
a model touches only the Mac; adding a client touches only the gateway.

### How the names line up

The gateway's `provider_model` is `openai/<name>`, where `<name>` is an **alias on the
Mac's gateway**, not a model file. This trips people up:

| gateway alias | `provider_model` | Mac alias | resolves to |
|---|---|---|---|
| `hermes-fast` | `openai/fast` | `fast` | `Qwen3.8-27B-oQ4e-mtp:oq-agent` — 4-bit, ~59 tok/s |
| `hermes-balanced` | `openai/coder` | `coder` | `Qwen3.8-27B-8bit:qwen-code` — 8-bit, thinking off |
| `hermes-deep` | `openai/reasoner` | `reasoner` | `Qwen3.8-27B-8bit:qwen-reason` — 8-bit, thinking on, 8k budget |

`hermes-deep` declares `context_window: 262144` while the Mac's `reasoner` is a 131k
profile. The reach is real but it comes from the **Mac's** router: `reasoner` has a
`context_window_fallbacks` entry onto `qwen-long`, a 262k profile. Crossing 131k therefore
trades reasoning depth for window — `qwen-long` runs thinking **off** at temp 0.3.
Exercised and measured in `tasks.md` T038.

## Why TLS, and why it is not optional

Plaintext HTTP **inbound** to this Mac is closed after ~300 s with no application-layer
response data, and unpredictably after that even when data is flowing (observed deaths at
658 s and 1443 s with SSE keepalives every 20–30 s). TCP keepalive does not help, which is
the diagnostic: the closer counts **application data**, so it is parsing HTTP. On an
MDM-managed Mac that means the firewall's stealth mode or the Zscaler network filter, and
neither is ours to change.

The same connection **over TLS held 1800 s of complete silence**. Encrypting the payload
removes what the middlebox acts on.

This matters because a cold prefill is genuinely silent for a long time: a 170,305-token
prompt completed in **901.8 s**, and it emits nothing until the first token. Six other
approaches were measured and rejected first — SSH tunnel, mosh, LiteLLM cache+retry, retry
alone, chunked prefix warming, TCP keepalive. The full comparison is in
[`mac-tls-terminator/README.md`](./mac-tls-terminator/README.md) and `docs/backlog/069`.

Verification is against the certificate, not disabled: the gateway sets
`litellm_settings.ssl_verify` to a path. Setting it to `false` would keep everything
working and silently drop the authentication on the leg that carries `mac_litellm_key`.

## The certificate

| | |
|---|---|
| lives | `~/.config/hermes-tls/` on the Mac (key mode `600`) |
| subject | `CN=xmjdvvw39y2t.local` |
| SAN | `DNS:xmjdvvw39y2t.local`, `IP:192.168.1.177` |
| expires | **2036-09-17** |
| public half, in-repo | `ansible/roles/llm_router/files/mac-ca.pem` |

The public half is committed on purpose and is exempted by name in `.gitignore`, which
otherwise refuses `*.pem`. **Regenerating the certificate requires copying the new public
half into the repo and redeploying** — otherwise every local-tier call fails TLS
verification while the Mac looks perfectly healthy from its own side.

## What breaks, and how it surfaces

All four processes die with the login session — three are user-scope agents and LiteLLM
rides Docker Desktop. On a reboot with no login, the Mac is simply absent, and the gateway
**fails clean** (SC-001 is withdrawn; there is no fallback tier to spill to).

| symptom at the gateway | first thing to check |
|---|---|
| every alias, HTTP 500 "Connection error" | terminator down, or the Mac logged out |
| every alias, TLS verification failure | certificate regenerated without redeploying `mac-ca.pem` |
| deploy fails "does not resolve on this host" | announcer down — `launchctl list \| grep hermes` |
| one alias slow then `408` | model evicted; check `is_pinned` with `mac-checks/verify-omlx-residency.sh` |
| everything dies at ~300 s | something is back on plaintext — check port 4443 is what the LXC is calling |

The doctor covers the first four: `./scripts/healthcheck/llm-router-doctor.py --base-url http://192.168.1.220:4000`.

## Where the detail lives

| | |
|---|---|
| install/uninstall, per component | `mac-tls-terminator/README.md`, `mac-mdns-announcer/README.md` |
| model residency check | `mac-checks/verify-omlx-residency.sh` |
| step-by-step operational commands | [`RUNBOOK.md`](./RUNBOOK.md) Jobs 1–4 |
| why the Mac announces but never answers | [`docs/naming-and-mdns.md`](../../docs/naming-and-mdns.md) |
| the ~300 s investigation, and the six rejected fixes | `docs/backlog/069-*` |
| the Mac's own gateway, on its own terms | `~/Development/private/local-llm/proxy/` |
| how the two gateways relate | [`docs/architecture/two-llm-gateways.md`](../../docs/architecture/two-llm-gateways.md) |
