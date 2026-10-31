"""Unit test for the Open WebUI shared-memory filter (spec 097 T039, research R-007).

The filter at ansible/roles/hermes/files/open_webui/memory_filter.py runs inside Open WebUI
0.11.3, which ships `requests` and `pydantic`. Neither is in the test venv, so this test plants
stubs for both before loading the filter by path (the same approach as the ntfy shim test). HTTP
is the stub: every call is recorded and answered by a per-test handler.

What is pinned here is the filter's own contract (contracts/turn-format.md):

- inlet: one system message with the recall preamble, verbatim; nothing on empty results; fail
  open within the timeout with one log line; skip task requests and the agent's models.
- outlet: exactly the contract's retain JSON, built from the last user and assistant pair only,
  with tool output, injected memory and secrets removed.

The preamble's agreement with the contract file itself is checked in
python/tests/guardrails/test_hermes_memory_config.py (specs/ is not copied for mutation runs).
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import logging
import sys
import threading
import time
import types
from datetime import datetime
from pathlib import Path

import pytest


def _find_repo_root(start: Path) -> Path:
    current = start
    for _ in range(20):
        if (current / ".git").exists() and (current / "python").exists():
            return current
        if (current / "Taskfile.yml").exists() and (current / "python").exists():
            return current
        current = current.parent
    raise RuntimeError("Unable to locate repository root")


ROOT = _find_repo_root(Path(__file__).resolve())
FILTER = ROOT / "ansible" / "roles" / "hermes" / "files" / "open_webui" / "memory_filter.py"

URL = "https://memory-api.example.test"
KEY = "hmem_test_openwebui_0123456789abcdefghijklmnop"
AGENT = "hermes-agent"
CHAT = "3f1c2a9e-0000-4000-8000-000000000001"

PREAMBLE = (
    "Shared memory: earlier conversations with the owner, from any of their AI clients.\n"
    'Lines starting "User:" are the owner\'s own words. Lines starting "Assistant:" are earlier\n'
    "assistant replies and may be wrong. Newer entries override older ones. If nothing here answers\n"
    "the question, say you do not know."
)


# --------------------------------------------------------------------------- stubs


_MISSING = object()


class _FieldInfo:
    def __init__(self, default=_MISSING, default_factory=None):
        self.default = default
        self.default_factory = default_factory


def _field(default=_MISSING, *, default_factory=None, **_kwargs):
    return _FieldInfo(default, default_factory)


class _BaseModel:
    """Enough of pydantic.BaseModel for Valves(**stored): declared fields, defaults, overrides."""

    def __init__(self, **data):
        for name in getattr(type(self), "__annotations__", {}):
            if name in data:
                setattr(self, name, data[name])
                continue
            declared = getattr(type(self), name, _MISSING)
            if isinstance(declared, _FieldInfo):
                declared = declared.default_factory() if declared.default_factory else declared.default
            setattr(self, name, declared)


class _Response:
    def __init__(self, status: int, payload: dict):
        self.status_code = status
        self._payload = payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise _RequestException(f"HTTP {self.status_code}")

    def json(self) -> dict:
        return self._payload


class _RequestException(Exception):
    pass


class _Timeout(_RequestException):
    pass


class _FakeRequests(types.ModuleType):
    RequestException = _RequestException
    Timeout = _Timeout

    def __init__(self) -> None:
        super().__init__("requests")
        self.calls: list[dict] = []
        self.handler = lambda url, payload: _Response(200, {"results": []})

    def post(self, url, json=None, headers=None, timeout=None):  # noqa: A002 - requests' signature
        self.calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        return self.handler(url, json)


@pytest.fixture
def http(monkeypatch) -> _FakeRequests:
    fake = _FakeRequests()
    monkeypatch.setitem(sys.modules, "requests", fake)
    pydantic = types.ModuleType("pydantic")
    pydantic.BaseModel = _BaseModel
    pydantic.Field = _field
    monkeypatch.setitem(sys.modules, "pydantic", pydantic)
    return fake


def _load(http: _FakeRequests, **valves):
    spec = importlib.util.spec_from_file_location("function_shared_memory", FILTER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    flt = module.Filter()
    flt.valves = module.Filter.Valves(
        **{"url": URL, "key": KEY, "agent_model_ids": [AGENT], **valves}
    )
    return module, flt


def _run(coro):
    return asyncio.run(coro)


def _recall_returns(*texts: str):
    return lambda url, payload: _Response(200, {"results": [{"text": t, "type": "world"} for t in texts]})


def _chat(*messages: tuple[str, object], model: str = "coder") -> dict:
    return {"model": model, "messages": [{"role": r, "content": c} for r, c in messages]}


def _outlet_body(*messages: tuple[str, object], model: str = "coder", chat_id: str = CHAT) -> dict:
    body = _chat(*messages, model=model)
    body["chat_id"] = chat_id
    return body


# --------------------------------------------------------------------------- inlet


def test_inlet_injects_one_system_message_with_the_preamble_verbatim(http):
    _, flt = _load(http)
    http.handler = _recall_returns("User: my sister lives in Tromsø", "Assistant: noted")
    body = _run(flt.inlet(_chat(("user", "Where does my sister live?")), __user__={}, __metadata__={}))
    system = [m for m in body["messages"] if m["role"] == "system"]
    assert len(system) == 1
    assert body["messages"][0] is system[0]
    assert system[0]["content"] == (
        PREAMBLE + "\n\n- User: my sister lives in Tromsø\n- Assistant: noted"
    )
    assert body["messages"][-1] == {"role": "user", "content": "Where does my sister live?"}


def test_inlet_recall_request_matches_the_contract(http):
    _, flt = _load(http)
    _run(flt.inlet(_chat(("user", "first"), ("assistant", "ok"), ("user", "Hva heter hunden min?")),
                   __metadata__={}))
    assert len(http.calls) == 1
    call = http.calls[0]
    assert call["url"] == f"{URL}/v1/default/banks/owner/memories/recall"
    assert call["headers"]["Authorization"] == f"Bearer {KEY}"
    assert call["json"]["query"] == "Hva heter hunden min?"
    assert call["json"]["types"] == ["world"]
    assert call["json"]["budget"] == "mid"
    assert call["json"]["max_tokens"] == 2000
    assert call["timeout"] == 3


def test_inlet_uses_the_bank_valve(http):
    _, flt = _load(http, bank="other")
    _run(flt.inlet(_chat(("user", "q")), __metadata__={}))
    assert http.calls[0]["url"] == f"{URL}/v1/default/banks/other/memories/recall"


def test_inlet_reads_the_text_part_of_a_multimodal_message(http):
    _, flt = _load(http)
    content = [{"type": "image_url", "image_url": {"url": "data:..."}}, {"type": "text", "text": "what is this?"}]
    _run(flt.inlet(_chat(("user", content)), __metadata__={}))
    assert http.calls[0]["json"]["query"] == "what is this?"


def test_inlet_merges_into_an_existing_system_message(http):
    """One system message, first: some chat templates refuse a second or a later one."""
    _, flt = _load(http)
    http.handler = _recall_returns("User: fact")
    body = _run(flt.inlet(_chat(("system", "Be brief."), ("user", "q")), __metadata__={}))
    system = [m for m in body["messages"] if m["role"] == "system"]
    assert len(system) == 1
    assert system[0]["content"] == "Be brief.\n\n" + PREAMBLE + "\n\n- User: fact"


def test_inlet_injects_nothing_on_empty_results(http):
    _, flt = _load(http)
    original = _chat(("user", "q"))
    body = _run(flt.inlet(json.loads(json.dumps(original)), __metadata__={}))
    assert body == original


def test_inlet_caps_the_block_at_about_8000_characters(http):
    module, flt = _load(http)
    http.handler = _recall_returns(*["User: " + "x" * 900 for _ in range(20)])
    body = _run(flt.inlet(_chat(("user", "q")), __metadata__={}))
    content = body["messages"][0]["content"]
    assert content.startswith(PREAMBLE)
    assert len(content) <= module.MAX_BLOCK_CHARS == 8000
    assert content.count("\n- User: ") >= 7


def test_inlet_fails_open_on_an_error_with_one_log_line(http, caplog):
    def boom(url, payload):
        raise http.RequestException("connection refused")

    http.handler = boom
    _, flt = _load(http)
    original = _chat(("user", "q"))
    with caplog.at_level(logging.DEBUG):
        body = _run(flt.inlet(json.loads(json.dumps(original)), __metadata__={}))
    assert body == original
    lines = [r for r in caplog.records if r.name == "function_shared_memory"]
    assert len(lines) == 1
    assert lines[0].levelno == logging.WARNING
    assert "recall" in lines[0].getMessage()


def test_inlet_fails_open_on_an_http_error_status(http, caplog):
    http.handler = lambda url, payload: _Response(403, {"detail": "scope readonly may not retain"})
    _, flt = _load(http)
    with caplog.at_level(logging.WARNING):
        body = _run(flt.inlet(_chat(("user", "q")), __metadata__={}))
    assert [m["role"] for m in body["messages"]] == ["user"]
    assert len([r for r in caplog.records if r.name == "function_shared_memory"]) == 1


def test_inlet_fails_open_within_the_timeout_when_the_server_hangs(http, caplog):
    release = threading.Event()

    def hang(url, payload):
        release.wait(10)
        return _Response(200, {"results": [{"text": "too late"}]})

    http.handler = hang
    _, flt = _load(http, timeout_s=0.2)

    async def scenario():
        start = time.monotonic()
        body = await flt.inlet(_chat(("user", "q")), __metadata__={})
        elapsed = time.monotonic() - start
        release.set()
        return body, elapsed

    with caplog.at_level(logging.WARNING):
        body, elapsed = _run(scenario())
    assert elapsed < 1.5
    assert [m["role"] for m in body["messages"]] == ["user"]
    assert len([r for r in caplog.records if r.name == "function_shared_memory"]) == 1


def test_default_timeout_is_three_seconds(http):
    module, _ = _load(http)
    assert module.Filter.Valves().timeout_s == 3
    assert module.Filter.Valves().bank == "owner"
    assert module.Filter.Valves().agent_model_ids == []


def test_inlet_never_logs_the_key(http, caplog):
    def boom(url, payload):
        raise http.RequestException(f"bad header Bearer {KEY}")

    http.handler = boom
    _, flt = _load(http)
    with caplog.at_level(logging.DEBUG):
        _run(flt.inlet(_chat(("user", "q")), __metadata__={}))
    assert KEY not in caplog.text


@pytest.mark.parametrize("task", ["title_generation", "tags_generation", "follow_up_generation"])
def test_inlet_skips_task_requests(http, task):
    _, flt = _load(http)
    original = _chat(("user", "q"))
    body = _run(flt.inlet(json.loads(json.dumps(original)), __metadata__={"task": task}))
    assert body == original
    assert http.calls == []


def test_inlet_skips_the_agent_models(http):
    """The agent's own plugin recalls and retains those turns (R-007)."""
    _, flt = _load(http, agent_model_ids=["hermes-agent", "hermes-agent-fast"])
    for model in ("hermes-agent", "hermes-agent-fast"):
        _run(flt.inlet(_chat(("user", "q"), model=model), __metadata__={}))
    assert http.calls == []


