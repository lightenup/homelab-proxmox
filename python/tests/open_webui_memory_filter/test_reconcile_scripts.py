"""Unit test for the two scripts the hermes role runs inside Open WebUI (spec 097 T042, T043).

- files/open_webui/reconcile_filter.py upserts the `shared_memory` filter row and its valves,
  reading the agent's model ids from the agent API.
- files/open_webui/read_memories.py reads Open WebUI's own memories as ready retain items.

Both run here as subprocesses against a temporary webui.db shaped like Open WebUI 0.11.3's
tables (models/functions.py, models/memories.py, the config key/value table), and a local HTTP
server stands in for the agent's /v1/models.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
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
FILES = ROOT / "ansible" / "roles" / "hermes" / "files" / "open_webui"
AGENT_KEY = "agent-api-key-0001"
MEMORY_KEY = "hmem_test_openwebui_0123456789abcdefghijklmnop"


def _make_db(path: Path) -> None:
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE config (key TEXT PRIMARY KEY, value TEXT, updated_at INTEGER);
        CREATE TABLE "user" (id TEXT PRIMARY KEY, role TEXT, created_at INTEGER);
        CREATE TABLE function (id TEXT PRIMARY KEY, user_id TEXT, name TEXT NOT NULL,
            type TEXT NOT NULL, content TEXT, meta TEXT, valves TEXT, is_active BOOLEAN,
            is_global BOOLEAN, updated_at BIGINT, created_at BIGINT);
        CREATE TABLE memory (id TEXT PRIMARY KEY, user_id TEXT, type TEXT, path TEXT,
            content TEXT, meta TEXT, updated_at BIGINT, created_at BIGINT);
        INSERT INTO "user" VALUES ('pending-user', 'pending', 1), ('admin-1', 'admin', 2);
        """
    )
    con.commit()
    con.close()


@pytest.fixture
def db(tmp_path) -> Path:
    path = tmp_path / "webui.db"
    _make_db(path)
    return path


