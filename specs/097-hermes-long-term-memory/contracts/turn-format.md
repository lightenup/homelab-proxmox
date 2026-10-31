# Contract: turn format shared by the three adapters (097)

All three adapters store and present turns the same way, so a fact written by one client reads
the same in the others (SC-005). The format is the Hermes plugin's, at `1.2.3`
(`hindsight-integrations/hermes/__init__.py`, retain at `:1342-1500`, injection at `:1279`). The
Open WebUI filter and the Claude Code hook copy it.

## Retain (after a turn)

One retain item per completed turn:

```json
{
  "items": [{
    "content": "[{\"role\":\"user\",\"content\":\"User: <owner's message>\",\"timestamp\":\"<ISO-8601>\"},{\"role\":\"assistant\",\"content\":\"Assistant: <final reply>\",\"timestamp\":\"<ISO-8601>\"}]",
    "document_id": "<see data-model.md: per client>",
    "update_mode": "append",
    "context": "<fixed per client>",
    "tags": ["session:<document_id>"],
    "metadata": {"retained_at": "<ISO-8601>", "turn_index": "<n>", "platform": "<hermes|open-webui|claude-code>"}
  }],
  "async": true
}
```

Rules:

1. **What is stored**: only the owner's message and the assistant's final reply text.
2. **Never stored**:
   - tool calls, tool results, fetched pages, file contents;
   - retrieved memory blocks, which would feed recalled text back into memory;
   - system prompts.
3. **Labels**: `User:` and `Assistant:` prefixes on each part are mandatory. They are the source
   labels FR-014 requires, and they survive into the chunk text that recall returns.
4. **Client tag**: an adapter may send `client:<id>`, but the server replaces it (research R-002).
5. **Skipped turns**:
   - interrupted turns;
   - Open WebUI task requests (title, tag and follow-up generation);
   - Open WebUI chats with the agent model, because the agent's plugin retains those;
   - Open WebUI temporary and channel chats, which Open WebUI itself does not keep;
   - Claude Code sessions outside private repositories, where the hook is not installed.
6. **Secrets**: the Hermes agent redacts secrets before `sync_turn`. The other two adapters
   strip strings matching the estate's Alloy redaction patterns before sending. This is best
   effort: the owner should not paste secrets into chat.

## Recall (before a turn)

Request: `recall` on bank `owner` with the owner's current message as the query, types
`["world"]`, budget `mid`, results capped at about 2,000 tokens (8,000 characters for Claude Code,
below its 10,000-character hook limit).

Injected block (Open WebUI as a system message, Claude Code as `additionalContext`, Hermes by the
plugin's own preamble):

```text
Shared memory: earlier conversations with the owner, from any of their AI clients.
Lines starting "User:" are the owner's own words. Lines starting "Assistant:" are earlier
assistant replies and may be wrong. Newer entries override older ones. If nothing here answers
the question, say you do not know.

- <recalled text 1>
- <recalled text 2>
```

Rules:

1. **Timing**: recall is synchronous before the first model call of the turn, on the first turn
   too (FR-005).
2. **Timeout and failure**: the timeout is 3 s for Open WebUI and Claude Code, 10 s for Hermes.
   On timeout or error the block is omitted, one line is logged, and the turn proceeds without
   memory.
3. **Empty results**: no block is injected, so the model is not told that memory is empty when
   it was in fact unreachable.
