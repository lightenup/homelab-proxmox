# Two LLM gateways, and why they are not one

There are two LiteLLM deployments in this estate. They were designed
independently, arrived at the same shape, and are **deliberately not
interchangeable**. This records why, so the divergence is a decision rather than
something a future reader has to reverse-engineer.

| | dev Mac | homelab (`064-llm-router`) |
|---|---|---|
| gateway | LiteLLM on `127.0.0.1:4000` | LiteLLM on a gated LXC |
| addressed by | `coder` `reasoner` `fast` `diagram` | `hermes-fast` `hermes-balanced` `hermes-deep` |
| local engine | oMLX, same machine | Ollama on the old Mac, over the tailnet |
| metered tier | **none** | OpenRouter + Anthropic |
| router fallbacks | **empty, enforced** | **ordered, required** (FR-004) |
| budgets | inert | enforcing |
| status | running | code-complete, undeployed |

## Why the fallback policy is opposite

This is the sharpest difference and the one most likely to look like a mistake.

**The homelab requires fallbacks.** Its local tier is a Mac that is *expected*
to be absent — asleep, off, off the tailnet. SC-001 states the Mac must be "a
discount that is usually available, never a dependency", so falling through to a
metered tier is the entire point of the design.

**The dev Mac forbids them.** LiteLLM fires a router-level fallback *even when
the calling key is not permitted to call the fallback model directly*, which
makes a local→cloud spill the **default** rather than an opt-in. On a machine
holding client work that is the wrong default, so `fallbacks` and
`content_policy_fallbacks` are pinned empty and a comment at the point of use
says why.

Both are correct. Neither transfers.

## Why the budget story differs

On the dev Mac, `max_budget` is **inert** — measured, not assumed. Local
deployments carry no per-token pricing, so `spend` stays at exactly 0.0 against
any cap no matter how much traffic runs. Postgres is necessary there and not
sufficient.

The homelab gateway has a metered tier with real pricing, so spend accrues and
FR-010's per-client budgets actually bite. **The Postgres requirement earns its
place there in a way it does not here**, which is worth knowing before anyone
"simplifies" either deployment by copying the other.

## Why the vocabularies differ, and the cost of that

`coder`/`reasoner`/`fast`/`diagram` name **roles** — what the caller is doing.
`hermes-fast`/`balanced`/`deep` name **capability tiers** — how much model the
caller wants. Both are legitimate indirections and both deliver FR-003's real
benefit: swapping the model behind a name touches no client.

The cost is concrete: **a client cannot move between the two gateways
unchanged.** An opencode agent pinned to `role/coder` does not have a name to
ask for on the homelab router, and Hermes asking for `hermes-balanced` has no
name here. If a client ever needs to run against both, that is the work.

This is accepted for now because no client spans both, and because the trust
domains differ enough that a shared vocabulary would imply an
interchangeability that does not exist.

## What keeps them apart today, and what would change it

Zscaler blocks Tailscale on the dev Mac. That is why this machine cannot reach
the homelab router, cannot read the old Mac's MagicDNS name, and why
`064`'s handoff moved deployment to a Linux laptop. **The separation is
currently enforced by the network whether or not it is wanted.**

Revisit if any of these change:

- **Zscaler stops blocking the tailnet here.** The dev Mac could then address the
  homelab router directly, and the local gateway's remaining justification is
  latency and offline use — both real, but a much weaker case for two.
- **A client needs both.** Align the vocabulary first; it is cheap before a
  client binds to either and expensive afterwards.
- **A third gateway appears.** Two is a divergence; three is a pattern that
  wants a shared contract.

## Findings that transferred, and one that did not

The dev Mac setup is documented in `local-llm/docs/FINDINGS.md`. Its dominant
failure mode — six cases of configuration that read correctly, raised no error,
and did nothing — produced one finding that applies directly here:
**`context_window_fallbacks` is silently dead without
`enable_pre_call_checks`.** That is the mechanism SC-009 depends on.

This role already sets it (`config.yaml.j2:43`), independently. That is worth
stating plainly: the finding did not need transferring, and
`scripts/healthcheck/llm-router-doctor.py` asserts the flag *stays* set rather
than taking credit for putting it there.