class _Models(BaseHTTPRequestHandler):
    models: list = ["hermes-agent"]
    seen_auth: list = []

    def do_GET(self):  # noqa: N802 - http.server API
        type(self).seen_auth.append(self.headers.get("Authorization"))
        body = json.dumps({"object": "list", "data": [{"id": m} for m in type(self).models]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture
def agent():
    _Models.models = ["hermes-agent"]
    _Models.seen_auth = []
    server = HTTPServer(("127.0.0.1", 0), _Models)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/v1"
    server.shutdown()


def _run(script: str, db: Path, payload: dict | None = None, **env) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", (FILES / script).read_text()],
        input=json.dumps(payload) if payload is not None else "",
        capture_output=True, text=True, timeout=30,
        env={**os.environ, "HERMES_WEBUI_DB": str(db), **env},
    )


def _payload(models_url: str, content: str = "class Filter:\n    pass\n") -> dict:
    return {
        "id": "shared_memory",
        "name": "Shared memory",
        "description": "Shared memory (097)",
        "content": content,
        "valves": {"url": "https://memory-api.example.test", "key": MEMORY_KEY, "bank": "owner"},
        "models_url": f"{models_url}/models",
        "models_key": AGENT_KEY,
    }


def _function(db: Path) -> dict:
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    row = dict(con.execute("SELECT * FROM function WHERE id='shared_memory'").fetchone())
    con.close()
    return row


# --------------------------------------------------------------------------- reconcile_filter


def test_first_run_inserts_an_active_global_filter(db, agent):
    result = _run("reconcile_filter.py", db, _payload(agent))
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("CHANGED")
    row = _function(db)
    assert row["type"] == "filter"
    assert row["is_active"] == 1 and row["is_global"] == 1
    assert row["user_id"] == "admin-1"
    assert row["content"] == "class Filter:\n    pass\n"
    assert json.loads(row["valves"]) == {
        "url": "https://memory-api.example.test", "key": MEMORY_KEY, "bank": "owner",
        "agent_model_ids": ["hermes-agent"],
    }
    assert json.loads(row["meta"]) == {"description": "Shared memory (097)", "manifest": {}}
    assert _Models.seen_auth == [f"Bearer {AGENT_KEY}"]


def test_second_run_is_unchanged(db, agent):
    _run("reconcile_filter.py", db, _payload(agent))
    result = _run("reconcile_filter.py", db, _payload(agent))
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "UNCHANGED"


def test_a_content_change_is_reported_and_written(db, agent):
    _run("reconcile_filter.py", db, _payload(agent))
    result = _run("reconcile_filter.py", db, _payload(agent, content="class Filter:\n    x = 1\n"))
    assert result.stdout.strip() == "CHANGED content"
    assert _function(db)["content"] == "class Filter:\n    x = 1\n"


def test_reactivates_a_filter_switched_off_and_keeps_app_meta(db, agent):
    """Open WebUI deactivates a function whose module fails to load (utils/plugin.py)."""
    _run("reconcile_filter.py", db, _payload(agent))
    con = sqlite3.connect(db)
    con.execute("UPDATE function SET is_active=0, meta=? WHERE id='shared_memory'",
                (json.dumps({"description": "old", "manifest": {"title": "Shared memory"}}),))
    con.commit()
    con.close()
    result = _run("reconcile_filter.py", db, _payload(agent))
    assert result.stdout.strip() == "CHANGED meta,is_active"
    row = _function(db)
    assert row["is_active"] == 1
    assert json.loads(row["meta"]) == {"description": "Shared memory (097)", "manifest": {"title": "Shared memory"}}


def test_agent_model_ids_follow_the_agent(db, agent):
    _run("reconcile_filter.py", db, _payload(agent))
    _Models.models = ["hermes-agent", "hermes-agent-fast"]
    result = _run("reconcile_filter.py", db, _payload(agent))
    assert result.stdout.strip() == "CHANGED valves"
    assert json.loads(_function(db)["valves"])["agent_model_ids"] == ["hermes-agent", "hermes-agent-fast"]


def test_no_agent_models_fails_and_writes_nothing(db, agent):
    _Models.models = []
    result = _run("reconcile_filter.py", db, _payload(agent))
    assert result.returncode != 0
    assert "listed no models" in result.stderr
    con = sqlite3.connect(db)
    assert con.execute("SELECT count(*) FROM function").fetchone()[0] == 0


def test_unreachable_agent_fails_without_echoing_the_key(db):
    result = _run("reconcile_filter.py", db, _payload("http://127.0.0.1:9"))
    assert result.returncode != 0
    assert "AGENT MODELS" in result.stderr
    assert AGENT_KEY not in result.stderr and MEMORY_KEY not in result.stderr


def test_refuses_encrypted_valves(db, agent):
    result = _run("reconcile_filter.py", db, _payload(agent), ENABLE_VALVE_ENCRYPTION="True")
    assert result.returncode != 0
    assert "VALVE ENCRYPTION" in result.stderr


def test_refuses_a_drifted_schema(tmp_path, agent):
    path = tmp_path / "webui.db"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE function (id TEXT PRIMARY KEY, name TEXT, content TEXT)")
    con.commit()
    con.close()
    result = _run("reconcile_filter.py", path, _payload(agent))
    assert result.returncode != 0
    assert "SCHEMA DRIFT" in result.stderr


# --------------------------------------------------------------------------- read_memories


def _memories(db: Path, *rows: tuple, enabled: object = True) -> None:
    con = sqlite3.connect(db)
    if enabled is not None:
        con.execute("INSERT INTO config VALUES ('memories.enable', ?, 0)", (json.dumps(enabled),))
    con.executemany("INSERT INTO memory (id, user_id, type, content, created_at) VALUES (?, 'admin-1', ?, ?, ?)", rows)
    con.commit()
    con.close()


def test_read_memories_builds_ready_retain_items(db):
    leaked = "hmem_" + "Z" * 30
    _memories(db, ("m2", "user", f"Uses key {leaked}", 1700000100), ("m1", "context", "Has a dog called Tinde", 1700000000),
              ("m3", "context", "   ", 1700000200))
    result = _run("read_memories.py", db)
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["enabled"] is True
    assert [m["document_id"] for m in out["memories"]] == ["owui-memory-m1", "owui-memory-m2"]
    first = out["memories"][0]
    assert first == {
        "content": "Open WebUI saved memory: Has a dog called Tinde",
        "document_id": "owui-memory-m1",
        "context": "memory saved in Open WebUI",
        "tags": ["origin:open-webui-memory", "client:open-webui"],
        "metadata": {"platform": "open-webui", "origin": "open-webui-memory", "memory_type": "context"},
        "timestamp": "2023-11-14T22:13:20+00:00",
    }
    assert out["memories"][1]["content"] == "Open WebUI saved memory: Uses key <redacted>"
    assert out["memories"][1]["metadata"]["memory_type"] == "user"


def test_read_memories_reports_the_switch(db):
    _memories(db, enabled=False)
    assert json.loads(_run("read_memories.py", db).stdout) == {"enabled": False, "memories": []}


def test_read_memories_without_the_config_row_or_table(tmp_path):
    path = tmp_path / "webui.db"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE config (key TEXT PRIMARY KEY, value TEXT, updated_at INTEGER)")
    con.commit()
    con.close()
    assert json.loads(_run("read_memories.py", path).stdout) == {"enabled": None, "memories": []}
