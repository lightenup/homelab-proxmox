"""Guard test: the agent's Hindsight memory provider (spec 097 T028; research R-003).

Renders the hermes role's agent-config.yaml.j2, hindsight-config.json.j2, docker-compose.yml.j2
and agent.env.j2 offline and asserts the shape the agent actually loads:

- the provider is set in the read-only config (FR-001, FR-008);
- the plugin config is research R-003's table exactly, and its URL goes through Caddy over TLS,
  never to the direct port :8888 (FR-010, G1);
- the plugin, its packages and its config are mounted read-only (FR-002);
- the memory key lives only in the plugin config, never in agent.env, so it is not an
  environment variable of the agent's children.

The per-mode secret freeze for hindsight-config.json is in test_hermes_env_modes.py.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined, Undefined

from test_hermes_env_modes import render_prod as render_agent_env
from test_hermes_ntfy_config import render_agent_config


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
HERMES_ROLE = ROOT / "ansible" / "roles" / "hermes"
HERMES_KEY = "hmem_test_hermes_0123456789abcdefghijklmnopqrstuvwxyz"

# Research R-003's plugin config table, exactly.
R003 = {
    "mode": "local_external",
    "api_url": "https://memory-api.hus-sky.no",
    "api_key": HERMES_KEY,
    "bank_id": "owner",
    "memory_mode": "context",
    "auto_recall": True,
    "auto_retain": True,
    "recall_sync": True,
    "recall_types": ["world"],
    "recall_budget": "mid",
    "retain_every_n_turns": 1,
    "retain_async": True,
    "retain_tags": ["client:hermes"],
    "retain_user_prefix": "User",
    "retain_assistant_prefix": "Assistant",
    "timeout": 10,
}


def _defaults() -> dict:
    return yaml.safe_load((HERMES_ROLE / "defaults" / "main.yml").read_text())


def render_plugin_config(memory_key: str = HERMES_KEY) -> dict:
    env = Environment(loader=FileSystemLoader(str(HERMES_ROLE / "templates")), undefined=StrictUndefined)
    defaults = _defaults()
    ctx = {
        "caddy_base_domain": "hus-sky.no",
        "memory_client_hermes_key": memory_key,
        "hermes_memory_bank_id": defaults["hermes_memory_bank_id"],
    }
    ctx["hermes_memory_api_url"] = env.from_string(defaults["hermes_memory_api_url"]).render(**ctx)
    return json.loads(env.get_template("hindsight-config.json.j2").render(**ctx))


class _Stub(Undefined):
    """Renders an unset variable as a visible placeholder, so the compose file parses as YAML
    without mirroring every role variable here."""

    def __str__(self) -> str:
        return f"STUB_{self._undefined_name}"


def render_compose() -> dict:
    env = Environment(loader=FileSystemLoader(str(HERMES_ROLE / "templates")), undefined=_Stub)
    env.filters["to_json"] = lambda v: json.dumps(v)
    env.filters["lower"] = lambda v: str(v).lower()
    defaults = _defaults()
    ctx = {
        "hermes_agent_operational": True,
        "hermes_install_dir": "/opt/hermes",
        "hermes_agent_plugins_dir": defaults["hermes_agent_plugins_dir"],
        "hermes_agent_tool_servers": [],
    }
    for name in ("hermes_memory_plugin_dir", "hermes_memory_deps_dir", "hermes_memory_plugin_config_path"):
        ctx[name] = env.from_string(defaults[name]).render(**ctx)
    return yaml.safe_load(env.get_template("docker-compose.yml.j2").render(**ctx))


def _agent_volumes() -> list[str]:
    return [str(v) for v in render_compose()["services"]["hermes-agent"]["volumes"]]


# --------------------------------------------------------------------------- agent config


def test_hindsight_is_the_memory_provider_beside_built_in_memory():
    memory = render_agent_config()["memory"]
    assert memory["memory_enabled"] is True
    assert memory["provider"] == "hindsight"


def test_provider_is_not_enabled_as_a_plugin():
    """The memory provider is selected under memory:, not plugins.enabled (R-018)."""
    enabled = render_agent_config().get("plugins", {}).get("enabled", [])
    assert "hindsight" not in enabled


# --------------------------------------------------------------------------- plugin config


def test_plugin_config_is_research_r003_exactly():
    assert render_plugin_config() == R003


def test_plugin_goes_through_caddy_never_the_direct_port():
    url = render_plugin_config()["api_url"]
    assert url.startswith("https://memory-api.")
    assert ":8888" not in url


def test_bank_matches_the_memory_role():
    memory_defaults = yaml.safe_load((ROOT / "ansible/roles/memory/defaults/main.yml").read_text())
    assert render_plugin_config()["bank_id"] == memory_defaults["memory_bank_id"]


# --------------------------------------------------------------------------- compose


def test_plugin_deps_and_config_are_mounted_read_only():
    volumes = _agent_volumes()
    expected = [
        "/opt/hermes-agent-plugins/memory/hindsight:/opt/data/plugins/hindsight:ro",
        "/opt/hermes-agent-plugins/memory-deps:/opt/hermes-memory-deps:ro",
        "/opt/hermes/hindsight-config.json:/opt/data/hindsight/config.json:ro",
    ]
    for mount in expected:
        assert mount in volumes, mount
    for mount in volumes:
        if ":/opt/data/plugins" in mount or ":/opt/data/hindsight" in mount or "memory-deps" in mount:
            assert mount.endswith(":ro"), mount


def test_agent_imports_the_plugin_packages_from_the_read_only_dir():
    env = render_compose()["services"]["hermes-agent"]["environment"]
    assert env == {"PYTHONPATH": "/opt/hermes-memory-deps"}


def test_compose_confinement_assert_covers_the_new_mounts():
    tasks = (HERMES_ROLE / "tasks" / "main.yml").read_text()
    assert "select('search', ':/opt/data/hindsight') | reject('search', ':ro$')" in tasks
    assert "select('search', ':/opt/hermes-memory-deps') | reject('search', ':ro$')" in tasks


# --------------------------------------------------------------------------- key placement


def test_memory_key_is_never_in_agent_env():
    rendered = render_agent_env()
    assert "hmem_" not in rendered
    assert "memory_client_hermes_key" not in (HERMES_ROLE / "templates" / "agent.env.j2").read_text()


def test_plugin_config_is_root_owned_and_not_logged():
    tasks = yaml.safe_load((HERMES_ROLE / "tasks" / "main.yml").read_text())
    task = next(t for t in tasks if t.get("name") == "Deploy the memory plugin configuration (read-only mount source)")
    module = task["ansible.builtin.template"]
    assert module["src"] == "hindsight-config.json.j2"
    assert module["owner"] == "root"
    # str(): other test modules strip YAML's bool resolver at import (see test_hermes_ntfy_config).
    assert str(task["no_log"]).lower() == "true"
