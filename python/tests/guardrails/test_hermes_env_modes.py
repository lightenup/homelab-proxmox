"""Guard test: hermes agent.env in all three modes, and the credential freeze (R-016, T070).

Renders `ansible/roles/hermes/templates/agent.env.j2` offline with plain Jinja2 (StrictUndefined)
in the three modes the role actually supports, selected the same way `hermes_agent_operational`
and `lab_inventory` select them at deploy time:

- **PROD** (`hermes_agent_operational: true`): inbound `hermes-in`, publish `hermes`, the PROD
  ntfy token.
- **LAB rig** (`hermes_agent_operational: false`, `lab_inventory: true`): the scratch pair
  `hermes-lab-in` / `hermes-lab`, the LAB ntfy token (spec 095 FR-011).
- **Pipeline LAB stage** (neither): no `NTFY_TOPIC`, no `NTFY_TOKEN`, no `NTFY_ALLOWED_USERS`
  (083 FR-014).

Every secret-bearing variable is stubbed with a distinct, greppable placeholder
(`STUB__<varname>__`), so the test can tell *which* secrets a render actually pulled in, not just
that rendering succeeded. That is the credential freeze from research R-016: today the LAB rig
holds production router/API identities alongside the LAB-only ntfy pair, and adding a key to the
rig is a credential-policy decision, not a silent template edit. Changing either pinned set below
is that decision — record it in research.md R-016 and update this test in the same change.

`agent.env.j2` also calls Ansible's `lookup('vars', name | lower)`, which is not a plain Jinja2
builtin; `_fake_lookup` below stands in for it, reading from the same stub context used for direct
`{{ var }}` references so both paths agree. The template's `| bool` and `| default(...)` filters
are likewise Ansible extensions (`default` ships with Jinja2; `bool` does not), so `bool` is
registered as a thin Python `bool()` wrapper — sufficient here because every value it is applied
to in this template is already a Python bool.
"""

from __future__ import annotations

import base64
import re
from pathlib import Path

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


def _stub(name: str) -> str:
    """A distinct, greppable placeholder — unique per variable name, never a real secret."""
    return f"STUB__{name}__"


# The full universe of secret-bearing variables agent.env.j2 can render, across all three
# modes. Every value is `_stub(name)`, so "is X's stub present in this render" tells us whether
# X was actually substituted, not just declared in the context.
SECRET_VAR_NAMES = [
    "hermes_agent_api_server_key",
    "llm_router_client_hermes_agent_key",
    "llm_router_client_scout_probe_key",
    "ntfy_hermes_token",
    "ntfy_hermes_lab_token",
    "hermes_mcp_homeassistant_key",
]


def _base_context() -> dict:
    ctx: dict = {
        "caddy_base_domain": "example.invalid",
        # Mirrors group_vars/services/vars.yml hermes_mcp_servers. market-model is auth: none,
        # so the bearer-only loop in agent.env.j2 skips it. homeassistant is auth: bearer and
        # enabled only when hermes_agent_operational (PROD); _render sets that per mode, the
        # same way the vars.yml template does (R-016, 2026-10-30 addendum).
        "hermes_mcp_servers": [
            {
                "name": "market-model",
                "url": "http://market-model.example.invalid:8001/mcp",
                "auth": "none",
                "credential_env": None,
                "enabled": True,
            },
            {
                "name": "homeassistant",
                "url": "http://homeassistant.example.invalid:8123/api/mcp/assist",
                "auth": "bearer",
                "credential_env": "AUXILIARY_MCP_HOMEASSISTANT_API_KEY",
                "vault_var": "hermes_mcp_homeassistant_key",
                "enabled": None,
            },
        ],
        # Mirrors hermes_agent_env_passthrough (backlog 088 scout-assess probe).
        "hermes_agent_env_passthrough": ["LLM_ROUTER_CLIENT_SCOUT_PROBE_KEY"],
    }
    for name in SECRET_VAR_NAMES:
        ctx[name] = _stub(name)
    return ctx


def _fake_lookup(kind: str, key: str, default: object = None) -> object:
    """Stand-in for Ansible's `lookup()` global, used by agent.env.j2's two for-loops.

    Only `lookup('vars', <name>)` is used by this template; reads from the same stub map as
    direct `{{ var }}` references, so both paths agree on what a given variable renders as.
    """
    assert kind == "vars", f"agent.env.j2 only uses lookup('vars', ...), got lookup({kind!r}, ...)"
    stubs = {name: _stub(name) for name in SECRET_VAR_NAMES}
    if key in stubs:
        return stubs[key]
    if default is not None:
        return default
    raise LookupError(f"no stub registered for lookup('vars', {key!r})")


