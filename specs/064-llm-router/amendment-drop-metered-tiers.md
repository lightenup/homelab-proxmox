# Amendment: drop the metered tiers, chain the local tier through the Mac's own LiteLLM

**Date**: 2026-09-15 · **Amends**: `spec.md` FR-004, FR-010, FR-014, FR-016,
SC-001, SC-008, SC-012, Decisions § Local runtime; `ansible/group_vars/services/vars.yml`;
`scripts/healthcheck/llm-router-doctor.py` · **Status**: pre-deploy ·
**Builds on**: [`amendment-local-tier-omlx.md`](./amendment-local-tier-omlx.md)

## Why

The previous amendment moved the local tier to oMLX over the LAN but kept the
metered tiers behind it: `hermes-fast` and `hermes-balanced` fell back to
OpenRouter, `hermes-deep` was Anthropic outright. Two facts made that shape not
worth keeping:

1. **The Mac already runs its own LiteLLM in front of oMLX**, with keys, access
   groups and role aliases (`fast`, `coder`, `reasoner`) already enforced there.
   Pointing this gateway at oMLX directly duplicated that layer and re-exposed
   oMLX to the LAN a second time.
2. **The metered tiers were never wanted as a steady state** — they were a
   discount-cushion for an intermittent Mac. In practice the Mac is a dependency
   either way (Zscaler means no tailnet fallback when it is off the home LAN), so
   the cushion bought a metered bill and a second failure surface without
   buying availability.

So: **remove the metered tiers, and chain this gateway to the Mac's LiteLLM
rather than to oMLX.** Every alias now resolves to exactly one backend — a role
alias on the Mac's `:4000` — and oMLX stays on `127.0.0.1:8000`, reachable only
by that LiteLLM.

| | after `amendment-local-tier-omlx` | after this amendment |
|---|---|---|
| backend of `hermes-*` | oMLX `:8000` + a metered fallback | the Mac's LiteLLM `:4000`, no fallback |
| LAN-exposed process on the Mac | oMLX (`0.0.0.0:8000`) | the Mac's LiteLLM (`0.0.0.0:4000`); oMLX back on `127.0.0.1` |
| what this gateway addresses | oMLX model IDs (`Qwen…:oq-agent`) | the Mac's **role aliases** (`fast`, `coder`, `reasoner`) |
| metered tiers | OpenRouter (aggregator), Anthropic (frontier) | **removed** |
| key in the vault | `omlx_api_key` | `mac_litellm_key` — a virtual key the Mac mints for the LXC |

## Why chain one gateway to another

It looks redundant and is not:

- **oMLX never touches the LAN.** Exactly one process is LAN-exposed and it is the
  one enforcing keys and access groups. That is a strictly smaller attack surface
  than exposing oMLX directly.
- **Enforcement is reused, not rebuilt.** The Mac's LiteLLM already has keys and
  access groups; this gateway mints or is handed a scoped virtual key rather than
  the master key.
- **This gateway addresses role aliases, not model IDs.** A model swap on the Mac
  — a new checkpoint behind `coder`, a re-tuned `reasoner` — needs **zero edits
  here**. That is FR-003 extended across the hop.

The cost is a second proxy hop, measured at ~21 ms, and a hard dependency on
Docker being up on the Mac. Both are accepted.

## The new mapping

| alias | deployment | Mac role alias | `context_window` | why |
|---|---|---|---|---|
| `hermes-fast` | `fast-local` | `openai/fast` | 131072 | 4-bit sibling, ~59 tok/s |
| `hermes-balanced` | `balanced-local` | `openai/coder` | 131072 | 8-bit, thinking off, validated for code at N=1 |
| `hermes-deep` | `deep-local` | `openai/reasoner` | 262144 | 8-bit, thinking on, 8k budget; **replaces the Anthropic frontier tier** |

All three:

```yaml
  api_base: "http://xmjdvvw39y2t.local:4000/v1"
  api_key_env: MAC_LITELLM_KEY
  health_checked: true
  fallback_to: null
  context_window_fallback_to: null
```

`hermes-deep` declares **262144** on purpose: the Mac's own router escalates the
`reasoner` alias to a 262k profile above its own 131k window, so this figure
exposes that reach rather than second-guessing the hop that can actually act on
it (SC-009 is still served, one hop down).