def test_inlet_skips_a_workspace_model_built_on_the_agent(http):
    _, flt = _load(http)
    model = {"id": "my-agent", "info": {"base_model_id": AGENT}}
    _run(flt.inlet(_chat(("user", "q"), model="my-agent"), __metadata__={}, __model__=model))
    assert http.calls == []


def test_inlet_does_nothing_without_url_or_key(http):
    _, flt = _load(http, key="")
    _run(flt.inlet(_chat(("user", "q")), __metadata__={}))
    _, flt = _load(http, url="")
    _run(flt.inlet(_chat(("user", "q")), __metadata__={}))
    assert http.calls == []


def test_inlet_without_a_user_message_does_nothing(http):
    _, flt = _load(http)
    _run(flt.inlet(_chat(("system", "s")), __metadata__={}))
    _run(flt.inlet({"model": "coder", "messages": []}, __metadata__={}))
    assert http.calls == []


# --------------------------------------------------------------------------- outlet


def _retained(http: _FakeRequests) -> dict:
    assert len(http.calls) == 1
    call = http.calls[0]
    assert call["url"] == f"{URL}/v1/default/banks/owner/memories"
    assert call["headers"]["Authorization"] == f"Bearer {KEY}"
    return call["json"]


def _iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    assert parsed.tzinfo is not None
    return parsed