def _render(hermes_agent_operational: bool, lab_inventory: bool) -> str:
    env = Environment(
        loader=FileSystemLoader(str(HERMES_ROLE / "templates")),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
    )
    env.globals["lookup"] = _fake_lookup
    env.filters["bool"] = bool
    ctx = _base_context()
    ctx["hermes_agent_operational"] = hermes_agent_operational
    ctx["lab_inventory"] = lab_inventory
    for server in ctx["hermes_mcp_servers"]:
        if server["name"] == "homeassistant":
            server["enabled"] = hermes_agent_operational
    return env.get_template("agent.env.j2").render(**ctx)


def render_prod() -> str:
    return _render(hermes_agent_operational=True, lab_inventory=False)


def render_lab_rig() -> str:
    return _render(hermes_agent_operational=False, lab_inventory=True)


def render_pipeline_lab_stage() -> str:
    return _render(hermes_agent_operational=False, lab_inventory=False)


def _secrets_present(rendered: str) -> set[str]:
    """Which of SECRET_VAR_NAMES actually made it into this render."""
    return {name for name in SECRET_VAR_NAMES if _stub(name) in rendered}


# --- (a) ntfy topic/token selection per mode (spec FR-011, 083 FR-014) ---


def test_prod_renders_the_inbound_topic_and_prod_token() -> None:
    rendered = render_prod()
    assert "NTFY_TOPIC=hermes-in" in rendered
    assert "NTFY_ALLOWED_USERS=hermes-in" in rendered
    assert "NTFY_PUBLISH_TOPIC=hermes" in rendered
    assert _stub("ntfy_hermes_token") in rendered
    assert _stub("ntfy_hermes_lab_token") not in rendered


def _non_comment_lines(rendered: str) -> str:
    """Drop `#` comment lines and blanks — the shared header describes all three modes by
    name (for the human reading the file), which would otherwise trip substring checks below."""
    return "\n".join(
        line for line in rendered.splitlines() if line.strip() and not line.lstrip().startswith("#")
    )


def test_lab_rig_renders_only_the_scratch_pair() -> None:
    rendered = render_lab_rig()
    assert "NTFY_TOPIC=hermes-lab-in" in rendered
    assert "NTFY_ALLOWED_USERS=hermes-lab-in" in rendered
    assert "NTFY_PUBLISH_TOPIC=hermes-lab" in rendered
    assert _stub("ntfy_hermes_lab_token") in rendered
    active = _non_comment_lines(rendered)
    assert "hermes-in" not in active, "the LAB rig must never see the PROD inbound topic"
    assert _stub("ntfy_hermes_token") not in rendered, "the LAB rig must never hold the PROD token"


def test_pipeline_lab_stage_renders_no_ntfy_topic_or_token() -> None:
    """083 FR-014 / 095 FR-011: the pipeline LAB stage never reaches the phone."""
    rendered = render_pipeline_lab_stage()
    assert not re.search(r"^\s*NTFY_TOPIC\s*=", rendered, re.MULTILINE)
    assert not re.search(r"^\s*NTFY_TOKEN\s*=", rendered, re.MULTILINE)
    assert not re.search(r"^\s*NTFY_ALLOWED_USERS\s*=", rendered, re.MULTILINE)
    assert _stub("ntfy_hermes_token") not in rendered
    assert _stub("ntfy_hermes_lab_token") not in rendered


# --- (b) the allow-all escape hatch must never appear (spec FR-003) ---


def test_no_mode_ever_renders_an_allow_all_setting() -> None:
    for rendered in (render_prod(), render_lab_rig(), render_pipeline_lab_stage()):
        assert not re.search(
            r"^\s*(NTFY_ALLOW_ALL_USERS|GATEWAY_ALLOW_ALL_USERS)\s*=", rendered, re.MULTILINE
        )


# --- (c) NTFY_ALLOWED_USERS is a single sender id, never a wildcard or a list ---


def test_ntfy_allowed_users_has_no_wildcard_or_comma() -> None:
    for rendered in (render_prod(), render_lab_rig()):
        match = re.search(r"^NTFY_ALLOWED_USERS=(.*)$", rendered, re.MULTILINE)
        assert match, "PROD and the LAB rig must both render NTFY_ALLOWED_USERS"
        value = match.group(1)
        assert "*" not in value
        assert "," not in value


# --- (d) credential freeze: the exact secret set each mode renders (research R-016) ---

