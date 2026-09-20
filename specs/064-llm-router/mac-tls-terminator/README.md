# Mac TLS terminator — how the gateway holds a 20-minute request

FR-013 has the gateway address the Mac over the LAN. Until 2026-09-20 that leg was
plaintext HTTP and could not hold a request for more than ~300 seconds. This is what was
wrong, why TLS fixes it, and what else was tried first.

## What was wrong

Inbound **plaintext HTTP** to this Mac is closed after ~300 s with no application-layer
response data — and unpredictably after that even when data *is* flowing:

| condition, LXC → Mac | outcome |
|---|---|
| silent 120 / 240 / 300 s | alive |
| silent 360 / 420 / 480 / 600 s | **dead**, clean FIN |
| SSE keepalive pings every 20–30 s | **still dead** at 658 s and 1443 s |
| TCP keepalive (`SO_KEEPALIVE`, 60 s idle) | **no help** |

TCP keepalive not helping is the diagnostic: the closer counts **application data**, not
packets, so it is parsing HTTP. On an MDM-managed Mac that means the app firewall's stealth
mode or the Zscaler network filter. Neither is ours to change.

It was localised by elimination, all at 480 s of silence:

| path | result |
|---|---|
| LXC → `pve` (Mac not in the path) | survived |
| Mac → Mac loopback | survived |
| Mac → `pve` (outbound from the Mac) | survived (1500 s) |
| LXC → Mac, plain listener, **no Docker** | **died** |
| LXC → Mac, through Docker | **died** |

So it is specific to **inbound** connections to the Mac, and it is not Docker's port
forwarder.

## Why TLS fixes it

If the closer is reading HTTP, encrypting the payload removes what it acts on. Measured
twice, with **zero** application data in either direction:

```
TLS, 1500s of complete silence  ->  HTTP 200
TLS, 1800s of complete silence  ->  HTTP 200
```

End to end through the real stack: a cold 108k-token prompt that returned `408` at 180 s and
a connection error at 417 s over plaintext **completed in 395.6 s over TLS**.

## The shape

```
gateway (LXC)  --https, cert-verified-->  terminator :4443  --loopback-->  LiteLLM :4000  -->  oMLX :8000
```

The terminator is the **only** LAN-exposed process. LiteLLM and oMLX are both back on
`127.0.0.1`, which is tighter than the arrangement FR-016 originally described, and the leg
carrying `mac_litellm_key` is now encrypted — it crossed the LAN in the clear before.

Verification is real: the gateway sets `ssl_verify` to a path, not `false`, so the
connection is authenticated as well as encrypted. An expired certificate fails with a TLS
error naming it, rather than hanging.

## Install

```bash
./make-cert.sh                                     # 10-year self-signed, SAN = the mDNS name
cp ~/.config/hermes-tls/cert.pem <repo>/ansible/roles/llm_router/files/mac-ca.pem

cp hermes-tls-terminator.py ~/.local/bin/ && chmod +x ~/.local/bin/hermes-tls-terminator.py
cp no.hus-sky.hermes-tls-terminator.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/no.hus-sky.hermes-tls-terminator.plist
launchctl list | grep hermes-tls                   # label present, last exit 0
```

Then bind the Mac's LiteLLM to loopback — in `~/Development/private/local-llm/proxy/docker-compose.yml`,
`ports:` must read `"127.0.0.1:4000:4000"`, not `"0.0.0.0:4000:4000"` — and
`docker compose up -d`.

### Verify

```bash
lsof -nP -iTCP:4443 -sTCP:LISTEN     # the terminator, *:4443
lsof -nP -iTCP:4000 -sTCP:LISTEN     # LiteLLM, 127.0.0.1 only
lsof -nP -iTCP:8000 -sTCP:LISTEN     # oMLX, 127.0.0.1 only

curl -s --cacert ~/.config/hermes-tls/cert.pem \
     --resolve xmjdvvw39y2t.local:4443:192.168.1.177 \
     https://xmjdvvw39y2t.local:4443/health/liveliness      # "I'm alive!"
```

## Why a Python relay and not stunnel

`stunnel` would be the conventional choice and is better tested than
`hermes-tls-terminator.py`. It was rejected on dependency grounds: this Mac is MDM-managed
with a documented policy prompt on unapproved software, Python 3 is system-provided, and the
mDNS announcer next door already establishes the "small Python script + LaunchAgent"
pattern. The trade is recorded rather than hidden — it is a hand-rolled relay carrying real
traffic, so it deliberately does as little as possible: it never parses, buffers or
interprets the stream, and the only timeouts it sets are on the TLS handshake and the
upstream connect. The relay itself has **no** timeout, because a 20-minute silent prefill is
the whole reason it exists.

Revisit if it ever needs to do more than relay bytes. At that point use stunnel.

## What else was tried, and why it failed

Recorded so nobody re-derives it — full measurements in
[`docs/backlog/069`](../../../docs/backlog/069-large-context-cross-host-ceiling.md).

| approach | why it failed |
|---|---|
| reverse SSH tunnel | the tunnel itself dies; requests failed at 417 s and 711 s, and `autossh` cannot resume an in-flight HTTP request |
| mosh | survives disconnects by design, but has no port forwarding |
| LiteLLM keepalive pings | raises the floor but does not bound the drop (658 s), and only applies to streaming |
| LiteLLM response cache + retry | `_cancel_llm_call_on_client_disconnect` is hardcoded and ungated, so the work never completes and nothing is cached |
| retry alone | an aborted prefill is discarded (689.7 s, fully cold) |
| chunked prefix warming | oMLX gives only 10–15 % on an extending prompt |
| TCP keepalive | the closer counts application data, not packets |

## Lifecycle

A LaunchAgent, not a daemon: it needs no root, and its login-session lifetime matches Docker
Desktop's and oMLX's. When the Mac cannot serve the local tier this stops listening too, so
the gateway fails clean rather than hanging. `KeepAlive` is set — unlike the announcer's
`StartInterval` — because this is a long-lived listener and the gateway has no other path to
the Mac if it dies.

The certificate expires **2036-09-17**. Re-run `make-cert.sh`, copy the public half into the
role, and redeploy.
