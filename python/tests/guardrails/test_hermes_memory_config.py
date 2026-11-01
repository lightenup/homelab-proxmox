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

import ast
import json
import re
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
    "recall_max_tokens": 2000,
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
    ctx["hermes_agent_site_packages"] = defaults["hermes_agent_site_packages"]
    for name in ("hermes_memory_plugin_dir", "hermes_memory_deps_dir", "hermes_memory_plugin_config_path", "hermes_memory_pth_path",
                 "hermes_agent_soul_path"):
        ctx[name] = env.from_string(defaults[name]).render(**ctx)
    return yaml.safe_load(env.get_template("docker-compose.yml.j2").render(**ctx))


def _agent_volumes() -> list[str]:
    return [str(v) for v in render_compose()["services"]["hermes-agent"]["volumes"]]


# --------------------------------------------------------------------------- agent config


def test_built_in_notes_are_off_and_the_owner_profile_stays():
    """097 § 8 (2026-11-01): with the built-in notes on, corrections and forgets went to the built-in
    files and the shared copy outlived them. The profile stays: without it, standing preferences
    left open-ended answers (harness p15). USER.md has its own switch."""
    memory = render_agent_config()["memory"]
    assert memory["memory_enabled"] is False
    assert memory["user_profile_enabled"] is True
    assert memory["provider"] == "hindsight"


def test_soul_keeps_upstream_identity_and_routes_corrections_to_the_memory_tools():
    soul = Environment(loader=FileSystemLoader(str(HERMES_ROLE / "templates")),
                       undefined=StrictUndefined).get_template("SOUL.md.j2").render()
    assert soul.startswith("You are Hermes Agent, built by Nous Research.")
    for tool in ("update_memory", "invalidate_memory", "list_memories"):
        assert f"`{tool}`" in soul
    assert "user profile holds the same thing, change it there too" in " ".join(soul.split())
    # Only on an explicit request: on ordinary new facts the local model looped on the tools.
    assert "only when the owner explicitly asks you to correct or forget" in " ".join(soul.split())
    assert "never say something is forgotten unless those calls succeeded" in " ".join(soul.split())


def test_recall_fits_under_the_hook_spill_limit():
    """2026-11-01: an uncapped recall (~13,000 characters) was spilled to a file and the model saw
    only its head and tail. 2,000 tokens at up to 8 characters each stays under the limit."""
    limit = render_agent_config()["hooks"]["output_spill"]["max_chars"]
    assert render_plugin_config()["recall_max_tokens"] * 8 <= limit
    harness = yaml.safe_load((ROOT / "docs/backlog/097-spike/runs/prod-render/config.yaml").read_text())
    assert harness["hooks"]["output_spill"]["max_chars"] == limit


def test_tool_loops_hard_stop_in_production_and_the_harness():
    assert render_agent_config()["tool_loop_guardrails"] == {"hard_stop_enabled": True}
    harness = yaml.safe_load((ROOT / "docs/backlog/097-spike/runs/prod-render/config.yaml").read_text())
    assert str(harness["tool_loop_guardrails"]["hard_stop_enabled"]).lower() == "true"


def test_soul_is_deploy_owned_and_mounted_read_only():
    assert "/opt/hermes/SOUL.md:/opt/data/SOUL.md:ro" in _agent_volumes()
    task = _task("Deploy the agent identity file (read-only mount source)")["ansible.builtin.template"]
    assert (task["src"], task["dest"], task["owner"]) == ("SOUL.md.j2", "{{ hermes_agent_soul_path }}", "root")
    tasks = (HERMES_ROLE / "tasks" / "main.yml").read_text()
    check = next(line.strip()[2:] for line in tasks.splitlines() if "(config[.]yaml|SOUL[.]md)" in line)
    env = Environment()
    env.tests["search"] = lambda value, pattern: re.search(pattern, value) is not None
    env.filters["from_yaml"] = yaml.safe_load
    def confined(volumes):
        compose = yaml.safe_dump({"services": {"hermes-agent": {"volumes": volumes}}})
        return env.from_string("{{ " + check + " }}").render(hermes_compose=compose) == "True"
    assert confined(["/opt/hermes/SOUL.md:/opt/data/SOUL.md:ro", "/opt/hermes/agent-config.yaml:/opt/data/config.yaml:ro"])
    # PR #340 review: an options suffix must not hide a writable mount.
    for bad in ("/opt/hermes/SOUL.md:/opt/data/SOUL.md", "/opt/hermes/SOUL.md:/opt/data/SOUL.md:rw",
                "/x/agent-config.yaml:/opt/data/config.yaml:rw,z"):
        assert not confined([bad]), bad


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
        "/opt/hermes-agent-plugins/memory/hermes-memory-deps.pth:"
        "/opt/hermes/.venv/lib/python3.14/site-packages/hermes-memory-deps.pth:ro",
    ]
    for mount in expected:
        assert mount in volumes, mount
    for mount in volumes:
        if any(t in mount for t in (":/opt/data/plugins", ":/opt/data/hindsight", "memory-deps", ":/opt/hermes/")):
            assert mount.endswith(":ro"), mount


