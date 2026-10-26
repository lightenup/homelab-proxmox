"""Guard test: the ntfy auth-access ACL matrix (specs 082 SC-002, extended by 095).

T003 baseline: renders ansible/roles/ntfy/templates/server.yml.j2 from
ansible/roles/ntfy/defaults/main.yml with stubbed secret vars (caddy_base_domain
example.invalid), parses auth-access into (user, topic, perm) tuples, and asserts today's
matrix exactly: owner:*:read-only plus one write-only grant per publisher. Helpers
writers(topic)/readers(topic) are extended by later tasks:

- T006 (US foundation): the two data-model validation rules.
- T007 (FR-011): the LAB scratch pair.
- T009 (US1): the hermes-in columns of contracts/acl-matrix.md.
- T044 (P2): the full 095 matrix (actions / relay / action_relay). Until P2 lands, the
  per-story tests assert the P1 cells; test_095_topics_matrix_full is added with T044.
"""

from __future__ import annotations

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
NTFY_ROLE = ROOT / "ansible" / "roles" / "ntfy"

# Secret vars are stubbed with placeholders: this test guards the ACL matrix, never values.
# The ntfy_hermes_lab_* / ntfy_action_relay_* stubs must exist for the post-T007/T043 render
# to resolve under StrictUndefined; preflight asserts their presence in the vault (T007/T043).
STUB_SECRETS = {
    "ntfy_owner_password_hash": "$2b$12$placeholderplaceholderplaceholderplaceholderplaceholderpl",
    "ntfy_owner_token": "tk_" + "a" * 29,
    "ntfy_alertmanager_password_hash": "$2b$12$placeholderplaceholderplaceholderplaceholderplaceholderpl",
    "ntfy_alertmanager_token": "tk_" + "b" * 29,
    "ntfy_hermes_password_hash": "$2b$12$placeholderplaceholderplaceholderplaceholderplaceholderpl",
    "ntfy_hermes_token": "tk_" + "c" * 29,
    "ntfy_pve_backup_password_hash": "$2b$12$placeholderplaceholderplaceholderplaceholderplaceholderpl",
    "ntfy_pve_backup_token": "tk_" + "d" * 29,
    "ntfy_version_check_password_hash": "$2b$12$placeholderplaceholderplaceholderplaceholderplaceholderpl",
    "ntfy_version_check_token": "tk_" + "e" * 29,
    "ntfy_mutation_password_hash": "$2b$12$placeholderplaceholderplaceholderplaceholderplaceholderpl",
    "ntfy_mutation_token": "tk_" + "f" * 29,
    "ntfy_hermes_lab_password_hash": "$2b$12$placeholderplaceholderplaceholderplaceholderplaceholderpl",
    "ntfy_hermes_lab_token": "tk_" + "g" * 29,
    "ntfy_action_relay_password_hash": "$2b$12$placeholderplaceholderplaceholderplaceholderplaceholderpl",
    "ntfy_action_relay_token": "tk_" + "h" * 29,
}


def _defaults() -> dict:
    text = (NTFY_ROLE / "defaults" / "main.yml").read_text()
    return yaml.safe_load(text)


def render_server_yml() -> str:
    env = Environment(
        loader=FileSystemLoader(str(NTFY_ROLE / "templates")),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
    )
    defaults = _defaults()
    ctx = {
        "caddy_base_domain": "example.invalid",
        "ntfy_owner_password_hash": STUB_SECRETS["ntfy_owner_password_hash"],
        "ntfy_owner_token": STUB_SECRETS["ntfy_owner_token"],
        "ntfy_users": defaults["ntfy_users"],
        "ntfy_owner_access": defaults["ntfy_owner_access"],
    }
    for user in defaults["ntfy_users"]:
        # password_hash/token are Jinja placeholders like "{{ ntfy_hermes_token }}";
        # stub every referenced var name with its placeholder value.
        for key in ("password_hash", "token"):
            ref = re.fullmatch(r"\{\{\s*(\w+)\s*\}\}", str(user[key]))
            assert ref, f"{user['name']}.{key} must be a plain {{{{ var }}}} placeholder"
            ctx[ref.group(1)] = STUB_SECRETS[ref.group(1)]
    return env.get_template("server.yml.j2").render(**ctx)


def _access_rules() -> list[tuple[str, str, str]]:
    rendered = yaml.safe_load(render_server_yml())
    rules = []
    for entry in rendered["auth-access"]:
        user, topic, perm = str(entry).split(":", 2)
        rules.append((user, topic, perm))
    return rules


def writers(topic: str) -> set[str]:
    """Users whose grants include write on `topic` (exact pattern match)."""
    return {u for u, t, p in _access_rules() if t == topic and p in ("write-only", "read-write")}


def readers(topic: str) -> set[str]:
    """Users who can read `topic`: explicit read grants, or the owner's `*:read-only`."""
    out = set()
    for u, t, p in _access_rules():
        if p in ("read-only", "read-write"):
            if t == topic or t == "*":
                out.add(u)
    return out


def test_render_parses_and_users_match_defaults() -> None:
    rendered = yaml.safe_load(render_server_yml())
    defaults = _defaults()
    auth_users = [str(e).split(":")[0] for e in rendered["auth-users"]]
    expected = ["owner"] + [u["name"] for u in defaults["ntfy_users"]]
    assert sorted(auth_users) == sorted(expected)


def test_message_size_limit_unchanged() -> None:
    """spec 095 Edge Case 'Oversized inbound message': server limit stays 32k."""
    rendered = yaml.safe_load(render_server_yml())
    assert str(rendered["message-size-limit"]) == "32k"


