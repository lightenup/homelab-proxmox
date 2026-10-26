"""Guard test: the agent's ntfy slash-command gating and approval policy (spec 095 T010, T021).

Renders `ansible/roles/hermes/templates/agent-config.yaml.j2` offline (StrictUndefined, minimal
stub context) and parses the result as YAML, so the assertions are about the config the agent
actually loads, not about template text.

Key names are verified against the pinned image (nousresearch/hermes-agent v0.21.6):
`gateway/config_loader.py:220` bridges `allow_admin_from` and `user_allowed_commands` from the
root-level platform block into the platform `extra`; `gateway/slash_access.py` enables gating only
when `allow_admin_from` is non-empty and always allows `help` and `whoami`. The ntfy adapter uses
the topic name as the sender id (research R-003), so `allow_admin_from` must never contain an
inbound topic name, or that topic's writer would become an admin with every command.

agent.env's ntfy topic/token selection (T010 parts a-c) lives in test_hermes_env_modes.py (T070).
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined


class _BoolSafeLoader(yaml.SafeLoader):
    """SafeLoader with the YAML 1.1 bool resolver re-pinned. Several test modules strip bool
    resolution from the shared yaml.SafeLoader at import time (same workaround and reason as
    test_log_pipeline.py's _AnsibleYamlLoader); without this, `false` loads as the string
    'false' once those modules are collected first."""


_BoolSafeLoader.add_implicit_resolver(
    "tag:yaml.org,2002:bool",
    re.compile(r"^(?:yes|Yes|YES|no|No|NO|true|True|TRUE|false|False|FALSE|on|On|ON|off|Off|OFF)$"),
    list("yYnNtTfFoO"),
)


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
HERMES_TEMPLATES = ROOT / "ansible" / "roles" / "hermes" / "templates"

# spec FR-014: exactly this set may be run over ntfy by a non-admin.
FR014_COMMANDS = {
    "approve", "deny", "new", "reset", "stop", "status",
    "compress", "retry", "undo", "usage", "title", "model",
}
# The adapter's sender ids (R-003): an inbound topic name in allow_admin_from = full admin.
SENDER_IDS = {"hermes-in", "hermes-lab-in"}


def render_agent_config() -> dict:
    env = Environment(
        loader=FileSystemLoader(str(HERMES_TEMPLATES)),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
    )
    ctx = {
        "hermes_agent_default_model": "hermes-balanced",
        "hermes_gateway_base_url": "http://router.example.invalid:4000/v1",
        "llm_router_aliases": [
            {"name": "hermes-balanced", "deployments": [{"context_window": 131072}]},
        ],
        "hermes_agent_env_passthrough": ["LLM_ROUTER_CLIENT_SCOUT_PROBE_KEY"],
        "hermes_mcp_servers": [
            {"name": "market-model", "url": "http://mm.example.invalid:8001/mcp",
             "auth": "none", "credential_env": None, "enabled": True},
        ],
    }
    return yaml.load(env.get_template("agent-config.yaml.j2").render(**ctx), Loader=_BoolSafeLoader)


def _ntfy_block() -> dict:
    block = render_agent_config().get("ntfy")
    assert isinstance(block, dict), "agent-config must have a root-level ntfy: block (R-014)"
    return block


# --- T010 (d): slash-command gating over ntfy (spec FR-014, research R-002/R-014) ---


def test_gating_is_enabled_with_a_non_sender_admin_placeholder() -> None:
    admins = _ntfy_block().get("allow_admin_from")
    assert admins, "allow_admin_from must be non-empty, or gating is disabled (slash_access.py)"
    assert not (set(admins) & SENDER_IDS), (
        "allow_admin_from must not name an inbound topic: the topic IS the sender id (R-003)"
    )


def test_user_allowed_commands_is_exactly_the_fr014_set() -> None:
    commands = {c.lstrip("/").lower() for c in _ntfy_block().get("user_allowed_commands", [])}
    assert commands == FR014_COMMANDS


def test_bypass_and_update_commands_are_never_allowed() -> None:
    commands = {c.lstrip("/").lower() for c in _ntfy_block().get("user_allowed_commands", [])}
    assert "yolo" not in commands
    assert "update" not in commands


def test_restart_notification_stays_off() -> None:
    """083: a restart must not push to the phone; the gap-notice hook replaces it (R-007)."""
    assert _ntfy_block().get("gateway_restart_notification") is False


# --- T021: approval policy (spec FR-004/FR-005) ---


def test_approval_policy() -> None:
    approvals = render_agent_config()["approvals"]
    assert approvals["mode"] == "manual"
    assert approvals["timeout"] == 900
    assert approvals["cron_mode"] == "deny"
    assert approvals["single_query_mode"] == "deny"
    assert approvals["unattended_mode"] == "deny"
