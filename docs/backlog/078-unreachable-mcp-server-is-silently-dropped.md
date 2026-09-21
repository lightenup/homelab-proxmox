# An unreachable MCP server is silently dropped, with no error and no log line

**Status**: Backlog — found 2026-09-21 running spec `065`'s T039.
**Impact**: when a tool service is down, Hermes gives the owner **no signal at all**. The tool
simply is not offered to the model. Nothing is logged. Whether the conversation degrades well
depends entirely on the model's own behaviour, not on anything the system does.

## What was measured

`market_model_mcp` was stopped on its LXC (its REST API left running), confirmed unreachable
from inside the Hermes container — refused in **0.15 ms**, so there is no hang to blame. Then
a question was asked that had been answered from that tool earlier the same day.

**The two failure modes T039 rules out did not occur, and that part is a genuine pass:**

- **No indefinite wait.** The conversation completed normally.
- **No fabricated answer presented as tool output.** The model was explicit about provenance:
  *"Based on the market model MCP (market-model.hus-sky.no) — which I queried a few hours
  earlier in our 'MCP Availability Check' chat; its tools aren't in my toolset in this
  session, so this is from that recorded data"*. It then reproduced the six scenarios
  correctly, having searched its own chat history (`search_chats`, `view_chat`) to find them.

**The requirement T039 actually states was not met:** there was no readable error naming the
unreachable service, because there was no error of any kind.

```
docker logs --since 15m hermes_open_webui | grep -iE 'mcp|tool.?server|market'
# -> nothing. Not one line about the server being unreachable.
```

The model's own words give the mechanism away: *"its tools aren't in my toolset in this
session"*. The tool list is built by connecting to each registered server; a server that does
not answer is omitted, and omission is indistinguishable from never having been configured.

## Why the good outcome is not reassuring

The answer was correct and honestly attributed — but **that was the model's doing, not the
system's**. It happened to have a prior conversation to draw on and happened to disclose it.
Change any of that and the same architecture gives:

- a question with no prior history → the model answers from general knowledge, with no
  indication a tool it was supposed to use was unavailable
- a less scrupulous model, or a shorter context → the same, without the disclosure

The owner cannot tell "the tool answered" from "the tool was never offered". That is the
substance of US-3 AS-3, and it rests on model manners rather than a guarantee.

## Directions, none verified

1. **Surface the connection failure.** At minimum a log line when a registered server fails to
   list its tools; ideally a visible marker in the conversation. Whether Open WebUI can be
   configured to do this, or whether it needs an upstream change, is the first thing to check.
2. **Probe the registered servers and alert.** The estate already has the machinery: a
   `monitoring_contract` liveness target per MCP URL would make "tool service down" a
   monitoring signal rather than a silent conversational one. Cheap, and it does not depend on
   upstream behaviour — but it tells the *operator*, not the person mid-conversation.
3. **Accept it and document it.** Weakest, but honest: the two dangerous outcomes (hang,
   fabrication-as-tool-output) genuinely do not occur, and the residual risk is a missing
   capability the owner may not notice.

Option 2 is the one this estate can implement today without waiting on upstream.

## Unrelated finding from the same logs

The only errors present were an **Ollama integration nobody configured**: upstream enables it
by default at `host.docker.internal:11434`, so Hermes polled a non-existent host and logged a
connection error every few minutes (10 since start). Fixed the same day with
`ENABLE_OLLAMA_API=False` plus an entry in `hermes_managed_config`, since `ollama.enable` is
persisted and the env var alone would not have turned it off on an existing deploy.

Worth noting *why* that mattered: those errors were the only thing in the log, and they are
exactly the kind of recurring noise that trains an operator to ignore the channel — which is
how a real error goes unread.