# Changing any of these three sets is a credential-policy decision; record it in research R-016
# before editing the set here.
PROD_SECRETS = {
    "hermes_agent_api_server_key",
    "llm_router_client_hermes_agent_key",
    "llm_router_client_scout_probe_key",
    "ntfy_hermes_token",
    "hermes_mcp_homeassistant_key",
}
LAB_RIG_SECRETS = {
    "hermes_agent_api_server_key",
    "llm_router_client_hermes_agent_key",
    "llm_router_client_scout_probe_key",
    "ntfy_hermes_lab_token",
}
PIPELINE_LAB_STAGE_SECRETS = {
    "hermes_agent_api_server_key",
    "llm_router_client_hermes_agent_key",
    "llm_router_client_scout_probe_key",
}


def test_credential_freeze_prod() -> None:
    assert _secrets_present(render_prod()) == PROD_SECRETS


def test_credential_freeze_lab_rig() -> None:
    """R-016 condition 2: the LAB rig's secret set is pinned. Adding a key here is a decision,
    not a side effect of a template edit — update research.md R-016 in the same change."""
    assert _secrets_present(render_lab_rig()) == LAB_RIG_SECRETS


def test_credential_freeze_pipeline_lab_stage() -> None:
    assert _secrets_present(render_pipeline_lab_stage()) == PIPELINE_LAB_STAGE_SECRETS


# Hermes' child-process filter (083 R-004): `_is_hermes_internal_secret` in the pinned image strips
# AUXILIARY_*_API_KEY / _BASE_URL from every spawn. A bearer token under any other name is readable
# by terminal commands and cron scripts (checked in the v0.21.6 container 2026-10-30:
# HERMES_MCP_HOMEASSISTANT_KEY survived `_sanitize_subprocess_env`, AUXILIARY_MCP_..._API_KEY did not).
_SCRUBBED_BEARER_ENV_RE = re.compile(r"AUXILIARY_[A-Z0-9_]+_API_KEY")


def _group_vars_mcp_servers() -> list[dict]:
    group_vars = yaml.safe_load(
        (ROOT / "ansible" / "group_vars" / "services" / "vars.yml").read_text()
    )
    return group_vars["hermes_mcp_servers"]


def test_every_bearer_mcp_token_uses_a_scrubbed_env_name() -> None:
    bearer = [s for s in _group_vars_mcp_servers() if s.get("auth") == "bearer"]
    assert bearer, "expected at least one bearer entry (homeassistant)"
    for server in bearer:
        assert _SCRUBBED_BEARER_ENV_RE.fullmatch(server["credential_env"]), (
            f"{server['name']}: credential_env {server['credential_env']!r} is not stripped from "
            "Hermes child processes; use AUXILIARY_MCP_<NAME>_API_KEY and set vault_var"
        )


def test_bearer_token_renders_under_its_env_name_from_its_vault_var() -> None:
    rendered = render_prod()
    assert f"AUXILIARY_MCP_HOMEASSISTANT_API_KEY={_stub('hermes_mcp_homeassistant_key')}" in rendered


def test_homeassistant_mcp_is_gated_on_prod_in_group_vars() -> None:
    """The render tests above set homeassistant's `enabled` per mode by hand. This pins the real
    entry to the same gate, so the Home Assistant token cannot reach the LAB rig or the pipeline
    LAB stage by an edit to vars.yml alone (R-016, 2026-10-30 addendum)."""
    entries = [s for s in _group_vars_mcp_servers() if s["name"] == "homeassistant"]
    assert len(entries) == 1
    entry = entries[0]
    assert entry["auth"] == "bearer"
    assert entry["credential_env"] == "AUXILIARY_MCP_HOMEASSISTANT_API_KEY"
    assert entry["vault_var"] == "hermes_mcp_homeassistant_key"
    assert entry["url"].endswith("/api/mcp/assist"), "non-admin access needs the Assist-only path"
    assert re.fullmatch(r"\{\{\s*hermes_agent_operational\s*\|\s*bool\s*\}\}", entry["enabled"])


# --- docker-compose.yml.j2: the vault variables it references directly (not via agent.env) ---

_JINJA_VAR_RE = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)")
_SECRET_NAME_MARKERS = ("key", "secret", "password", "token")


def _secret_like_vars_referenced(template_text: str) -> set[str]:
    names = {m.group(1) for m in _JINJA_VAR_RE.finditer(template_text)}
    return {n for n in names if any(marker in n for marker in _SECRET_NAME_MARKERS)}


