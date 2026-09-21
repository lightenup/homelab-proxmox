# Two LLM gateways, and why they are now chained

**Rewritten 2026-09-20.** The previous version described two independent, parallel
gateways and asked why they were not one. That question has been overtaken: the homelab
gateway's **only backend is the dev Mac's gateway**. They are no longer alternatives, they
are two layers of one path, and the interesting question changed from "why two?" to "what
does each layer own?".

## The path

```
Hermes (spec 065, 192.168.1.221), and any other homelab client
   │
   │  sk-… virtual key, alias hermes-fast | hermes-balanced | hermes-deep
   │       | hermes-embed | hermes-rerank (retrieval, amendment-hermes-retrieval-aliases.md)
   ▼
gateway LXC  192.168.1.220:4000          ← owns WHO may call, and HOW MUCH
   │                                        virtual keys, budgets, RPM, spend logs
   │  https, certificate-verified, over the LAN
   ▼
dev Mac      xmjdvvw39y2t.local:4443     ← TLS terminator, the only LAN-exposed process
   │  loopback
   ▼
dev Mac      127.0.0.1:4000              ← owns WHICH MODEL answers
   │                                        role aliases, profile selection, escalation
   │  loopback
   ▼
oMLX         127.0.0.1:8000              ← the inference engine
```

The Mac side of that — all four processes, the bindings, the certificate, what breaks
how — is [`specs/064-llm-router/mac-side.md`](../../specs/064-llm-router/mac-side.md).

## The division of ownership

This is the part worth keeping, because it is what makes two layers cheaper than one.

| | gateway LXC (`064-llm-router`) | dev Mac |
|---|---|---|
| addressed by | `hermes-fast` `hermes-balanced` `hermes-deep` | `coder` `reasoner` `fast` `diagram` |
| names | **capability tiers** — how much model the caller wants | **roles** — what the caller is doing |
| owns | identity, budgets, rate limits, spend accounting | model choice, quantisation, thinking budget, context escalation |
| backend | the Mac, and nothing else | oMLX, same machine |
| metered tier | **none** | **none** |
| router fallbacks | **null throughout** | **empty, enforced** |
| persistent state | Postgres — keys, budgets, `LiteLLM_SpendLogs` | Postgres — keys only |
| reachable from | the homelab LAN | `127.0.0.1` only |
| status | deployed, `192.168.1.220` | running |

**Retiering a model touches only the Mac. Adding a client touches only the gateway.**
Neither operation crosses the boundary, which is the whole return on running two.

## Why both forbid fallbacks, for different reasons

The previous version called this "the sharpest difference and the one most likely to look
like a mistake", because one required fallbacks and the other forbade them. Both now
refuse them, and the reasons have nothing to do with each other — so the symmetry is
coincidence, and treating it as a shared policy would be wrong.

**The Mac forbids them to stop data leaving.** LiteLLM fires a router-level fallback *even
when the calling key is not permitted to call the fallback model directly*, which makes a
local→cloud spill the **default** rather than an opt-in. On a machine holding client work
that is the wrong default, so `fallbacks` and `content_policy_fallbacks` are pinned empty
with a comment at the point of use saying why. This constraint returns the moment a cloud
deployment is added there.

**The gateway has nothing to fall back to.** The metered tiers (OpenRouter, Anthropic)
were removed; every alias resolves to the same Mac. Cross-alias fallback within one host
is theatre — if the Mac is away, every alias is away together, and if a model is merely
evicted, silently serving `hermes-fast` from the 8-bit is *slower*, which defeats the only
reason a caller asked for fast. So `fallback_to` is null throughout and the gateway
**fails clean** when the Mac is absent.

That is an explicit trade: **SC-001 is withdrawn.** The Mac was once specified as "a
discount that is usually available, never a dependency". It is now a dependency. The
simplification bought one trust domain, one set of credentials and no spend, at the cost
of availability that was never actually being paid for.

### The one fallback that is enabled, and where it lives

`reasoner` on the Mac has a `context_window_fallbacks` entry onto `qwen-long`, a 262k
profile. It is local→local, so it cannot spill across a trust boundary, and it only fires
on a request that would otherwise be rejected outright for length.