def test_packages_reach_sys_path_through_a_pth_file_not_pythonpath():
    """The image's launcher rewrites PYTHONPATH before it starts the gateway (harness gate,
    2026-10-31), so a PYTHONPATH in compose never reaches the plugin's import."""
    service = render_compose()["services"]["hermes-agent"]
    assert "PYTHONPATH" not in str(service.get("environment", {}))
    tasks = (HERMES_ROLE / "tasks" / "memory_plugin.yml").read_text()
    assert 'content: "/opt/hermes-memory-deps\\n"' in tasks
    assert "dest: \"{{ hermes_memory_pth_path }}\"" in tasks


def test_deploy_asserts_the_gateway_can_import_the_client():
    tasks = yaml.safe_load((HERMES_ROLE / "tasks" / "main.yml").read_text())
    task = next(t for t in tasks if t.get("name") == "Assert the agent can import the memory provider's packages")
    argv = task["ansible.builtin.command"]["argv"]
    assert argv[-1] == "import hindsight_client, hindsight_embed, aiohttp_retry"
    assert "PYTHONPATH=/opt/hermes/.:{{ hermes_agent_site_packages }}" in argv


def test_compose_confinement_assert_covers_the_new_mounts():
    tasks = (HERMES_ROLE / "tasks" / "main.yml").read_text()
    assert "select('search', ':/opt/data/hindsight') | reject('search', ':ro$')" in tasks
    assert "select('search', ':/opt/hermes-memory-deps') | reject('search', ':ro$')" in tasks
    assert "select('search', ':/opt/hermes/') | reject('search', ':ro$')" in tasks


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


# --------------------------------------------------------------------------- Open WebUI (US2)
#
# Spec 097 T040: the Open WebUI filter, the one-shot import of Open WebUI's memories and the
# retirement of that feature (research R-007, R-008). The filter's own behaviour and the two
# container-side scripts are unit-tested in python/tests/open_webui_memory_filter/.

FILTER_FILE = HERMES_ROLE / "files" / "open_webui" / "memory_filter.py"
FILTER_TASK = "Reconcile the shared memory filter (097 T042, R-007)"
CONFIG_TASK = "Reconcile the persisted Open WebUI configuration we own"
TOOL_SERVER_TASK = "Reconcile the persisted MCP tool-server registrations"
IMPORT_READ_TASK = "Read Open WebUI's own memories for the one-shot import (097 R-008)"
IMPORT_TASK = "Import Open WebUI's memories into the shared memory (admin key, synchronous)"
IMPORT_ASSERT_TASK = "Assert every Open WebUI memory is in the shared memory (097 R-008)"


def _tasks() -> list[dict]:
    return yaml.safe_load((HERMES_ROLE / "tasks" / "main.yml").read_text())


def _task(name: str) -> dict:
    return next(t for t in _tasks() if t.get("name") == name)


def _index(name: str) -> int:
    return next(i for i, t in enumerate(_tasks()) if t.get("name") == name)


def _filter_constant(name: str):
    """A module-level literal of the filter, read without importing it (it needs requests)."""
    for node in ast.parse(FILTER_FILE.read_text()).body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == name for t in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError(f"{name} not found in {FILTER_FILE}")


def test_open_webui_memories_are_switched_off_in_compose():
    env = render_compose()["services"]["open-webui"]["environment"]
    assert str(env["ENABLE_MEMORIES"]).lower() == "false"
    assert str(env["USER_PERMISSIONS_FEATURES_MEMORIES"]).lower() == "false"