**Caveat, verified on the Mac 2026-09-16.** `reasoner` itself is a 131k profile
running **thinking ON with an 8k budget**. The 262k reach is not a pure context
bump: it comes from the Mac's `context_window_fallbacks: reasoner → qwen-long`,
and `qwen-long` runs **thinking OFF at temp 0.3**. So a `hermes-deep` request that
crosses 131k silently trades reasoning depth for window — the right trade for
whole-repo analysis, the wrong one for a hard reasoning question that merely
carries a large context. If that bites, the honest fix is a separate `long` role
on the Mac, not a cleverer fallback here. This gateway cannot see the swap; it is
one hop down and documented on the Mac's own `litellm-config.yaml`.

## What this withdraws or makes inert

Recorded here in one place; the individual FR/SC entries in `spec.md` carry the
same wording inline.

- **SC-001 — WITHDRAWN.** With no remote tier there is nothing to fall back to.
  The replacement guarantee is weaker and explicit: with the Mac away, every
  alias MUST **fail clean** — a prompt error naming the unreachable backend,
  within the health-check interval, never a hang. The gateway fails *clean*, not
  *over*. That is the trade the simplification buys.
- **FR-004 — WITHDRAWN.** No alias has a remote equivalent any more. Cross-alias
  fallback within one host is not a substitute: if the Mac is away every alias is
  away together, and silently serving `hermes-fast` from a larger model is
  *slower*, defeating the only reason a caller asked for fast. `fallback_to` is
  null throughout, deliberately.
- **FR-010 spend half — INERT.** Local deployments carry no per-token pricing, so
  `max_budget` reads 0.0 against any cap regardless of traffic. Budgets stay
  declared so a priced tier re-arms them, but the runaway-loop guard is now
  **rate limiting**, not spend.
- **SC-012 — NOT VERIFIABLE.** Same root cause: spend accrues at exactly zero, so
  no cap can be reached. The mechanism stays configured and untested until a
  priced tier returns.
- **SC-008 — REPHRASED.** A downed backend now produces a *clear error attributing
  the failure to the unreachable backend*, not a fallback. The rejoin half is
  unchanged and is the half that still proves the health checking works.

## What this does NOT change

- **FR-014 stands.** Its budget / spend-attribution justification went inert, but
  virtual keys and per-client identity (FR-015, SC-010) still require the Postgres
  backing service, and it is already specified, deployed and backed up.
- **The alias contract (FR-002, FR-003).** `hermes-fast|balanced|deep` keep their
  names and meanings; clients see nothing.
- **The Postgres backing service, the health-check cadence, the monitoring
  contract, the exposure posture (FR-008).**

## Security posture

- **oMLX returns to `127.0.0.1:8000` on the Mac.** It is no longer LAN-exposed.
  Only the Mac's LiteLLM binds `0.0.0.0:4000`.
- **The LXC authenticates to the Mac with a scoped virtual key** (`mac_litellm_key`),
  minted by the Mac's LiteLLM (`POST /key/generate`) and scoped to the three
  aliases — not the Mac's master key. Vaulted like any other secret.
- **`openrouter_api_key` and `anthropic_api_key` are no longer consumed** by any
  deployment. They may be dropped from the vault; the router holds no metered
  credential once they are.

## Vault delta

| key | change |
|---|---|
| `mac_litellm_key` | **new** — replaces `omlx_api_key`. A virtual key the Mac mints for the LXC. `sk-` prefix. |
| `omlx_api_key` | **removed** — the gateway no longer talks to oMLX directly. |
| `openrouter_api_key` | **removed** — no aggregator tier. |
| `anthropic_api_key` | **removed** — no frontier tier. |

The compose template derives container env vars from the distinct `api_key_env`
values in `llm_router_aliases`, so `MAC_LITELLM_KEY` is wired automatically from
the vault variable `mac_litellm_key`; no hand-edit of the compose file is needed.

## Doctor changes

The local-tier layer can no longer observe oMLX — it is behind `127.0.0.1` on the
Mac. A check that cannot reach its subject is removed, not left returning a pass.

