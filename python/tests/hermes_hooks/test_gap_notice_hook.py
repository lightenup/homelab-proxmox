"""Unit test for the gap-notice gateway hook (spec 095 T027, FR-006, research R-007).

The hook (ansible/roles/hermes/files/hooks/gap-notice/handler.py) runs inside the agent on every
gateway start and posts a silent ntfy notice naming the window in which inbound messages were not
received. Its pure functions are tested here; the handler's I/O (reading the heartbeat file and the
HTTP POST) is tested with stand-ins. It must never raise into the gateway.
"""

from __future__ import annotations

import asyncio
import importlib.util
from datetime import datetime, timezone
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
HOOK_DIR = ROOT / "ansible" / "roles" / "hermes" / "files" / "hooks" / "gap-notice"


@pytest.fixture()
def hook():
    spec = importlib.util.spec_from_file_location("gap_notice_under_test", HOOK_DIR / "handler.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PROM = (
    "# HELP hermes_agent_heartbeat_timestamp_seconds Unix time of the last scheduler heartbeat.\n"
    "# TYPE hermes_agent_heartbeat_timestamp_seconds gauge\n"
    "hermes_agent_heartbeat_timestamp_seconds 1793000000\n"
)
ENV = {
    "NTFY_SERVER_URL": "https://ntfy.example.invalid",
    "NTFY_PUBLISH_TOPIC": "hermes",
    "NTFY_TOPIC": "hermes-in",
    "NTFY_TOKEN": "tk_stub",
}


def test_manifest_listens_to_gateway_startup_only() -> None:
    manifest = (HOOK_DIR / "HOOK.yaml").read_text()
    assert "gateway:startup" in manifest
    assert "agent:" not in manifest and "command:" not in manifest


def test_parse_last_heartbeat(hook) -> None:
    assert hook.parse_last_heartbeat(PROM) == datetime.fromtimestamp(1793000000, timezone.utc)
    assert hook.parse_last_heartbeat("") is None
    assert hook.parse_last_heartbeat("hermes_agent_heartbeat_timestamp_seconds not-a-number\n") is None
    assert hook.parse_last_heartbeat(None) is None


def test_notice_names_the_window_in_oslo_time(hook) -> None:
    started = datetime(2026, 10, 26, 11, 0, 0, tzinfo=timezone.utc)  # 12:00 in Oslo (CET)
    last = datetime(2026, 10, 26, 10, 45, 0, tzinfo=timezone.utc)  # 11:45 in Oslo
    text = hook.build_gap_notice(started, last, inbound_topic="hermes-in")
    assert text == (
        "Back online at 2026-10-26 12:00. Last heartbeat 2026-10-26 11:45. "
        "Anything sent to hermes-in between 11:45 and 12:00 was not received."
    )


def test_notice_without_heartbeat_says_unknown(hook) -> None:
    started = datetime(2026, 7, 1, 10, 0, 0, tzinfo=timezone.utc)  # 12:00 in Oslo (CEST)
    text = hook.build_gap_notice(started, None, inbound_topic="hermes-in")
    assert text == (
        "Back online at 2026-07-01 12:00. Last heartbeat unknown. "
        "Anything sent to hermes-in while Hermes was offline was not received."
    )


def test_there_is_no_threshold(hook) -> None:
    """FR-006: every restart reports, even a 1-second gap."""
    started = datetime(2026, 10, 26, 11, 0, 1, tzinfo=timezone.utc)
    last = datetime(2026, 10, 26, 11, 0, 0, tzinfo=timezone.utc)
    assert "not received" in hook.build_gap_notice(started, last, inbound_topic="hermes-in")


def test_publish_headers_are_silent_and_authenticated(hook) -> None:
    headers = hook.publish_headers("tk_stub")
    assert headers["Priority"] == "2"
    assert headers["Authorization"] == "Bearer tk_stub"


def test_should_publish_only_with_token_and_topics(hook) -> None:
    assert hook.should_publish(ENV) is True
    assert hook.should_publish({k: v for k, v in ENV.items() if k != "NTFY_TOKEN"}) is False
    assert hook.should_publish({k: v for k, v in ENV.items() if k != "NTFY_PUBLISH_TOPIC"}) is False
    assert hook.should_publish({}) is False


def test_post_notice_sends_one_request_and_never_raises(hook) -> None:
    calls = []

    def fake_urlopen(request, timeout):
        calls.append((request.full_url, dict(request.header_items()), request.data, timeout))

        class _Resp:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        return _Resp()

    hook.post_notice(ENV, "hello", opener=fake_urlopen)
    assert len(calls) == 1
    url, headers, data, timeout = calls[0]
    assert url == "https://ntfy.example.invalid/hermes"
    assert headers["Priority"] == "2"
    assert data == b"hello"
    assert timeout == 10

    def boom(request, timeout):
        raise OSError("network down")

    hook.post_notice(ENV, "hello", opener=boom)  # must not raise


def test_handle_schedules_the_post_and_returns_immediately(hook, monkeypatch, tmp_path) -> None:
    beat = tmp_path / "hermes_agent.prom"
    beat.write_text(PROM)
    monkeypatch.setattr(hook, "HEARTBEAT_FILE", str(beat))
    posted = []
    monkeypatch.setattr(hook, "post_notice", lambda env, text, opener=None: posted.append((env, text)))
    for key, value in ENV.items():
        monkeypatch.setenv(key, value)

    async def run():
        await hook.handle("gateway:startup", {"platforms": ["ntfy"]})
        await asyncio.gather(*hook._PENDING)

    asyncio.run(run())
    assert len(posted) == 1
    assert "Last heartbeat" in posted[0][1] and "hermes-in" in posted[0][1]


def test_handle_skips_without_token(hook, monkeypatch) -> None:
    for key in ENV:
        monkeypatch.delenv(key, raising=False)
    posted = []
    monkeypatch.setattr(hook, "post_notice", lambda env, text, opener=None: posted.append(text))
    asyncio.run(hook.handle("gateway:startup", {"platforms": []}))
    assert posted == []
