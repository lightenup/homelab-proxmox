"""Gap notice on gateway start (spec 095 FR-006, US3; research R-007).

The ntfy adapter subscribes without `since=`, so nothing sent to the inbound topic while the agent
was down is ever replayed. On every gateway start this hook posts one silent (priority 2) notice
naming that window: from the scheduler's last heartbeat to now. No threshold: restarts are rare
(deploys), and a missing notice must never be mistaken for "nothing was missed".

- Heartbeat: /heartbeat/hermes_agent.prom, written every 15 min by the PROD heartbeat job and
  mounted on PROD only. Absent elsewhere: the notice says "Last heartbeat unknown".
- Skips when NTFY_TOKEN or NTFY_PUBLISH_TOPIC is absent (the pipeline LAB stage renders no ntfy).
- Never blocks or breaks the gateway: the POST runs in a worker thread, startup does not wait for
  it, and every failure is logged in one line, never raised.

Static file, standard library only, copied (not templated) so pytest can import it
(python/tests/hermes_hooks/test_gap_notice_hook.py). Mounted read-only.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

logger = logging.getLogger("hooks.gap_notice")

HEARTBEAT_FILE = "/heartbeat/hermes_agent.prom"
LOCAL_TZ = ZoneInfo("Europe/Oslo")
_METRIC = re.compile(r"^hermes_agent_heartbeat_timestamp_seconds\s+(\d+(?:\.\d+)?)\s*$", re.M)
_PENDING: set = set()  # strong refs to in-flight posts, so they are not garbage-collected


def parse_last_heartbeat(prom_text):
    """UTC time of the last heartbeat from the textfile-collector file, or None."""
    if not prom_text:
        return None
    match = _METRIC.search(prom_text)
    if not match:
        return None
    return datetime.fromtimestamp(float(match.group(1)), timezone.utc)


def build_gap_notice(started_at, last_heartbeat_at, inbound_topic):
    """The notice text, in Oslo local time. No threshold (FR-006)."""
    start = started_at.astimezone(LOCAL_TZ)
    if last_heartbeat_at is None:
        return (
            f"Back online at {start:%Y-%m-%d %H:%M}. Last heartbeat unknown. "
            f"Anything sent to {inbound_topic} while Hermes was offline was not received."
        )
    last = last_heartbeat_at.astimezone(LOCAL_TZ)
    return (
        f"Back online at {start:%Y-%m-%d %H:%M}. Last heartbeat {last:%Y-%m-%d %H:%M}. "
        f"Anything sent to {inbound_topic} between {last:%H:%M} and {start:%H:%M} was not received."
    )


def publish_headers(token):
    return {
        "Authorization": f"Bearer {token}",
        "Priority": "2",  # silent: restarts stay quiet (083), but are never invisible (FR-006)
        "Tags": "hermes-agent,gap-notice",
    }


def should_publish(env):
    return bool(env.get("NTFY_TOKEN") and env.get("NTFY_PUBLISH_TOPIC") and env.get("NTFY_SERVER_URL"))


def post_notice(env, text, opener=None):
    """POST the notice to the publish topic. Logs one line on failure; never raises."""
    opener = opener or urllib.request.urlopen
    url = f"{env['NTFY_SERVER_URL'].rstrip('/')}/{env['NTFY_PUBLISH_TOPIC']}"
    request = urllib.request.Request(
        url, data=text.encode("utf-8"), headers=publish_headers(env["NTFY_TOKEN"]), method="POST"
    )
    try:
        with opener(request, timeout=10) as response:
            status = getattr(response, "status", 200)
            if status >= 300:
                logger.warning("gap-notice: ntfy answered %s", status)
    except Exception as exc:  # never break the gateway
        logger.warning("gap-notice: post failed: %s", exc)


def _read_heartbeat():
    try:
        with open(HEARTBEAT_FILE, encoding="utf-8") as fh:
            return parse_last_heartbeat(fh.read())
    except OSError:
        return None


async def handle(event_type, context):
    """gateway:startup: schedule the notice and return at once (startup never waits on ntfy)."""
    try:
        env = dict(os.environ)
        if not should_publish(env):
            return
        text = build_gap_notice(
            datetime.now(timezone.utc), _read_heartbeat(), env.get("NTFY_TOPIC") or "the inbound topic"
        )
        task = asyncio.get_running_loop().create_task(asyncio.to_thread(post_notice, env, text))
        _PENDING.add(task)
        task.add_done_callback(_PENDING.discard)
    except Exception as exc:  # never break the gateway
        logger.warning("gap-notice: skipped: %s", exc)
