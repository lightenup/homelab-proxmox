"""Behaviour tests for the pve alerting heartbeat script (alerting-heartbeat.sh).

The script is the out-of-band check of the whole alerting path: it asks the monitoring LXC's
Alertmanager whether the always-firing Watchdog alert is active and, if it is not for
FAIL_THRESHOLD consecutive runs, pages Pushover directly (not through Alertmanager, which is
what it is checking). These tests run the real script against local stand-ins for
Alertmanager and Pushover.
"""

from __future__ import annotations

import http.server
import json
import os
import subprocess
import threading
import urllib.parse
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


SCRIPT = _find_repo_root(Path(__file__).resolve()) / "ansible/roles/alerting_heartbeat/files/alerting-heartbeat.sh"

WATCHDOG = [{"labels": {"alertname": "Watchdog", "severity": "none"}, "status": {"state": "active"}}]


class _Fake:
    """One local HTTP server playing Alertmanager (GET /api/v2/alerts) and Pushover (POST)."""

    def __init__(self):
        self.alerts: list | None = WATCHDOG  # None => answer 500
        self.am_queries: list[dict] = []
        self.pushes: list[dict] = []
        self.push_status = 200
        fake = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                url = urllib.parse.urlparse(self.path)
                fake.am_queries.append(urllib.parse.parse_qs(url.query))
                if url.path != "/api/v2/alerts" or fake.alerts is None:
                    self.send_response(500)
                    self.end_headers()
                    return
                body = json.dumps(fake.alerts).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                n = int(self.headers.get("Content-Length", 0))
                fake.pushes.append({k: v[0] for k, v in urllib.parse.parse_qs(self.rfile.read(n).decode()).items()})
                self.send_response(fake.push_status)
                self.end_headers()
                self.wfile.write(b'{"status":1}')

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()


@pytest.fixture
def fake():
    f = _Fake()
    yield f
    f.close()


@pytest.fixture
def run(fake, tmp_path):
    def _run(now: int = 1_800_000_000, **env_over):
        env = {
            "PATH": os.environ["PATH"],
            "AM_URL": fake.url,
            "PUSHOVER_URL": f"{fake.url}/1/messages.json",
            "PUSHOVER_USER_KEY": "STUB-user",
            "PUSHOVER_API_TOKEN": "STUB-token",
            "STATE_DIR": str(tmp_path),
            "FAIL_THRESHOLD": "3",
            "REPEAT_SECONDS": "21600",
            "NOW": str(now),
            **env_over,
        }
        return subprocess.run(["bash", str(SCRIPT)], env=env, capture_output=True, text=True, timeout=30)

    return _run


def test_script_parses():
    assert subprocess.run(["bash", "-n", str(SCRIPT)]).returncode == 0


def test_healthy_when_watchdog_active_and_queries_only_unsilenced_active_watchdog(fake, run):
    r = run()
    assert r.returncode == 0, r.stderr
    assert fake.pushes == []
    q = fake.am_queries[0]
    assert q["filter"] == ['alertname="Watchdog"']
    assert q["active"] == ["true"] and q["silenced"] == ["false"] and q["inhibited"] == ["false"]


def test_missing_watchdog_pages_only_after_threshold_consecutive_failures(fake, run):
    fake.alerts = []
    for i in range(2):
        r = run(now=1_800_000_000 + i * 300)
        assert r.returncode == 1
    assert fake.pushes == [], "must not page before FAIL_THRESHOLD runs"
    run(now=1_800_000_600)
    assert len(fake.pushes) == 1
    p = fake.pushes[0]
    assert p["token"] == "STUB-token" and p["user"] == "STUB-user"
    assert "DOWN" in p["title"] and "Watchdog" in p["message"]
    assert p["priority"] == "1"


def test_unreachable_alertmanager_counts_as_failure(fake, run):
    fake.alerts = None
    for i in range(3):
        run(now=1_800_000_000 + i * 300)
    assert len(fake.pushes) == 1
    assert "unreachable" in fake.pushes[0]["message"].lower() or "http" in fake.pushes[0]["message"].lower()


def test_one_healthy_run_resets_the_failure_count(fake, run):
    fake.alerts = []
    run(now=1_800_000_000)
    run(now=1_800_000_300)
    fake.alerts = WATCHDOG
    run(now=1_800_000_600)
    fake.alerts = []
    run(now=1_800_000_900)
    run(now=1_800_001_200)
    assert fake.pushes == []


def test_repeats_while_down_no_more_than_every_repeat_seconds(fake, run):
    fake.alerts = []
    t = 1_800_000_000
    for i in range(3 + 12):  # threshold reached at run 3, then an hour of 5-min runs
        run(now=t + i * 300)
    assert len(fake.pushes) == 1
    run(now=t + 2 * 300 + 21600)
    assert len(fake.pushes) == 2


def test_recovery_is_announced_once_after_a_page(fake, run):
    fake.alerts = []
    for i in range(3):
        run(now=1_800_000_000 + i * 300)
    fake.alerts = WATCHDOG
    run(now=1_800_001_200)
    run(now=1_800_001_500)
    assert len(fake.pushes) == 2
    assert "recovered" in fake.pushes[1]["title"].lower()
    assert fake.pushes[1]["priority"] == "0"


def test_no_recovery_message_without_a_prior_page(fake, run):
    fake.alerts = []
    run(now=1_800_000_000)
    fake.alerts = WATCHDOG
    run(now=1_800_000_300)
    assert fake.pushes == []


def test_failed_page_is_retried_next_run(fake, run):
    fake.alerts = []
    fake.push_status = 500
    for i in range(3):
        run(now=1_800_000_000 + i * 300)
    assert len(fake.pushes) == 1  # attempted, failed
    fake.push_status = 200
    run(now=1_800_000_900)
    assert len(fake.pushes) == 2, "a failed Pushover call must not count as notified"


def test_secrets_never_printed(fake, run):
    fake.alerts = []
    out = ""
    for i in range(3):
        r = run(now=1_800_000_000 + i * 300)
        out += r.stdout + r.stderr
    assert "STUB-user" not in out and "STUB-token" not in out
