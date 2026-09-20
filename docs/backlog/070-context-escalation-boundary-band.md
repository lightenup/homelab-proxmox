# Backlog: prompts just above 131k are rejected instead of escalating

**Status**: Backlog — measured 2026-09-20 while closing `064`'s T038. Narrow but real.
**Impact**: a prompt whose true token count sits in a narrow band above `reasoner`'s
131,072 window fails with a 400 instead of escalating to `qwen-long`.

## What happens

| prompt | result |
|---|---|
| 132,658 tokens | **400 in 0.56s** — `Prompt too long: 132658 tokens exceeds max context window of 131072 tokens` |
| 170,305 tokens | **200 in 901.8s** — escalated to `qwen-long` and served |

So the escalation mechanism works. Only the band immediately above the boundary is broken.

## Why

The Mac's configuration is correct:

```yaml
- model_name: reasoner
  model_info: { max_input_tokens: 131072 }
- model_name: Qwen3.8-27B-8bit:qwen-long
  model_info: { max_input_tokens: 262144 }
router_settings:
  enable_pre_call_checks: true
  context_window_fallbacks:
    - reasoner: ["Qwen3.8-27B-8bit:qwen-long"]
```

`enable_pre_call_checks` decides whether to escalate by **estimating** the prompt's token
count with LiteLLM's own tokenizer. That estimate undercounts relative to oMLX's actual
tokenizer, so a prompt truly at 132,658 is estimated below 131,072, `reasoner` still looks
viable, the request is sent there, and oMLX rejects it. The proxy then reports
`No fallback model group found for original model_group=reasoner. Fallbacks=[]` — it is
looking at the general `fallbacks` list, not `context_window_fallbacks`, because as far as
the pre-call check was concerned no escalation was needed.

At 170k the estimate clears 131,072 even after undercounting, so the escalation fires
normally. At 431k it exceeds even `qwen-long`, and the pre-call check correctly refuses with
"No models have context window large enough" — which confirms the check itself works.

The error band is therefore roughly 131,072 up to wherever the estimate catches up —
somewhere under 140k on this corpus, but it depends on the text, since tokenizer divergence
is content-dependent.

## Options

1. **Lower `reasoner`'s declared `max_input_tokens`** on the Mac to absorb the estimation
   error — say 124,000. Escalation then fires early and the band disappears. Costs a little
   usable context on the non-escalated path, and it is a one-line change on the Mac.
2. **Make LiteLLM count rather than estimate** for this deployment, if the pinned version
   supports a custom tokenizer for an `openai/`-style backend. Needs research.
3. **Leave it and document the band** — the current state. Acceptable because the failure is
   fast, loud and legible, not a hang or a silent truncation.

Option 1 is the cheap and honest fix, and it is on the Mac rather than in this repo.

## Not to be confused with

This is unrelated to backlog 069 (the ~300s transport ceiling, resolved by TLS). That one
prevented long requests from completing at all; this one is a token-accounting edge at a
specific boundary, and it was only observable *because* 069 was fixed.