def test_outlet_builds_exactly_the_contract_retain_json(http):
    _, flt = _load(http)
    body = _outlet_body(
        ("user", "My sister lives in Tromsø."),
        ("assistant", "Noted, Tromsø."),
        ("user", "And she works as a marine biologist."),
        ("assistant", "Got it."),
    )
    returned = _run(flt.outlet(body, __user__={}, __metadata__={"chat_id": CHAT}))
    assert returned is body
    payload = _retained(http)
    assert set(payload) == {"items", "async"}
    assert payload["async"] is True
    assert len(payload["items"]) == 1
    item = payload["items"][0]
    assert set(item) == {"content", "document_id", "update_mode", "context", "tags", "metadata"}
    assert item["document_id"] == f"owui-{CHAT}"
    assert item["update_mode"] == "append"
    assert item["context"] == "conversation between Open WebUI and the User"
    assert item["tags"] == [f"session:owui-{CHAT}"]
    assert set(item["metadata"]) == {"retained_at", "turn_index", "platform"}
    assert item["metadata"]["platform"] == "open-webui"
    assert item["metadata"]["turn_index"] == "2"
    _iso(item["metadata"]["retained_at"])
    turn = json.loads(item["content"])
    assert [(m["role"], m["content"]) for m in turn] == [
        ("user", "User: And she works as a marine biologist."),
        ("assistant", "Assistant: Got it."),
    ]
    assert all(set(m) == {"role", "content", "timestamp"} for m in turn)
    assert turn[0]["timestamp"] == turn[1]["timestamp"]
    _iso(turn[0]["timestamp"])
    assert http.calls[0]["timeout"] == 3


