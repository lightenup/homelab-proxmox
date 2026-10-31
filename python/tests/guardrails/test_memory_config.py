"""Guard test: the memory server's rendered configuration (spec 097 T006, T007).

Renders ansible/roles/memory/templates/{server.env,clients.json,docker-compose.yml}.j2 offline
with the real group vars and role defaults, and placeholder secrets that start `hmem_test`.
Assertions are about the files the server actually loads:

- server.env holds research R-004's table exactly, no LLM provider and no cloud default
  (FR-003, FR-004), and the six MCP tools of FR-009;
- clients.json holds hashes only, valid for memory_access.load_clients (R-001);
- the API binds memory_ip only (FR-010);
- the shim and the policy match the pinned Hindsight release (T007, R-001, R-018).
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import pytest
import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateAssertionError, UndefinedError

from homelab_proxmox_orchestrator import memory_access


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
ROLE = ROOT / "ansible" / "roles" / "memory"
SERVICES_VARS = ROOT / "ansible" / "group_vars" / "services" / "vars.yml"
SHIM = ROLE / "files" / "hindsight_ext" / "shim.py"

SECRETS = {
    "memory_db_password": "hmemtestdbpassword0123456789",
    "llm_router_client_memory_key": "sk-hmem_test_gateway_memory_key",
    "memory_client_hermes_key": "hmem_test_hermes_0123456789abcdefghijklmnopqrstuvwxyz",
    "memory_client_open_webui_key": "hmem_test_open_webui_0123456789abcdefghijklmnopqrstuv",
    "memory_client_claude_code_key": "hmem_test_claude_code_0123456789abcdefghijklmnopqrstu",
    "memory_client_control_plane_key": "hmem_test_control_plane_0123456789abcdefghijklmnopqrs",
    "memory_admin_key": "hmem_test_admin_0123456789abcdefghijklmnopqrstuvwxyz0",
    "memory_ui_access_key": "hmem_test_ui_access_0123456789abcdefghijklmnopqrstuvw",
}

# Research R-004's decision table, exactly.
R004 = {
    "HINDSIGHT_API_RETAIN_EXTRACTION_MODE": "chunks",
    "HINDSIGHT_API_ENABLE_OBSERVATIONS": "false",
    "HINDSIGHT_API_ENABLE_AUTO_CONSOLIDATION": "false",
    "HINDSIGHT_API_LLM_PROVIDER": "none",
    "HINDSIGHT_API_EMBEDDINGS_PROVIDER": "openai",
    "HINDSIGHT_API_EMBEDDINGS_OPENAI_BASE_URL": "http://192.168.1.220:4000/v1",
    "HINDSIGHT_API_EMBEDDINGS_OPENAI_MODEL": "hermes-embed",
    "HINDSIGHT_API_EMBEDDINGS_OPENAI_DIMENSIONS": "1024",
    "HINDSIGHT_API_RERANKER_PROVIDER": "litellm",
    "HINDSIGHT_API_RERANKER_LITELLM_API_BASE": "http://192.168.1.220:4000",
    "HINDSIGHT_API_RERANKER_LITELLM_MODEL": "hermes-rerank",
    "HINDSIGHT_API_MCP_ENABLED_TOOLS": "recall,retain,list_memories,update_memory,invalidate_memory,list_tags",
    "HINDSIGHT_API_METRICS_BACKLOG_ENABLED": "true",
    "HINDSIGHT_ENABLE_CP": "false",
    "HF_HUB_OFFLINE": "1",
    "TRANSFORMERS_OFFLINE": "1",
    "HINDSIGHT_API_TENANT_EXTENSION": "shim:ClientKeyTenantExtension",
    "HINDSIGHT_API_OPERATION_VALIDATOR_EXTENSION": "shim:ClientScopeValidator",
}
CLOUD_DEFAULTS = ("openai.com", "openrouter", "huggingface", "anthropic")


# --------------------------------------------------------------------------- rendering


def _resolve(value: Any, ctx: dict[str, Any], env: Environment) -> Any:
    if isinstance(value, str) and "{{" in value:
        try:
            return env.from_string(value).render(**ctx)
        except (UndefinedError, TemplateAssertionError):
            return value  # refers to a variable outside the services group; unused here
    if isinstance(value, list):
        return [_resolve(v, ctx, env) for v in value]
    if isinstance(value, dict):
        return {k: _resolve(v, ctx, env) for k, v in value.items()}
    return value


def _context(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    ctx: dict[str, Any] = {}
    ctx.update(yaml.safe_load(SERVICES_VARS.read_text()))
    ctx.update(yaml.safe_load((ROLE / "defaults" / "main.yml").read_text()))
    ctx.update(SECRETS)
    ctx.update(overrides or {})
    env = _env()
    # Ansible resolves variables lazily; a few passes reach the same fixed point here.
    for _ in range(5):
        ctx = {k: _resolve(v, ctx, env) for k, v in ctx.items()}
    return ctx


def _env(ctx: dict[str, Any] | None = None) -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(ROLE / "templates")),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
    )
    env.filters["hash"] = lambda s, algo: hashlib.new(algo, str(s).encode()).hexdigest()
    env.filters["to_nice_json"] = lambda v: json.dumps(v, indent=4, sort_keys=True)

    def lookup(kind: str, name: str, default: Any = None) -> Any:
        assert kind in ("vars", "ansible.builtin.vars"), kind
        return (ctx or {})[name]

    env.globals["lookup"] = lookup
    return env


def render(template: str, overrides: dict[str, Any] | None = None) -> str:
    ctx = _context(overrides)
    return _env(ctx).get_template(template).render(**ctx)


def _env_file(text: str) -> dict[str, str]:
    pairs = {}
    for line in text.splitlines():
        if line and not line.startswith("#"):
            key, _, value = line.partition("=")
            assert key not in pairs, f"duplicate {key}"
            pairs[key] = value
    return pairs


@pytest.fixture(scope="module")
def server_env() -> dict[str, str]:
    return _env_file(render("server.env.j2"))


# --------------------------------------------------------------------------- server.env (T006)


def test_server_env_holds_research_r004_exactly(server_env):
    assert {k: server_env.get(k) for k in R004} == R004


def test_server_env_has_no_other_settings(server_env):
    extra = set(server_env) - set(R004)
    assert extra == {
        "HINDSIGHT_API_DATABASE_URL",
        "HINDSIGHT_API_EMBEDDINGS_OPENAI_API_KEY",
        "HINDSIGHT_API_RERANKER_LITELLM_API_KEY",
        "HINDSIGHT_API_TENANT_CLIENTS_FILE",
        "HINDSIGHT_API_OPERATION_VALIDATOR_CLIENTS_FILE",
        "PYTHONPATH",
    }


def test_no_llm_endpoint_is_configured(server_env):
    assert server_env["HINDSIGHT_API_LLM_PROVIDER"] == "none"
    llm = [k for k in server_env if k.startswith("HINDSIGHT_API_LLM_") and k != "HINDSIGHT_API_LLM_PROVIDER"]
    assert llm == []


def test_no_rendered_value_names_a_cloud_default(server_env):
    for key, value in server_env.items():
        for cloud in CLOUD_DEFAULTS:
            assert cloud not in value.lower(), (key, cloud)


def test_gateway_and_database_settings(server_env):
    assert server_env["HINDSIGHT_API_DATABASE_URL"] == (
        f"postgresql://hindsight:{SECRETS['memory_db_password']}@memory_postgres:5432/hindsight"
    )
    key = SECRETS["llm_router_client_memory_key"]
    assert server_env["HINDSIGHT_API_EMBEDDINGS_OPENAI_API_KEY"] == key
    assert server_env["HINDSIGHT_API_RERANKER_LITELLM_API_KEY"] == key


def test_both_extensions_read_the_mounted_client_file(server_env):
    compose = yaml.safe_load(render("docker-compose.yml.j2"))
    mounts = compose["services"]["memory_api"]["volumes"]
    assert "/opt/memory/clients.json:/run/memory/clients.json:ro" in mounts
    assert server_env["HINDSIGHT_API_TENANT_CLIENTS_FILE"] == "/run/memory/clients.json"
    assert server_env["HINDSIGHT_API_OPERATION_VALIDATOR_CLIENTS_FILE"] == "/run/memory/clients.json"
    assert server_env["PYTHONPATH"] == "/opt/memory-ext"
    assert "/opt/memory-ext:/opt/memory-ext:ro" in mounts


def test_lab_server_env_points_at_the_lab_gateway():
    env = _env_file(render("server.env.j2", {"llm_router_ip": "10.99.0.220"}))
    assert env["HINDSIGHT_API_EMBEDDINGS_OPENAI_BASE_URL"] == "http://10.99.0.220:4000/v1"


def test_db_env_matches_the_database_url():
    env = _env_file(render("db.env.j2"))
    assert env == {
        "POSTGRES_USER": "hindsight",
        "POSTGRES_DB": "hindsight",
        "POSTGRES_PASSWORD": SECRETS["memory_db_password"],
    }


# --------------------------------------------------------------------------- clients.json (T006)


def test_clients_json_holds_hashes_only():
    text = render("clients.json.j2")
    assert "hmem_" not in text
    entries = json.loads(text)
    assert [e["id"] for e in entries] == ["hermes", "open-webui", "claude-code", "control-plane", "backup"]
    for entry in entries:
        assert set(entry) == {"id", "sha256", "scope"}
        assert re.fullmatch(r"[0-9a-f]{64}", entry["sha256"])
    by_id = {e["id"]: e for e in entries}
    assert by_id["hermes"]["sha256"] == hashlib.sha256(SECRETS["memory_client_hermes_key"].encode()).hexdigest()
    assert by_id["backup"]["scope"] == "admin"
    assert by_id["control-plane"]["scope"] == "curator"


def test_clients_json_loads_in_the_policy():
    clients = memory_access.load_clients(render("clients.json.j2"))
    assert memory_access.authenticate(SECRETS["memory_client_open_webui_key"], clients).id == "open-webui"


@pytest.mark.parametrize("scope", ["readwrite", "readonly"])
def test_claude_code_scope_is_switchable(scope):
    entries = json.loads(render("clients.json.j2", {"memory_claude_code_scope": scope}))
    assert {e["id"]: e["scope"] for e in entries}["claude-code"] == scope


def test_revoked_claude_code_is_left_out():
    entries = json.loads(render("clients.json.j2", {"memory_claude_code_scope": "revoked"}))
    assert "claude-code" not in [e["id"] for e in entries]
    memory_access.load_clients(json.dumps(entries))


# --------------------------------------------------------------------------- compose (T006)


def test_only_the_api_publishes_a_port_and_only_on_memory_ip():
    compose = yaml.safe_load(render("docker-compose.yml.j2"))
    services = compose["services"]
    assert services["memory_api"]["ports"] == ["192.168.1.223:8888:8888"]
    assert "ports" not in services["memory_postgres"]
    for name, svc in services.items():
        for port in svc.get("ports", []):
            assert port.startswith("192.168.1.223:"), (name, port)


def test_images_are_the_pinned_stock_images():
    ctx = _context()
    compose = yaml.safe_load(render("docker-compose.yml.j2"))
    services = compose["services"]
    assert services["memory_api"]["image"] == f"ghcr.io/vectorize-io/hindsight:{ctx['hindsight_version']}-slim"
    assert services["memory_postgres"]["image"] == f"pgvector/pgvector:{ctx['memory_postgres_version']}"


def test_shim_is_verified_against_the_pinned_hindsight_version():
    match = re.search(r'^HINDSIGHT_VERIFIED_VERSION = "([^"]+)"$', SHIM.read_text(), re.M)
    assert match, "shim.py must declare HINDSIGHT_VERIFIED_VERSION"
    assert match.group(1) == _context()["hindsight_version"], (
        "hindsight_version moved: re-read the shim's base classes at the new tag, regenerate "
        "operations-<version>.txt, bump HINDSIGHT_VERIFIED_VERSION and re-run the harness (FR-021)"
    )


# --------------------------------------------------------------------------- allowlist guard (T007)


def _snapshot() -> set[str]:
    version = _context()["hindsight_version"]
    path = ROLE / "files" / "hindsight_ext" / f"operations-{version}.txt"
    assert path.is_file(), f"no operation snapshot for hindsight_version {version}: {path}"
    return {line.strip() for line in path.read_text().splitlines() if line.strip() and not line.startswith("#")}


def _policy_names() -> set[str]:
    return set().union(*memory_access.SCOPE_ALLOWLISTS.values()) | memory_access.REFUSED_FOR_ALL


def _shim_operation_names() -> set[str]:
    """String literals the shim passes as operation names to _result()."""
    names = set()
    for node in ast.walk(ast.parse(SHIM.read_text())):
        if isinstance(node, ast.Call) and getattr(node.func, "attr", None) == "_result":
            arg = node.args[1]
            if isinstance(arg, ast.Constant):
                names.add(arg.value)
    return names


def test_every_policy_name_exists_in_the_pinned_hindsight():
    assert _policy_names() - _snapshot() == set()


def test_every_hindsight_operation_is_classified():
    unclassified = _snapshot() - _policy_names()
    assert unclassified == set(), (
        "Hindsight operations neither allowed to a scope nor refused for all: classify them in "
        f"memory_access.py (research R-001): {sorted(unclassified)}"
    )


def test_every_shim_hook_name_exists_in_the_pinned_hindsight():
    names = _shim_operation_names()
    assert "recall" in names and "import" in names
    assert names - _snapshot() == set()


# --------------------------------------------------------------------------- deploy probe (R-019)


def test_deploy_probe_token_is_drawn_once():
    """A lookup re-evaluates at every reference: built in one templating pass, the probe's
    document id, text and token each got a different random value, and the recall check
    failed on every deploy (PR #318 review). The token must be stored by a set_fact of its own
    and only referenced afterwards."""
    tasks = yaml.safe_load((ROLE / "tasks" / "bank.yml").read_text())
    probe = next(t for t in tasks if t.get("name") == "Run the deploy probe")
    assert "vars" not in probe, "no lookup in block vars: it would be re-evaluated per reference"
    draw, build = probe["block"][0], probe["block"][1]
    assert list(draw["ansible.builtin.set_fact"]) == ["memory_probe_token"]
    assert "lookup(" in draw["ansible.builtin.set_fact"]["memory_probe_token"]
    fields = build["ansible.builtin.set_fact"]["memory_probe"]
    assert all("{{ memory_probe_token }}" in v and "lookup(" not in v for v in fields.values())


def test_probe_and_backup_read_fresh_stats():
    """Bank stats are cached for 60 s; a before/after comparison must bypass the cache."""
    bank = (ROLE / "tasks" / "bank.yml").read_text()
    assert bank.count("/stats?refresh=true") == 2 and "/stats\"" not in bank
    snapshot = (ROOT / "ansible/roles/service_backup/templates/snapshot/memory.sh.j2").read_text()
    assert "/stats?refresh=true" in snapshot


# --------------------------------------------------------------------------- web UI (T063, R-020)


def test_ui_env_holds_exactly_the_login_key_and_the_curator_key():
    env = _env_file(render("ui.env.j2"))
    assert env == {
        "HINDSIGHT_CP_ACCESS_KEY": SECRETS["memory_ui_access_key"],
        "HINDSIGHT_CP_DATAPLANE_API_KEY": SECRETS["memory_client_control_plane_key"],
    }


def test_ui_service_is_bounded_and_bound_to_memory_ip():
    ui = yaml.safe_load(render("docker-compose.yml.j2"))["services"]["memory_ui"]
    assert ui["image"] == f"ghcr.io/vectorize-io/hindsight-control-plane:{_context()['hindsight_version']}"
    assert ui["env_file"] == "ui.env"
    assert ui["environment"] == {"HINDSIGHT_CP_DATAPLANE_API_URL": "http://memory_api:8888"}
    assert ui["ports"] == ["192.168.1.223:9999:9999"]
    assert ui["mem_limit"] == "384m"
    assert ui["depends_on"] == {"memory_api": {"condition": "service_healthy"}}


def test_ui_never_holds_the_admin_gateway_or_database_secrets():
    rendered = render("ui.env.j2") + yaml.safe_dump(yaml.safe_load(render("docker-compose.yml.j2"))["services"]["memory_ui"])
    for name in ("memory_admin_key", "llm_router_client_memory_key", "memory_db_password"):
        assert SECRETS[name] not in rendered, name


def test_portal_tile_publishes_the_ui_only():
    services = {s["host"]: s for s in _context()["caddy_services"]}
    ui = services["memory"]
    # str(): other test modules strip YAML's bool resolver at import (see test_hermes_ntfy_config).
    assert str(ui["user_facing"]).lower() == "true" and ui["port"] == "9999" and ui["ip"] == "192.168.1.223"
    assert str(services["memory-api"]["user_facing"]).lower() == "false"


# --------------------------------------------------------------------------- restore drill (T057)

RESTORE_TEMPLATES = ROOT / "ansible" / "roles" / "service_backup" / "templates" / "restore"
DRILL = ROOT / "ansible" / "playbooks" / "memory-restore-drill.yml"


def _restore_compose() -> dict[str, Any]:
    ctx = _context()
    env = Environment(loader=FileSystemLoader(str(RESTORE_TEMPLATES)), undefined=StrictUndefined)
    return yaml.safe_load(env.get_template("memory-compose.yml.j2").render(**ctx))


def test_restore_compose_runs_the_live_images_on_their_own_network():
    restore = _restore_compose()
    live = yaml.safe_load(render("docker-compose.yml.j2"))["services"]
    services = restore["services"]
    assert set(services) == {"memory_postgres_restore", "memory_api_restore"}
    for name, svc in services.items():
        assert svc["container_name"] == name
        assert str(svc["restart"]).lower() == "no"
        assert svc["networks"] == ["memory_restore"]
    assert services["memory_postgres_restore"]["image"] == live["memory_postgres"]["image"]
    assert services["memory_api_restore"]["image"] == live["memory_api"]["image"]
    network = restore["networks"]["memory_restore"]
    assert network["name"] == "memory-restore-drill"


def test_restore_compose_publishes_the_api_on_localhost_8889_only():
    services = _restore_compose()["services"]
    assert services["memory_api_restore"]["ports"] == ["127.0.0.1:8889:8888"]
    assert "ports" not in services["memory_postgres_restore"]


def test_restore_compose_shares_the_live_mounts_but_not_the_live_data():
    services = _restore_compose()["services"]
    live = yaml.safe_load(render("docker-compose.yml.j2"))["services"]
    api, db = services["memory_api_restore"], services["memory_postgres_restore"]
    assert api["volumes"] == live["memory_api"]["volumes"]
    assert api["env_file"] == "server.env" and db["env_file"] == "db.env"
    assert db["volumes"] == ["memory-postgres-restore:/var/lib/postgresql/data"]
    assert "memory-postgres-restore" in _restore_compose()["volumes"]
    rendered = yaml.safe_dump(services)
    assert _context()["memory_data_dir"] not in rendered
    for secret in SECRETS.values():
        assert secret not in rendered


def test_drill_server_env_points_at_the_restore_database():
    """The drill renders the role's server.env and rewrites the database host with the
    playbook's own regex_replace; the result must name memory_postgres_restore only."""
    match = re.search(r"regex_replace\('(@memory_postgres:[^']+)', '([^']+)'\)", DRILL.read_text())
    assert match, "the drill rewrites server.env with regex_replace"
    env = _env_file(re.sub(match.group(1), match.group(2), render("server.env.j2")))
    url = env["HINDSIGHT_API_DATABASE_URL"]
    assert url == f"postgresql://hindsight:{SECRETS['memory_db_password']}@memory_postgres_restore:5432/hindsight"
    assert {k: v for k, v in env.items() if k != "HINDSIGHT_API_DATABASE_URL"} == {
        k: v for k, v in _env_file(render("server.env.j2")).items() if k != "HINDSIGHT_API_DATABASE_URL"
    }


def test_preflight_refuses_a_ui_without_its_login_key():
    preflight = (ROLE / "tasks" / "preflight.yml").read_text()
    assert "memory_ui_access_key" in preflight and "serves the UI open" in preflight