def test_pve_backup_topic_constant_matches_its_grant() -> None:
    """089 T035 coupling: the backup role's ntfy topic constant tracks its ACL grant."""
    entry = next(u for u in _defaults()["ntfy_users"] if u["name"] == "pve_backup")
    topics = [t for t, p in _user_grants(entry) if p in ("write-only", "read-write")]
    assert topics == ["pve-backup"]
    pve_vars = (ROOT / "ansible/group_vars/proxmox_hosts/vars.yml").read_text()
    assert 'proxmox_backup_ntfy_topic: "pve-backup"' in pve_vars


def _user_grants(user: dict) -> list[tuple[str, str]]:
    """(topic, perm) pairs from a defaults entry's `access:` list (T004 shape)."""
    out = []
    for grant in user["access"]:
        topic, perm = grant.split(":", 1)
        out.append((topic, perm))
    return out


# --- 082 baseline matrix (behaviour-preserving across the T004/T005 refactor) ---


def test_owner_is_read_only_wildcard() -> None:
    assert ("owner", "*", "read-only") in _access_rules()


def test_every_publisher_has_write_only_on_its_topic() -> None:
    """T003/T004: every publisher's write grant appears in the rendered matrix."""
    for user in _defaults()["ntfy_users"]:
        for topic, perm in _user_grants(user):
            if perm in ("write-only", "read-write"):
                assert (user["name"], topic, perm) in _access_rules(), (
                    f"{user['name']} must hold {perm} on {topic}"
                )


def test_owner_access_list_is_read_only_wildcard_plus_inbound_topics() -> None:
    """T004/T007/T012: owner reads everything, plus read-write on the inbound topics. read-write,
    not write-only: the specific entry replaces the wildcard read for that topic (R-004)."""
    assert _defaults()["ntfy_owner_access"] == [
        "*:read-only", "hermes-lab-in:read-write", "hermes-in:read-write",
    ]


def test_writers_baseline() -> None:
    """082 publishers, excluding the P2 relay (its writers cell is in the P2 test)."""
    assert writers("hermes") == {"hermes"}
    assert writers("pve-backup") == {"pve_backup"}
    assert writers("versions") == {"version_check"}
    assert writers("mutation") == {"mutation"}


# --- extended by later tasks ---
# T007 (LAB scratch pair), T009 (hermes-in columns) and T044 (full 095 matrix incl.
# actions/relay/action_relay) extend this file in place.
#
# T006: the two data-model validation rules, mirroring the preflight asserts in
# ansible/roles/ntfy/tasks/preflight.yml (which fail the deploy on the same data).


def test_one_writer_per_writable_topic() -> None:
    """082 rule (data-model § Validation): one non-owner writer per writable topic."""
    writers_per_topic: dict[str, list[str]] = {}
    for user in _defaults()["ntfy_users"]:
        for topic, perm in _user_grants(user):
            if perm in ("write-only", "read-write"):
                writers_per_topic.setdefault(topic, []).append(user["name"])
    for topic, ws in writers_per_topic.items():
        assert len(ws) == 1, f"topic {topic} has writers {ws}, want exactly one"


def test_no_non_owner_write_on_inbound_or_action_topics() -> None:
    """FR-002 (data-model § Validation): hermes-in/actions/hermes-lab-in are owner-only."""
    for user in _defaults()["ntfy_users"]:
        for topic, perm in _user_grants(user):
            if topic in ("hermes-in", "actions", "hermes-lab-in"):
                assert perm not in ("write-only", "read-write"), (
                    f"{user['name']} must not write {topic} (FR-002)"
                )


# --- T007 (FR-011): the LAB scratch pair ---

PRODUCTION_TOPICS = {
    "hermes", "hermes-in", "alerts", "actions", "relay",
    "pve-backup", "versions", "mutation",
}


def test_hermes_lab_scratch_pair_grants() -> None:
    """FR-011: hermes_lab reads hermes-lab-in and writes only hermes-lab."""
    entry = next(u for u in _defaults()["ntfy_users"] if u["name"] == "hermes_lab")
    assert _user_grants(entry) == [
        ("hermes-lab-in", "read-only"),
        ("hermes-lab", "write-only"),
    ]
    assert writers("hermes-lab") == {"hermes_lab"}
    assert writers("hermes-lab-in") == {"owner"}
    assert ("owner", "hermes-lab-in", "read-write") in _access_rules()


def test_hermes_lab_has_no_grant_on_any_production_topic() -> None:
    """FR-011 / SC-002: the scratch user touches nothing outside the scratch pair."""
    entry = next(u for u in _defaults()["ntfy_users"] if u["name"] == "hermes_lab")
    for topic, _perm in _user_grants(entry):
        assert topic not in PRODUCTION_TOPICS, (
            f"hermes_lab holds a grant on production topic {topic} (FR-011)"
        )


# --- T009 (US1, FR-001/FR-002): the hermes-in columns of contracts/acl-matrix.md ---


def test_only_owner_writes_hermes_in() -> None:
    """Bold cell: the agent's credential can never write its own inbound topic."""
    assert writers("hermes-in") == {"owner"}
    assert ("owner", "hermes-in", "read-write") in _access_rules()


def test_owner_and_agent_read_hermes_in() -> None:
    assert readers("hermes-in") == {"owner", "hermes"}


def test_agent_reads_hermes_in_and_still_writes_only_hermes() -> None:
    entry = next(u for u in _defaults()["ntfy_users"] if u["name"] == "hermes")
    assert _user_grants(entry) == [("hermes", "write-only"), ("hermes-in", "read-only")]