def test_managed_config_switches_memories_off():
    """ENABLE_MEMORIES seeds a fresh database only; the reconcile turns an existing install off
    (memories.enable is a PersistentConfig in Open WebUI 0.11.3, config.py)."""
    managed = yaml.safe_load((ROOT / "ansible/group_vars/services/vars.yml").read_text())["hermes_managed_config"]
    assert str(managed["memories.enable"]).lower() == "false"


def test_filter_reconcile_carries_the_open_webui_key_never_the_hermes_key():
    task = _task(FILTER_TASK)
    payload = task["vars"]["hermes_memory_filter_payload"]
    assert payload["valves"]["key"] == "{{ memory_client_open_webui_key }}"
    assert "memory_client_hermes_key" not in yaml.safe_dump(task)
    assert task["ansible.builtin.command"]["stdin"] == "{{ hermes_memory_filter_payload | to_json }}"
    assert str(task["no_log"]).lower() == "true"


def test_filter_valve_url_goes_through_caddy_never_the_direct_port():
    payload = _task(FILTER_TASK)["vars"]["hermes_memory_filter_payload"]
    vars_yml = yaml.safe_load((ROOT / "ansible/group_vars/services/vars.yml").read_text())
    env = Environment(undefined=StrictUndefined)
    ctx = {"caddy_base_domain": vars_yml["caddy_base_domain"]}
    ctx["hermes_memory_api_url"] = env.from_string(_defaults()["hermes_memory_api_url"]).render(**ctx)
    url = env.from_string(payload["valves"]["url"]).render(**ctx)
    assert url.startswith("https://memory-api.")
    assert ":8888" not in url


def test_filter_reconcile_reads_the_agent_models_with_the_agent_key():
    payload = _task(FILTER_TASK)["vars"]["hermes_memory_filter_payload"]
    assert payload["id"] == "shared_memory"
    assert payload["models_url"] == "{{ hermes_agent_api_base_url }}/models"
    assert payload["models_key"] == "{{ hermes_agent_api_server_key }}"
    assert payload["content"] == "{{ lookup('ansible.builtin.file', 'open_webui/memory_filter.py') }}"
    assert payload["valves"]["bank"] == "{{ hermes_memory_bank_id }}"


def test_filter_reconcile_runs_after_the_tool_server_reconcile():
    assert _index(FILTER_TASK) > _index(TOOL_SERVER_TASK)


def test_import_runs_before_memories_are_switched_off():
    """R-008: import while memories.enable is still true; the config reconcile flips it."""
    for name in (IMPORT_READ_TASK, IMPORT_TASK, IMPORT_ASSERT_TASK):
        assert _index(name) < _index(CONFIG_TASK), name


def test_import_uses_the_admin_key_and_is_prod_only():
    task = _task(IMPORT_TASK)
    dumped = yaml.safe_dump(task)
    assert "memory_admin_key" in dumped
    assert "memory_client_" not in dumped
    assert str(task["no_log"]).lower() == "true"
    assert task["ansible.builtin.uri"]["url"] == (
        "{{ hermes_memory_api_url }}/v1/default/banks/{{ hermes_memory_bank_id }}/memories")
    read = _task(IMPORT_READ_TASK)
    assert str(read["no_log"]).lower() == "true"
    assert "(deploy_environment | default('prod')) != 'lab'" in yaml.safe_dump(read["when"])


def test_every_task_naming_a_memory_key_is_no_log():
    for task in _tasks():
        if re.search(r"memory_(admin|client_\w+)_key", yaml.safe_dump(task)):
            assert str(task.get("no_log")).lower() == "true", task.get("name")


def test_lab_records_the_skipped_import():
    tasks = (HERMES_ROLE / "tasks" / "main.yml").read_text()
    assert "Open WebUI memories import" in tasks
    assert tasks.count("{{ evidence_dir }}/reports/lab/skipped-checks.txt") >= 2


def test_filter_preamble_is_the_contract_verbatim():
    contract = (ROOT / "specs/097-hermes-long-term-memory/contracts/turn-format.md").read_text()
    block = contract.split("```text\n", 1)[1].split("\n\n- <recalled text 1>", 1)[0]
    assert _filter_constant("PREAMBLE") == block