| was | becomes |
|---|---|
| `GET /health` on oMLX — reachability | `GET /health/liveliness` on the Mac's LiteLLM |
| `GET /admin/api/models` — residency/pinning/context assertion | `GET /v1/models` — assert each hermes alias maps onto a **live Mac role alias** |
| `every alias answers right now` (SC-001) | removed — SC-001 withdrawn; the note now states the fail-clean requirement |

The residency/pinning check moves to the **Mac side** of `RUNBOOK.md` § 1, since
that is the only place it can be run. It is not silently dropped.

## Sequence

1. Re-point the three `local` deployments in `group_vars` to `:4000` role aliases,
   `MAC_LITELLM_KEY`; remove the metered deployments. *(done)*
2. Amend FR-004/010/014/016 and SC-001/008/012 in `spec.md`. *(done)*
3. Rewrite the doctor's local-tier layer. *(done)*
4. On the Mac: rebind LiteLLM to `0.0.0.0:4000`, keep oMLX on `127.0.0.1:8000`,
   mint the scoped virtual key — `RUNBOOK.md` § 1. *(done 2026-09-16 — see below.)*
5. Vault: add `mac_litellm_key`, drop the three removed keys — `RUNBOOK.md` § 3.
6. Deploy once against the final design.

## Executed on the Mac — 2026-09-16 (`RUNBOOK.md` § 1)

Run on `XMJDVVW39Y2T` (192.168.1.177) itself, the oMLX host.

- **Job 1 done.** The Mac's LiteLLM runs via `docker compose` at
  `~/Development/private/local-llm/proxy`. Rebound `docker-compose.yml` from
  `127.0.0.1:4000:4000` to `0.0.0.0:4000:4000`; `docker compose up -d`; verified
  `*:4000`, `/health/liveliness` answering from both `127.0.0.1` and the LAN IP,
  and `fast`/`coder`/`reasoner` serving completions over the LAN. oMLX confirmed
  still on `127.0.0.1:8000`. macOS app firewall stays enabled — Docker's backend
  was already permitted inbound, so no firewall change was needed. The Mac owner's
  local loopback consumers (opencode providers, `bench/*.py`) are unaffected —
  `0.0.0.0` is a superset of loopback.
- **Job 2 done.** Minted a virtual key `key_alias: homelab-lxc-064-llm-router`,
  scoped to `models: ["local"]` (the access group — includes `qwen-long` so the
  `hermes-deep` context fallback works, and excludes any future `cloud-approved`
  group). This is the vault's `mac_litellm_key`. Verified it serves all three
  aliases over the LAN and reaches `qwen-long` directly. **The key value is
  handed over out-of-band, not recorded here.**

### Two findings from the Mac side

1. **Config drift, benign.** The running container predated the on-disk
   `litellm-config.yaml`; the Job 1 recreate reloaded it, adding three
   `Flash-Next` trial models. They are wired to no role alias, so
   `fast`/`coder`/`reasoner`/`diagram` are unchanged and the homelab is unaffected.
2. **Residency/pinning cannot be checked via the admin API — RESOLVED 2026-09-19 by not
   using it.** oMLX's `/admin/api/models` returns `Admin authentication required` to *every*
   credential on the machine: the 4-char `auth.api_key`, the 64-char `auth.secret_key`, and
   no auth at all. The GUI does not use it over HTTP — it talks to the server through a unix
   socket at `~/Library/Application Support/oMLX/control.sock`. So the endpoint is not
   scriptable, and that is why the claim sat unverified from 2026-09-14.

   It did not need to be. Pinning is **configured** in `~/.omlx/model_settings.json`
   (`is_pinned`) — the same lever the amendment used to set it — and that file is readable.
   `mac-checks/verify-omlx-residency.sh` asserts it, deriving the fallback targets from the
   Mac's own `context_window_fallbacks`. **Verified 2026-09-19: all four pinned** —
   `Qwen3.8-27B-oQ4e-mtp` (`fast`) and `Qwen3.8-27B-8bit` (`coder`, `reasoner`, and
   `qwen-long`, hermes-deep's escalation target). Fault-injected both ways: it goes red on an
   unpinned model and on oMLX being down.

   The stated limit: this asserts configuration, not live engine state. `/health` exposes only
   an aggregate `loaded_count` (4 of 11, 75.7 GB of a 115.4 GB ceiling at check time), so no
   unprivileged caller can observe which models are resident *right now*.
