# Amendment: the local tier moves from Ollama-over-tailnet to oMLX-over-LAN

**Date**: 2026-09-14 · **Amends**: `spec.md` FR-016, FR-009; `quickstart.md` § 0b;
`ansible/group_vars/services/vars.yml` · **Status**: pre-deploy

## Why

The spec's local tier is Ollama on a Mac, reached over the tailnet. **That Mac is
being returned** — weeks away, not days. The machine that will run local
inference from here on is a different Mac, and it changes three things at once:

| | spec as written | after this amendment |
|---|---|---|
| host | old Mac, being returned | new Mac, kept |
| runtime | Ollama `0.33.1` | **oMLX** |
| transport | tailnet, via the LXC's tailscaled sidecar | **LAN** |
| provider | `ollama_chat/…` | **`openai/…`** — oMLX is OpenAI-compatible |

**The transport change is the consequential one.** Zscaler blocks Tailscale on
the EY-managed Mac but does not touch LAN traffic. Verified: the Mac sits at
`192.168.1.177` and reaches `pve` at `192.168.1.112` directly. PROD lands on
`192.168.1.220` — the same subnet. So the local tier needs no tailnet at all.

## What this deletes

**`T026` is moot.** It asked whether LiteLLM's httpx honours `HTTP_PROXY` on the
`ollama_chat` provider path — flagged in `HANDOFF.md` as the single most likely
thing to bite, unproven, and capable of changing the compose file. There is no
`ollama_chat` path any more and no proxy hop on the backend leg, so the question
dissolves rather than being answered.

**The tailscaled sidecar is not needed for the backend.** Check whether anything
else depends on it before removing it — FR-008 requires the gateway be *client*
reachable over the tailnet, which is a separate leg and probably still wants it.

## What this does not change

**SC-001 still holds and still matters.** The new Mac is a laptop that leaves the
house. On the office LAN it is unreachable, and Zscaler means no tailnet
fallback, so it is absent more predictably than the old one was — "a discount
that is usually available, never a dependency" is if anything more apt.

**The alias contract is untouched.** `hermes-fast`, `hermes-balanced`,
`hermes-deep` keep their names and their meanings. This is FR-003 doing exactly
what it was built for: the backend changes, no client changes.

## The new mapping

oMLX serves profile-suffixed model IDs. Two checkpoints are resident together —
an 8-bit for quality and a 4-bit sibling for speed — and they swap without an
engine reload.

| alias | deployment | model | why |
|---|---|---|---|
| `hermes-fast` | `fast-local` | `Qwen3.8-27B-oQ4e-mtp:oq-agent` | 4-bit, ~59 tok/s, low temperature, tool-call shaped |
| `hermes-balanced` | `balanced-local` | `Qwen3.8-27B-8bit:qwen-code` | 8-bit, ~34 tok/s, the quality tier |
| `hermes-deep` | `deep-frontier` | unchanged — Anthropic | |

Both local deployments:

```yaml
  provider_model: "openai/<model-id>"
  api_base: "http://xmjdvvw39y2t.local:8000/v1"
  api_key_env: OMLX_API_KEY
  context_window: 131072
  health_checked: true
```

**Addressing follows `docs/naming-and-mdns.md`** — mDNS `.local`, as every other
host here does, rather than a DHCP-assigned IP. The LXC resolves it through
`avahi-daemon`, which is already the estate convention.

**`context_window` rises to 131072.** The profiles are configured for it and it
is verified. The old Ollama figure of 32768 was a constraint of that setup, not
of this one.

## New environmental blocker, replacing the old one

**oMLX binds `127.0.0.1:8000` only** — confirmed by `lsof` and by its own
`server-info`. This is the identical trap `quickstart.md` § 0b documents for
Ollama, in a different runtime: the LXC cannot reach it as-is.

Fix on the Mac, in the oMLX UI or `~/.omlx/settings.json`, then restart:

```
server.host: 0.0.0.0
```

Verify from the Mac, then from `pve`:

```bash
lsof -nP -iTCP:8000 -sTCP:LISTEN            # must be *:8000, not 127.0.0.1:8000
ssh root@192.168.1.112 "curl -s -m5 http://xmjdvvw39y2t.local:8000/health"
```

**Residency replaces keep-alive.** Ollama needed `OLLAMA_KEEP_ALIVE=-1` so a cold
load could not trip the gateway timeout into a false fallback. oMLX has the same
hazard with a different lever: both models must be **loaded and the 8-bit
pinned**, so a swap does not stall the first request. Confirm with
`/admin/api/models` that both show `loaded: true`.

## Security posture

Binding `0.0.0.0` exposes oMLX to the home LAN. Accepted deliberately, with the
boundary stated so it is enforced rather than assumed:

- **LAN only.** No port forward, no reverse-proxy route, no public DNS name — SC-007
  already requires this of the gateway and it extends to the backend.
- **Request-inbound only.** The homelab calls the Mac; the Mac initiates nothing
  toward the homelab and sends it no data of its own.
- **No remote path.** Zscaler blocks Tailscale on this machine, so there is no
  route to oMLX when it is off the home LAN. That is a constraint worth keeping
  rather than working around.
- oMLX's API key still applies; `OMLX_API_KEY` goes in the vault like any other.

## Doctor changes

`scripts/healthcheck/llm-router-doctor.py` probes Ollama's `/api/tags` and
`/api/ps`. Neither exists on oMLX. Replace with:

| was | becomes |
|---|---|
| `GET /api/tags` — reachability | `GET /health` |
| `GET /api/ps` — context and residency | `GET /admin/api/models` → assert both `loaded: true`, and `model_context_length` ≥ declared |

The check's *intent* is unchanged and worth restating: it must ask **the Mac**
what it is actually serving, never read the environment of whatever box happens
to be running the doctor. The first version of that check made exactly that
mistake.

## Sequence

1. Amend FR-016 and FR-009 in `spec.md` to name oMLX and LAN.
2. Rewrite the two `local` deployments in `group_vars`, delete the MagicDNS
   placeholders.
3. Update the doctor's local-tier probes.
4. ~~Decide whether the tailscaled sidecar still earns its place under FR-008.~~
   **Decided**: kept for the first deploy. FR-017's original justification —
   reaching the Mac — is gone, but the sidecar is what keeps FR-008's tailnet
   client reach independent of `pve`'s subnet router, which is logged out and
   would otherwise be a single point of failure. FR-017 is amended with that
   justification and a revisit condition.
5. Bind oMLX to `0.0.0.0`, pin both models, verify reachability from `pve`.
6. Then deploy once, against the final design.

The old Mac is weeks away, so there is no need to deploy against hardware that is
leaving in order to prove the pipeline.
