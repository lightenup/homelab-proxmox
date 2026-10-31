"""
title: Shared memory
author: homelab-proxmox (spec 097)
version: 1.0.0
description: Recall from the shared memory before a turn, retain the turn after it.
"""

# Deployed by the hermes role as the global filter `shared_memory` (097 T042), with valves set
# by the deploy. Turn format and recall preamble: specs/097-hermes-long-term-memory/contracts/
# turn-format.md. Both directions fail open: memory never blocks a chat (FR-006).
# Chats with the agent's models are skipped; the agent's own plugin recalls and retains them.

import asyncio
import json
import logging
import re
from datetime import datetime, timezone

import requests
from pydantic import BaseModel, Field

log = logging.getLogger(__name__)

PREAMBLE = (
    "Shared memory: earlier conversations with the owner, from any of their AI clients.\n"
    'Lines starting "User:" are the owner\'s own words. Lines starting "Assistant:" are earlier\n'
    "assistant replies and may be wrong. Newer entries override older ones. If nothing here answers\n"
    "the question, say you do not know."
)
MAX_BLOCK_CHARS = 8000
CONTEXT = "conversation between Open WebUI and the User"
# Temporary and channel chats are not kept by Open WebUI (utils/chat_id.py), so not here either.
UNSAVED_CHAT_PREFIXES = ("temporary:", "local:", "channel:")
# Tool calls, tool results and reasoning are serialised into <details> blocks; Open WebUI strips
# the same blocks before its own task prompts (utils/middleware.py).
DETAILS = re.compile(r"<details\b[^>]*>.*?</details>", re.S | re.I)
# The token-shaped patterns of the estate's Alloy redaction list (roles/alloy/defaults).
SECRETS = (
    r"hmem_[A-Za-z0-9_-]{20,}",
    r"\bsk-[A-Za-z0-9_-]{8,}",
    r"tk_[A-Za-z0-9]{29}",
    r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}",
    r"tskey-[A-Za-z0-9_-]+",
)
SECRET = re.compile("|".join(SECRETS))


def _redact(text):
    return SECRET.sub("<redacted>", text)


def _text(content):
    if isinstance(content, list):
        content = "\n".join(p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text")
    return content if isinstance(content, str) else ""


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Filter:
    class Valves(BaseModel):
        url: str = Field(default="", description="Memory API base URL, through Caddy")
        key: str = Field(default="", description="This client's memory key (hmem_...)")
        bank: str = Field(default="owner", description="Memory bank")
        agent_model_ids: list[str] = Field(default_factory=list, description="Models served by the agent")
        timeout_s: float = Field(default=3, description="Per-call limit in seconds")

    def __init__(self):
        self.valves = self.Valves()

    def _skip(self, body, metadata, model):
        if not (self.valves.url and self.valves.key) or (metadata or {}).get("task"):
            return True
        base = ((model or {}).get("info") or {}).get("base_model_id")
        return bool({body.get("model"), base} & set(self.valves.agent_model_ids))

    def _post(self, path, payload):
        response = requests.post(
            f"{self.valves.url.rstrip('/')}/v1/default/banks/{self.valves.bank}{path}",
            json=payload,
            headers={"Authorization": f"Bearer {self.valves.key}"},
            timeout=self.valves.timeout_s,
        )
        response.raise_for_status()
        return response.json()

    async def _call(self, what, path, payload):
        """One HTTP call, bounded by the timeout; on any failure one log line and None."""
        try:
            return await asyncio.wait_for(asyncio.to_thread(self._post, path, payload), self.valves.timeout_s)
        except Exception as e:  # fail open: memory never blocks a chat
            log.warning("shared memory %s failed, continuing without it: %s %s",
                        what, type(e).__name__, _redact(str(e))[:200])
            return None

    async def inlet(self, body, __user__=None, __metadata__=None, __model__=None):
        messages = body.get("messages") or []
        users = [m for m in messages if m.get("role") == "user"]
        query = _text(users[-1].get("content")).strip() if users else ""
        if not query or self._skip(body, __metadata__, __model__):
            return body
        recalled = await self._call(
            "recall", "/memories/recall",
            {"query": query, "types": ["world"], "budget": "mid", "max_tokens": 2000},
        )
        texts = [r.get("text") for r in (recalled or {}).get("results") or [] if r.get("text")]
        if not texts:
            return body
        block = PREAMBLE + "\n"
        for text in texts:
            line = f"\n- {text}"
            if len(block) + len(line) > MAX_BLOCK_CHARS:
                break
            block += line
        if messages[0].get("role") == "system":
            messages[0]["content"] = f"{_text(messages[0].get('content'))}\n\n{block}"
        else:
            messages.insert(0, {"role": "system", "content": block})
        return body

    def build_retain(self, messages, chat_id):
        """The contract's retain payload for the last completed turn, or None."""
        turns = []
        for m in messages:
            text = DETAILS.sub("", _text(m.get("content"))).strip()
            if m.get("role") in ("user", "assistant") and text and not text.startswith(PREAMBLE.split("\n")[0]):
                turns.append((m["role"], _redact(text)))
        if not turns or turns[-1][0] != "assistant" or not any(r == "user" for r, _ in turns):
            return None
        user = next(text for role, text in reversed(turns) if role == "user")
        now = _now()
        content = [
            {"role": "user", "content": f"User: {user}", "timestamp": now},
            {"role": "assistant", "content": f"Assistant: {turns[-1][1]}", "timestamp": now},
        ]
        document_id = f"owui-{chat_id}"
        return {
            "items": [{
                "content": json.dumps(content, ensure_ascii=False),
                "document_id": document_id,
                "update_mode": "append",
                "context": CONTEXT,
                "tags": [f"session:{document_id}"],
                "metadata": {
                    "retained_at": now,
                    "turn_index": str(sum(role == "user" for role, _ in turns)),
                    "platform": "open-webui",
                },
            }],
            "async": True,
        }

    async def outlet(self, body, __user__=None, __metadata__=None, __model__=None):
        chat_id = body.get("chat_id") or (__metadata__ or {}).get("chat_id") or ""
        if not chat_id or chat_id.startswith(UNSAVED_CHAT_PREFIXES) or self._skip(body, __metadata__, __model__):
            return body
        payload = self.build_retain(body.get("messages") or [], chat_id)
        if payload:
            await self._call("retain", "/memories", payload)
        return body