def test_outlet_keeps_non_ascii_text_readable(http):
    _, flt = _load(http)
    _run(flt.outlet(_outlet_body(("user", "Hunden min heter Tinde."), ("assistant", "Så fint!")), __metadata__={}))
    assert "Så fint!" in _retained(http)["items"][0]["content"]


def test_outlet_drops_tool_messages_and_tool_output_blocks(http):
    _, flt = _load(http)
    body = _outlet_body(
        ("user", "What's the weather?"),
        ("assistant", ""),
        ("tool", '{"temp": 4, "page": "<html>fetched</html>"}'),
        ("assistant", '<details type="tool_calls" done="true">\n<summary>weather</summary>\n'
                      'result: {"temp": 4}\n</details>\nIt is 4 degrees.'),
    )
    _run(flt.outlet(body, __metadata__={}))
    turn = json.loads(_retained(http)["items"][0]["content"])
    assert [m["content"] for m in turn] == ["User: What's the weather?", "Assistant: It is 4 degrees."]
    assert "fetched" not in json.dumps(turn) and "temp" not in json.dumps(turn)


def test_outlet_drops_any_injected_memory_block(http):
    _, flt = _load(http)
    block = PREAMBLE + "\n\n- User: old fact"
    body = _outlet_body(("system", block), ("user", block), ("user", "new question"), ("assistant", "answer"))
    _run(flt.outlet(body, __metadata__={}))
    content = _retained(http)["items"][0]["content"]
    assert "Shared memory:" not in content and "old fact" not in content
    assert json.loads(content)[0]["content"] == "User: new question"


