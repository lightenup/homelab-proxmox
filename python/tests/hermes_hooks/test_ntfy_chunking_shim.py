"""Unit test for the ntfy chunking shim (spec 095 T073, research R-018).

The shim at ansible/roles/hermes/files/plugins/platforms/ntfy/__init__.py overrides the bundled
Hermes ntfy adapter, which slices chat replies to 4096 characters with only a WARNING (T008 step 7).
It runs inside the hermes-agent image and imports the bundled module, which isn't installed here,
so this test plants a stub `plugins.platforms.ntfy.adapter` in sys.modules before loading the shim
by path. The stub's `truncate_message` is a simple fixed-width splitter. The real one (base class,
verified in the container per R-018) splits on whitespace and adds (n/m) indicators. What this
test pins is the shim's own logic: which chunks get sent, in what order, what stops the loop, and
that register() forwards the bundled registration unchanged except for the adapter factory.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
import types
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
SHIM = ROOT / "ansible" / "roles" / "hermes" / "files" / "plugins" / "platforms" / "ntfy" / "__init__.py"
LIMIT = 50


class _Result:
    def __init__(self, success: bool, error: str | None = None) -> None:
        self.success = success
        self.error = error


class _FakeNtfyAdapter:
    MAX_MESSAGE_LENGTH = LIMIT
    splits_long_messages = False

    def __init__(self, config=None) -> None:
        self.config = config
        self.sent: list[tuple] = []
        self.fail_on_call: int | None = None

    @staticmethod
    def truncate_message(content: str, max_length: int = 4096, len_fn=None) -> list[str]:
        return [content[i:i + max_length] for i in range(0, len(content), max_length)] or [""]

    async def send(self, chat_id, content, reply_to=None, metadata=None):
        self.sent.append((chat_id, content, reply_to, metadata))
        if self.fail_on_call is not None and len(self.sent) == self.fail_on_call:
            return _Result(False, "boom")
        return _Result(True)


def _bundled_register(ctx) -> None:
    ctx.register_platform(
        name="ntfy", label="ntfy", adapter_factory=lambda cfg: _FakeNtfyAdapter(cfg),
        required_env=["NTFY_TOPIC"], max_message_length=LIMIT, allow_update_command=True,
        platform_hint="hint",
    )


@pytest.fixture()
def shim(monkeypatch):
    stub = types.ModuleType("plugins.platforms.ntfy.adapter")
    stub.NtfyAdapter = _FakeNtfyAdapter
    stub.MAX_MESSAGE_LENGTH = LIMIT
    stub.register = _bundled_register
    for name in ("plugins", "plugins.platforms", "plugins.platforms.ntfy"):
        monkeypatch.setitem(sys.modules, name, types.ModuleType(name))
    monkeypatch.setitem(sys.modules, "plugins.platforms.ntfy.adapter", stub)
    sys.modules["plugins.platforms.ntfy"].adapter = stub
    spec = importlib.util.spec_from_file_location("ntfy_chunking_shim_under_test", SHIM)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _send(adapter, content, **kw):
    return asyncio.run(adapter.send("hermes-lab-in", content, **kw))


def test_shim_declares_native_splitting(shim) -> None:
    assert shim.ChunkingNtfyAdapter.splits_long_messages is True
    assert issubclass(shim.ChunkingNtfyAdapter, _FakeNtfyAdapter)


def test_short_body_is_one_unchanged_call(shim) -> None:
    adapter = shim.ChunkingNtfyAdapter(None)
    result = _send(adapter, "hello", metadata={"publish_topic": "hermes-lab"})
    assert result.success
    assert adapter.sent == [("hermes-lab-in", "hello", None, {"publish_topic": "hermes-lab"})]


def test_long_body_is_sent_as_every_chunk_in_order(shim) -> None:
    adapter = shim.ChunkingNtfyAdapter(None)
    body = "".join(str(i % 10) for i in range(LIMIT * 3 + 7))
    result = _send(adapter, body, metadata={"publish_topic": "hermes-lab"})
    assert result.success
    sent_bodies = [c for _, c, _, _ in adapter.sent]
    assert "".join(sent_bodies) == body, "nothing may be lost or reordered"
    assert len(sent_bodies) == 4
    assert all(len(c) <= LIMIT for c in sent_bodies)
    assert all(m == {"publish_topic": "hermes-lab"} for _, _, _, m in adapter.sent)


def test_first_failed_chunk_stops_and_is_returned(shim) -> None:
    adapter = shim.ChunkingNtfyAdapter(None)
    adapter.fail_on_call = 2
    result = _send(adapter, "x" * (LIMIT * 3))
    assert result.success is False and result.error == "boom"
    assert len(adapter.sent) == 2, "no chunk is sent after a failure"


def test_register_forwards_everything_but_the_factory(shim) -> None:
    calls = []

    class _Ctx:
        manifest = "kept"

        def register_platform(self, **kwargs):
            calls.append(kwargs)

    ctx = _Ctx()
    shim.register(ctx)
    assert len(calls) == 1
    kwargs = calls[0]
    assert kwargs["name"] == "ntfy"
    assert kwargs["required_env"] == ["NTFY_TOPIC"]
    assert kwargs["allow_update_command"] is True
    assert kwargs["platform_hint"] == "hint"
    assert isinstance(kwargs["adapter_factory"]("cfg"), shim.ChunkingNtfyAdapter)