# Changing this set is a credential-policy decision; record it in research R-016.
DOCKER_COMPOSE_SECRET_VARS = {
    "hermes_webui_secret_key",
    "hermes_admin_password_bootstrap",
    "llm_router_client_hermes_key",
    "hermes_agent_api_server_key",
    "hermes_searxng_secret",
}


def test_docker_compose_secret_vars_are_pinned() -> None:
    text = (HERMES_ROLE / "templates" / "docker-compose.yml.j2").read_text()
    assert _secret_like_vars_referenced(text) == DOCKER_COMPOSE_SECRET_VARS


# --- the role's own LAB-rig guard task, executed for real (found 2026-10-26, T068) ---
#
# The deploy-time assert in ansible/roles/hermes/tasks/main.yml scanned the WHOLE rendered
# file, including its own header comment ("PROD ... -> inbound hermes-in, publish hermes,
# PROD token."), for the unanchored substring "hermes-in". That comment necessarily names the
# PROD branch to document it, so the guard failed on every correct LAB-rig render, not just a
# leaking one -- caught on the very first real deploy to the rig (T068), since nothing had
# exercised this task end-to-end before. Fixed by rejecting comment lines first. This test runs
# the REAL task's Jinja expressions (parsed from the YAML, not re-implemented), so a future edit
# that reintroduces the same mistake fails here, not in production again.


def _hermes_main_tasks() -> list[dict]:
    return yaml.safe_load((HERMES_ROLE / "tasks" / "main.yml").read_text())


def _find_task(tasks: list[dict], name: str) -> dict:
    for task in tasks:
        if task.get("name") == name:
            return task
    raise AssertionError(f"no task named {name!r} in hermes/tasks/main.yml")


def _strip_jinja_braces(expr: str) -> str:
    match = re.fullmatch(r"\{\{\s*(.*?)\s*\}\}", expr.strip(), re.DOTALL)
    assert match, f"expected a {{{{ ... }}}} template string, got: {expr!r}"
    return match.group(1)


def _ansible_like_jinja_env() -> Environment:
    """A bare Jinja2 Environment with just enough of Ansible's extensions registered to
    evaluate this role's own assert expressions for real: the `match`/`search` tests (regex,
    anchored/unanchored respectively) and the `b64decode` filter. Mirrors the `lookup`/`bool`
    stand-ins used for agent.env.j2 itself, above."""
    jenv = Environment(undefined=StrictUndefined)
    jenv.tests["match"] = lambda value, pattern: re.match(pattern, str(value)) is not None
    jenv.tests["search"] = lambda value, pattern: re.search(pattern, str(value)) is not None
    jenv.filters["b64decode"] = lambda s: base64.b64decode(s).decode()
    return jenv


def test_lab_rig_guard_task_is_not_fooled_by_the_header_comment() -> None:
    task = _find_task(
        _hermes_main_tasks(),
        "Assert the LAB rig environment holds only the scratch pair (095 FR-011)",
    )
    env_lines_expr = task["vars"]["env_lines"]
    that_exprs = task["ansible.builtin.assert"]["that"]

    jenv = _ansible_like_jinja_env()

    # hermes_agent_env_rendered is the ansible.builtin.slurp result the real task reads from;
    # reproduce its shape (base64 content) rather than the plain string agent.env.j2 renders to.
    fake_slurp = {"content": base64.b64encode(render_lab_rig().encode()).decode()}
    env_lines = jenv.compile_expression(_strip_jinja_braces(env_lines_expr))(
        hermes_agent_env_rendered=fake_slurp
    )

    for expr in that_exprs:
        result = jenv.compile_expression(expr)(
            env_lines=env_lines, ntfy_hermes_token=_stub("ntfy_hermes_token")
        )
        assert result is True, f"condition evaluated to {result!r}: {expr}"


def test_allow_all_guard_runs_on_every_deploy_including_prod() -> None:
    """095 T016 (FR-003): PROD is where hermes-in reaches the agent, so the allow-all guard must
    not be skipped there. It also executes cleanly against a real PROD render."""
    task = _find_task(
        _hermes_main_tasks(),
        "Assert no allow-all variable ever appears in the agent environment (095 FR-003)",
    )
    assert "when" not in task, "the allow-all guard must run in every mode, PROD included"
    jenv = _ansible_like_jinja_env()
    fake_slurp = {"content": base64.b64encode(render_prod().encode()).decode()}
    env_lines = jenv.compile_expression(_strip_jinja_braces(task["vars"]["env_lines"]))(
        hermes_agent_env_rendered=fake_slurp
    )
    for expr in task["ansible.builtin.assert"]["that"]:
        assert jenv.compile_expression(expr)(env_lines=env_lines) is True, expr