def test_filter_secret_patterns_are_alloy_redaction_patterns():
    """turn-format.md rule 6: adapters strip what the estate's Alloy redaction would."""
    alloy = yaml.safe_load((ROOT / "ansible/roles/alloy/defaults/main.yml").read_text())
    expressions = {
        re.sub(r"^(\\b)?\((.*)\)$", r"\1\2", rule["expression"])
        for rules in alloy.values() if isinstance(rules, list)
        for rule in rules if isinstance(rule, dict) and "expression" in rule
    }
    patterns = _filter_constant("SECRETS")
    assert r"hmem_[A-Za-z0-9_-]{20,}" in patterns
    for pattern in patterns:
        assert pattern in expressions, pattern


# --------------------------------------------------------------------------- built-in memory import
#
# 097 § 8: built-in memory is switched off, and its two files are retained once into the shared
# store. The item builder is rendered with stand-ins for Ansible's filters; the split was also
# checked with real Ansible on the dev Mac (2026-11-01).

BUILTIN_TASKS = (
    "Check whether the built-in memory was imported already",
    "Read the built-in memory notes for the one-shot import (inside the agent, as hermes)",
    "Build the built-in memory retain items",
    "Import the built-in memory into the shared memory (agent key, synchronous)",
    "Count the built-in memory entries in the shared memory after the import",
    "Assert every built-in memory entry is in the shared memory (097 § 8)",
    "Mark the built-in memory as imported",
)


def _build_items(files: dict[str, str]) -> list[dict]:
    import base64
    import hashlib

    expression = _task("Build the built-in memory retain items")["ansible.builtin.set_fact"]["hermes_builtin_memory_items"]
    env = Environment(undefined=StrictUndefined)
    env.filters["b64decode"] = lambda v: base64.b64decode(v).decode()
    env.filters["hash"] = lambda v, algo: hashlib.new(algo, v.encode()).hexdigest()
    env.filters["regex_replace"] = lambda v, pattern, repl: re.sub(pattern, repl, v)
    notes = files.get("MEMORY", "")
    rendered = env.from_string(expression).render(
        hermes_builtin_memory_notes={"stdout": base64.b64encode(notes.encode()).decode()},
        hermes_builtin_memory_redact_pattern=_defaults()["hermes_builtin_memory_redact_pattern"])
    return ast.literal_eval(rendered)


def test_builtin_import_splits_entries_as_hermes_does():
    items = _build_items({"MEMORY": "Likes tea.\n§\nKey hmem_abcdefghijklmnopqrstuvwxyz0 here.\n§\n\n§\nTwo\nlines."})
    assert [i["content"] for i in items] == ["Likes tea.", "Key <redacted> here.", "Two\nlines."]
    for item in items:
        assert re.fullmatch(r"hermes-builtin-memory-[0-9a-f]{16}", item["document_id"])
        assert item["context"] == "Hermes built-in memory memory entry"
        assert item["tags"] == ["builtin-memory", "builtin-target:memory", "origin:hermes-builtin-memory"]


def test_builtin_import_of_absent_notes_is_empty():
    assert _build_items({}) == []


def test_builtin_import_is_once_prod_only_private_and_uses_the_agent_key():
    for name in BUILTIN_TASKS:
        task = _task(name)
        assert "(deploy_environment | default('prod')) != 'lab'" in yaml.safe_dump(task["when"]), name
        if name != BUILTIN_TASKS[0]:
            assert "not hermes_builtin_memory_marker.stat.exists" in yaml.safe_dump(task["when"]), name
    for name in BUILTIN_TASKS[1:5]:
        assert str(_task(name)["no_log"]).lower() == "true", name
    dumped = yaml.safe_dump(_task(BUILTIN_TASKS[3]))
    assert "memory_client_hermes_key" in dumped and "memory_admin_key" not in dumped
    assert _index(BUILTIN_TASKS[5]) < _index(BUILTIN_TASKS[6]), "the marker follows the assert"


READER = HERMES_ROLE / "files" / "read_builtin_notes.py"