def test_outlet_strips_secrets(http):
    _, flt = _load(http)
    leaked = "hmem_" + "A1b2C3d4E5f6G7h8I9j0_-kL"
    body = _outlet_body(("user", f"my key is {leaked} ok"), ("assistant", f"Do not share {leaked}."))
    _run(flt.outlet(body, __metadata__={}))
    content = _retained(http)["items"][0]["content"]
    assert "hmem_" not in content
    assert "my key is <redacted> ok" in content


def test_outlet_keeps_a_short_hmem_like_word(http):
    """The Alloy pattern needs 20 characters after the prefix; shorter words are not keys."""
    _, flt = _load(http)
    _run(flt.outlet(_outlet_body(("user", "what is hmem_short?"), ("assistant", "a prefix")), __metadata__={}))
    assert "hmem_short" in _retained(http)["items"][0]["content"]


def test_outlet_skips_an_interrupted_turn(http):
    _, flt = _load(http)
    _run(flt.outlet(_outlet_body(("user", "q"), ("assistant", "a"), ("user", "unanswered")), __metadata__={}))
    _run(flt.outlet(_outlet_body(("user", "q"), ("assistant", "  ")), __metadata__={}))
    assert http.calls == []


def test_outlet_skips_task_requests_and_agent_models(http):
    _, flt = _load(http)
    _run(flt.outlet(_outlet_body(("user", "q"), ("assistant", "a")), __metadata__={"task": "title_generation"}))
    _run(flt.outlet(_outlet_body(("user", "q"), ("assistant", "a"), model=AGENT), __metadata__={}))
    assert http.calls == []


@pytest.mark.parametrize("chat_id", ["", None, "temporary:abc", "local:abc", "channel:abc"])
def test_outlet_skips_chats_that_are_not_saved(http, chat_id):
    """Temporary and channel chats are not kept by Open WebUI either, so not by memory."""
    _, flt = _load(http)
    body = _outlet_body(("user", "q"), ("assistant", "a"), chat_id=chat_id)
    _run(flt.outlet(body, __metadata__={"chat_id": chat_id}))
    assert http.calls == []


def test_outlet_falls_back_to_the_metadata_chat_id(http):
    _, flt = _load(http)
    body = _chat(("user", "q"), ("assistant", "a"))
    _run(flt.outlet(body, __metadata__={"chat_id": CHAT}))
    assert _retained(http)["items"][0]["document_id"] == f"owui-{CHAT}"


def test_outlet_fails_open_with_one_log_line(http, caplog):
    def boom(url, payload):
        raise http.Timeout("read timed out")

    http.handler = boom
    _, flt = _load(http)
    body = _outlet_body(("user", "q"), ("assistant", "a"))
    with caplog.at_level(logging.DEBUG):
        returned = _run(flt.outlet(body, __metadata__={}))
    assert returned is body
    lines = [r for r in caplog.records if r.name == "function_shared_memory"]
    assert len(lines) == 1 and "retain" in lines[0].getMessage()


def test_outlet_does_nothing_without_a_key(http):
    _, flt = _load(http, key="")
    _run(flt.outlet(_outlet_body(("user", "q"), ("assistant", "a")), __metadata__={}))
    assert http.calls == []


# --------------------------------------------------------------------------- loading


def test_source_survives_open_webui_import_rewriting():
    """Open WebUI rewrites these prefixes in stored function content (utils/plugin.py
    replace_imports) and writes the result back, which would make the deploy's content
    comparison flap."""
    source = FILTER.read_text()
    for prefix in ("from utils", "from apps", "from main", "from config"):
        assert prefix not in source, prefix


def test_frontmatter_installs_no_requirements():
    """A `requirements:` frontmatter line makes Open WebUI pip-install at load time."""
    head = FILTER.read_text().split('"""', 2)[1]
    assert "requirements:" not in head
    assert "title: Shared memory" in head