The gateway deliberately does **not** duplicate it. `hermes-deep` declares
`context_window: 262144` to *expose* that reach, but sets `context_window_fallback_to:
null`, because the Mac's router is the hop that can actually act on it.

**The principle: escalation belongs to the layer that owns the models.** The gateway
advertises the capability; the Mac decides how to deliver it. Duplicating the rule at both
layers would mean two places to get it wrong and a second-guess at the outer one.

(The escalation is not a pure context bump: `qwen-reason` runs thinking on with an 8k
budget, `qwen-long` runs thinking **off** at temp 0.3. Crossing 131k trades reasoning
depth for window. Right for whole-repo analysis, wrong for a hard architecture question
that happens to carry a large context.)

## Why the budget story is now the same, and Postgres still earns its place

The previous version said the homelab gateway's budgets "actually bite" because it had a
metered tier. It does not have one any more, so **both gateways' `max_budget` is inert**:
local deployments carry no per-token pricing, so `spend` stays at exactly 0.0 against any
cap no matter how much traffic runs.

Postgres is still required on the gateway, and it is worth being precise about what for,
because "budgets" is now the wrong answer:

- **virtual keys** — per-client `sk-…` credentials, scoped with `models` so a key cannot
  call an alias it was not granted
- **RPM limits** — these *do* bite, and are the only live quantitative control
- **`LiteLLM_SpendLogs`** — request accounting, which stays useful at zero cost

If a metered tier ever returns, the budget machinery is already in place and correct. It
is dormant, not absent, and the preflight still enforces
`gateway cap > sum(client budgets)` so it cannot come back misconfigured.

## Why the vocabularies differ, and the cost of that

`coder`/`reasoner`/`fast`/`diagram` name **roles** — what the caller is doing.
`hermes-fast`/`balanced`/`deep` name **capability tiers** — how much model the caller
wants. Both are legitimate indirections and both deliver FR-003's real benefit: swapping
the model behind a name touches no client.

Now that the two are chained, the cost is smaller than it was but more specific: the
mapping between the vocabularies is a real table that has to be maintained, and it is
non-obvious in the config, because the gateway's `provider_model` reads `openai/coder` —
which looks like a model name and is actually *an alias on the other gateway*. The table
is in [`mac-side.md`](../../specs/064-llm-router/mac-side.md#how-the-names-line-up).

A client still cannot move between the two unchanged. No client needs to, and the
vocabularies are honest about the different questions each layer answers, so this stays.

## What would change the shape

- **A metered tier returns.** The budget machinery wakes up, and the Mac's
  data-protection constraint on `fallbacks` starts applying to the gateway too — that is
  the moment to re-read the first section rather than copying a pattern across.
- **A second inference engine appears** alongside or instead of oMLX. This is the case the
  chain was built for: it lands behind the Mac's gateway and the homelab sees nothing.
- **A client needs both vocabularies.** Align them first; cheap before a client binds,
  expensive after.
- **A third gateway appears.** Two is a chain; three wants a shared contract.
- **Zscaler stops blocking Tailscale on the dev Mac.** Affects the *control plane* only —
  browser auth, `git push` — which is why those live on the Linux laptop. The data path
  between the gateways is LAN and always was unaffected.

## The finding that transferred

The dev Mac setup is documented in `local-llm/docs/FINDINGS.md`. Its dominant failure mode
— six cases of configuration that read correctly, raised no error, and did nothing —
produced one finding that applies directly here: **`context_window_fallbacks` is silently
dead without `enable_pre_call_checks`.**

This role already sets it, independently, and
`scripts/healthcheck/llm-router-doctor.py` asserts the flag *stays* set rather than taking
credit for putting it there.

Two more of that shape have since been found on the homelab side, and they are the same
class — correct-looking configuration that does nothing:

- **`allowed_fails: 2` was unreachable.** The failure counter's TTL is `cooldown_time`, so
  a threshold above zero is only crossed by that many failures *inside* the cooldown
  window. With a 1200 s request timeout it never was, and every request paid the full
  timeout against a dead backend. Now `0`.
- **A client key with no `models` scoping could call any alias.** The key looked
  constrained because it had a budget and an alias of its own; it was not.

The lesson generalises past LiteLLM: **a setting that cannot fail loudly has to be tested
by observation, not by reading.** That is what `doctor-fault-injection.md` is for.