def test_builtin_notes_are_read_inside_the_agent_as_hermes():
    """PR #340 review: root on the host must never read a path the agent controls."""
    argv = _task(BUILTIN_TASKS[1])["ansible.builtin.command"]["argv"]
    assert argv[:5] == ["docker", "exec", "-u", "hermes", "hermes_agent"]
    assert "read_builtin_notes.py" in argv[7] and argv[8] == "/opt/data/memories/MEMORY.md"
    assert "failed_when" not in _task(BUILTIN_TASKS[1]) and "ignore_errors" not in _task(BUILTIN_TASKS[1])
    assert not any("slurp" in str(t) and "memories" in str(t) for t in _tasks())


def _read_notes(path):
    import subprocess
    import sys
    return subprocess.run([sys.executable, str(READER), str(path)], capture_output=True, text=True)


def test_reader_prints_a_regular_file_and_nothing_when_absent(tmp_path):
    import base64
    notes = tmp_path / "MEMORY.md"
    notes.write_text("Likes tea.\n§\nTwo")
    out = _read_notes(notes)
    assert out.returncode == 0 and base64.b64decode(out.stdout).decode() == "Likes tea.\n§\nTwo"
    absent = _read_notes(tmp_path / "missing.md")
    assert (absent.returncode, absent.stdout) == (0, "")


def test_reader_refuses_a_symlinked_file_or_directory(tmp_path):
    secret = tmp_path / "host-secret"
    secret.write_text("root:x:0:0")
    (tmp_path / "memories").mkdir()
    (tmp_path / "memories" / "MEMORY.md").symlink_to(secret)
    linked = _read_notes(tmp_path / "memories" / "MEMORY.md")
    assert linked.returncode != 0 and "root:x" not in linked.stdout
    (tmp_path / "elsewhere").mkdir()
    (tmp_path / "elsewhere" / "MEMORY.md").write_text("x")
    (tmp_path / "linkdir").symlink_to(tmp_path / "elsewhere")
    assert _read_notes(tmp_path / "linkdir" / "MEMORY.md").returncode != 0


def test_reader_refuses_a_non_regular_file(tmp_path):
    (tmp_path / "MEMORY.md").mkdir()
    assert _read_notes(tmp_path / "MEMORY.md").returncode != 0


def test_builtin_import_redacts_the_same_token_shapes_as_the_open_webui_filter():
    """PR #340 review: the import is a retain into the shared store, so it strips what the filter
    strips (the estate's Alloy redaction patterns)."""
    assert _defaults()["hermes_builtin_memory_redact_pattern"] == "|".join(_filter_constant("SECRETS"))
    tokens = ("sk-" + "a" * 20, "tskey-auth-" + "b" * 20, "tk_" + "c" * 29,
              "eyJ" + "d" * 10 + ".eyJ" + "e" * 10 + "." + "f" * 10, "hmem_" + "g" * 43)
    [item] = _build_items({"MEMORY": "keys: " + " ".join(tokens)})
    assert item["content"] == "keys: " + " ".join(["<redacted>"] * len(tokens))


def test_builtin_import_marker_is_outside_the_agent_writable_data():
    marker = _defaults()["hermes_builtin_memory_import_marker"]
    assert marker.startswith("{{ hermes_install_dir }}/")
    assert "hermes_agent_data_dir" not in marker


def test_harness_agent_memory_switches_match_production():
    """The harness gate (FR-021) runs its own config.yaml; its memory section must be PROD's."""
    harness = yaml.safe_load((ROOT / "docs/backlog/097-spike/runs/prod-render/config.yaml").read_text())
    assert {k: str(v).lower() for k, v in harness["memory"].items()} == {
        k: str(v).lower() for k, v in render_agent_config()["memory"].items()}
    compose = (ROOT / "docs/backlog/097-spike/compose.prod-render.yml").read_text()
    assert "./runs/prod-render/build/SOUL.md:/opt/data/SOUL.md:ro" in compose
    # SOUL.md names the memory tools, so the harness agent must have them, as PROD does.
    memory = harness["mcp_servers"]["memory"]
    assert memory["url"].endswith("/mcp/owner/")
    assert memory["headers"] == {"Authorization": "Bearer ${AUXILIARY_MCP_MEMORY_API_KEY}"}
    assert "env_file: ./runs/prod-render/build/agent-mcp.env" in compose
