"""Guard test: the shared memory as an MCP server for the agent and Open WebUI (spec 097 T062).

The `memory` entry in `hermes_mcp_servers` (R-009) is reached through Caddy (`via_proxy`, R-005)
and gives Open WebUI its own key (`webui_vault_var`). Renders the real templates and the real
`set_fact` expressions from `ansible/roles/hermes/tasks/main.yml` with plain Jinja2, Ansible's
`urlsplit` and `lookup('vars', …)` stood in for, and asserts:

- the egress script derives no per-host rule for a `via_proxy` entry (rule 6 covers it);
- the deploy's egress probe tests `reverse_proxy_ip:443` for it, not its URL host;
- the agent sends `Authorization: Bearer ${AUXILIARY_MCP_MEMORY_API_KEY}`;
- Open WebUI's connection carries `memory_client_open_webui_key`, other entries keep `vault_var`;
- the real entry goes through `https://memory-api.`, never the direct port `:8888` (FR-010).
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlsplit

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined


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
GROUP_VARS = ROOT / "ansible" / "group_vars" / "services" / "vars.yml"
PROXY_IP = "192.0.2.11"

SERVERS = [
    {"name": "market-model", "url": "http://198.51.100.5:8001/mcp", "auth": "none",
     "credential_env": None, "enabled": True},
    {"name": "homeassistant", "url": "http://198.51.100.6:8123/api/mcp/assist", "auth": "bearer",
     "credential_env": "AUXILIARY_MCP_HOMEASSISTANT_API_KEY",
     "vault_var": "hermes_mcp_homeassistant_key", "enabled": True},
    {"name": "memory", "url": "https://memory-api.example.invalid/mcp/owner/", "auth": "bearer",
     "credential_env": "AUXILIARY_MCP_MEMORY_API_KEY", "vault_var": "memory_client_hermes_key",
     "webui_vault_var": "memory_client_open_webui_key", "via_proxy": True, "enabled": True},
]
VAULT = {name: f"STUB__{name}__" for name in (
    "hermes_mcp_homeassistant_key", "memory_client_hermes_key", "memory_client_open_webui_key")}


class _BoolSafeLoader(yaml.SafeLoader):
    """SafeLoader with the YAML 1.1 bool resolver re-pinned: other test modules strip it from
    yaml.SafeLoader at import time (see test_hermes_ntfy_config.py)."""


_BoolSafeLoader.add_implicit_resolver(
    "tag:yaml.org,2002:bool",
    re.compile(r"^(?:yes|Yes|YES|no|No|NO|true|True|TRUE|false|False|FALSE|on|On|ON|off|Off|OFF)$"),
    list("yYnNtTfFoO"),
)


def _urlsplit(url: str, part: str):
    return getattr(urlsplit(url), part)


def _lookup(kind: str, name: str, default=None):
    assert kind == "vars"
    return VAULT[name]


def _env() -> Environment:
    env = Environment(loader=FileSystemLoader(str(HERMES_ROLE / "templates")),
                      undefined=StrictUndefined, keep_trailing_newline=True)
    env.filters["urlsplit"] = _urlsplit
    env.filters["bool"] = bool
    env.filters["regex_replace"] = lambda value, pattern, repl: re.sub(pattern, repl, value)
    env.globals["lookup"] = _lookup
    return env


def _task(name: str) -> dict:
    tasks = yaml.load((HERMES_ROLE / "tasks" / "main.yml").read_text(), Loader=_BoolSafeLoader)
    matches = [t for t in tasks if t.get("name") == name]
    assert len(matches) == 1, name
    return matches[0]["ansible.builtin.set_fact"]


def _set_fact(expression: str, **ctx):
    """Render a `>-` set_fact value the way Ansible does, then read the literal it produces."""
    return yaml.safe_load(_env().from_string(expression).render(**ctx))


# --- egress script and probe ---


def test_egress_script_derives_no_rule_for_a_via_proxy_entry() -> None:
    rendered = _env().get_template("hermes-agent-egress.sh.j2").render(
        hermes_agent_ip="172.30.0.10", hermes_agent_subnet="172.30.0.0/24",
        llm_router_ip="198.51.100.20", llm_router_port=4000, reverse_proxy_ip=PROXY_IP,
        hermes_mcp_servers=SERVERS)
    destinations = re.search(r"^MCP_DESTINATIONS=\((.*?)^\)", rendered, re.S | re.M).group(1)
    assert re.findall(r'"([^"]+)"', destinations) == ["198.51.100.5 8001", "198.51.100.6 8123"]
    assert "memory-api" not in rendered
    assert f'PROXY_IP="{PROXY_IP}"' in rendered


def test_egress_probe_tests_the_reverse_proxy_for_a_via_proxy_entry() -> None:
    fact = _task("Build the egress probe destination list")["hermes_agent_egress_probe_allowed"]
    dests = {d["name"]: (d["host"], d["port"]) for d in _set_fact(
        fact, hermes_mcp_servers=SERVERS, llm_router_ip="198.51.100.20", llm_router_port=4000,
        reverse_proxy_ip=PROXY_IP)}
    assert dests["mcp-memory"] == (PROXY_IP, 443)
    assert dests["mcp-homeassistant"] == ("198.51.100.6", 8123)


# --- agent and Open WebUI credentials ---


def test_agent_sends_the_memory_key_from_its_scrubbed_env_name() -> None:
    ctx = {
        "hermes_agent_default_model": "hermes-balanced",
        "hermes_gateway_base_url": "http://router.example.invalid:4000/v1",
        "llm_router_aliases": [{"name": "hermes-balanced", "deployments": [{"context_window": 131072}]}],
        "hermes_agent_env_passthrough": [],
        "hermes_mcp_servers": SERVERS,
    }
    rendered = _env().get_template("agent-config.yaml.j2").render(**ctx)
    memory = yaml.load(rendered, Loader=_BoolSafeLoader)["mcp_servers"]["memory"]
    assert memory["url"] == "https://memory-api.example.invalid/mcp/owner/"
    assert memory["headers"] == {"Authorization": "Bearer ${AUXILIARY_MCP_MEMORY_API_KEY}"}
    assert not any(v.startswith("STUB__") for v in memory["headers"].values())


def test_open_webui_connection_uses_its_own_memory_key() -> None:
    fact = _task("Build the MCP tool-server connection list")["hermes_tool_server_connections"]
    connections = []
    for item in SERVERS:
        connections = _set_fact(fact, item=item, hermes_tool_server_connections=connections)
    keys = {c["info"]["name"]: c["key"] for c in connections}
    assert keys == {
        "market-model": "",
        "homeassistant": VAULT["hermes_mcp_homeassistant_key"],
        "memory": VAULT["memory_client_open_webui_key"],
    }


# --- the real entry (FR-010, R-009) ---


def test_real_memory_entry_goes_through_caddy_to_the_owner_bank() -> None:
    servers = yaml.load(GROUP_VARS.read_text(), Loader=_BoolSafeLoader)["hermes_mcp_servers"]
    entries = [s for s in servers if s["name"] == "memory"]
    assert len(entries) == 1
    entry = entries[0]
    assert entry["url"].startswith("https://memory-api.")
    assert ":8888" not in entry["url"]
    assert entry["url"].endswith("/mcp/owner/"), "the bank is bound by the path (R-009)"
    assert entry["via_proxy"] is True
    assert entry["enabled"] is True
    assert entry["auth"] == "bearer"
    assert entry["credential_env"] == "AUXILIARY_MCP_MEMORY_API_KEY"
    assert entry["vault_var"] == "memory_client_hermes_key"
    assert entry["webui_vault_var"] == "memory_client_open_webui_key"
