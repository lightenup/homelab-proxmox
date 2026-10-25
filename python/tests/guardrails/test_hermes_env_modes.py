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

import re
from pathlib import Path

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
]


def _base_context() -> dict:
    ctx: dict = {
        "caddy_base_domain": "example.invalid",
        # Mirrors ansible/roles/hermes/defaults/main.yml hermes_mcp_servers: market-model is
        # auth: none, so the bearer-only loop in agent.env.j2 never fires. If a bearer-auth
        # server is ever enabled by default, its credential_env joins SECRET_VAR_NAMES and
        # whichever pinned set(s) it renders into (R-016 decision).
        "hermes_mcp_servers": [
            {
                "name": "market-model",
                "url": "http://market-model.example.invalid:8001/mcp",
                "auth": "none",
                "credential_env": None,
                "enabled": True,
            }
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
