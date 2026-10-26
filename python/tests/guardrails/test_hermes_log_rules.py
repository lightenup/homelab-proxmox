"""Guard test: Hermes log collection and the 095 log rules (T022, T028, T072; research R-008, R-014).

What it pins:

- T072: Hermes's own log folder lives on the host at /var/log/hermes-agent (bind-mounted at
  /opt/data/logs), outside the agent's 0750 state folder, and alloy collects exactly gateway.log.
  An exact path (not a glob) keeps alloy's readability check active (it skips globs) and stops
  rotated gateway.log.N files being re-read as new streams. The playbook creates the folder and an
  empty gateway.log before lxc_base runs that readability check, so the first deploy can't fail on
  ordering.
- T022/T023: HermesPermanentApprovalGranted fires on any `via /approve (always)` line in that file
  stream. The approval lines are INFO and only exist in gateway.log (T008 step 2, R-014).
- T028/T030: HermesNtfyStreamDown fires on sustained `Stream error` WARNINGs, which are on the
  container's stdout (T008 step 9: 60 s cap, so a [5m] window always sees them).
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml


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
ANSIBLE = ROOT / "ansible"
LOG_DIR = "/var/log/hermes-agent"
GATEWAY_LOG = f"{LOG_DIR}/gateway.log"


class _Loader(yaml.SafeLoader):
    """SafeLoader that accepts Ansible's !unsafe and re-pins bool resolution (same cross-test
    workaround as test_log_pipeline.py)."""


_Loader.add_constructor("!unsafe", lambda loader, node: loader.construct_scalar(node))
_Loader.add_implicit_resolver(
    "tag:yaml.org,2002:bool",
    re.compile(r"^(?:yes|Yes|YES|no|No|NO|true|True|TRUE|false|False|FALSE|on|On|ON|off|Off|OFF)$"),
    list("yYnNtTfFoO"),
)


def _load(rel: str):
    return yaml.load((ANSIBLE / rel).read_text(), Loader=_Loader)


def _rule(name: str) -> dict:
    rules = _load("host_vars/hermes.yml")["monitoring_contract"]["log_alert_rules"]
    matches = [r for r in rules if r["alert"] == name]
    assert len(matches) == 1, f"expected exactly one {name}"
    return matches[0]


# --- T072: gateway.log collection ---


def test_log_folder_is_a_host_folder_outside_the_agent_state() -> None:
    assert _load("roles/hermes/defaults/main.yml")["hermes_agent_log_dir"] == LOG_DIR
    compose = (ANSIBLE / "roles/hermes/templates/docker-compose.yml.j2").read_text()
    assert '"{{ hermes_agent_log_dir }}:/opt/data/logs"' in compose


def test_alloy_collects_exactly_gateway_log() -> None:
    file_logs = _load("host_vars/hermes.yml")["alloy_file_logs"]
    assert [f["path_glob"] for f in file_logs] == [GATEWAY_LOG]
    assert "*" not in GATEWAY_LOG


def test_playbook_creates_the_log_file_before_lxc_base() -> None:
    plays = _load("playbooks/hermes.yml")
    first = plays[0]
    assert "lxc_base" in [r if isinstance(r, str) else r["role"] for r in first["roles"]]
    pre = first.get("pre_tasks") or []
    paths = [str(t.get("ansible.builtin.file", {}).get("path", "")) for t in pre]
    assert any(LOG_DIR in p or "hermes_agent_log_dir" in p for p in paths), "log dir must be made in pre_tasks"
    assert any("gateway.log" in p for p in paths), "an empty gateway.log must exist for alloy's -r check"


# --- T022/T023: HermesPermanentApprovalGranted ---


def test_permanent_approval_rule() -> None:
    rule = _rule("HermesPermanentApprovalGranted")
    assert rule["enabled"] is True
    assert rule["kind"] == "event"
    assert rule["for"] == "0m"
    assert rule["severity"] == "warning"
    expr = rule["expr"]
    assert 'host="hermes"' in expr and 'source="file"' in expr
    assert f'filename="{GATEWAY_LOG}"' in expr
    assert '|= "via /approve (always)"' in expr
    assert "container=" not in expr, "approval lines are INFO and never reach container stdout"
    assert "{host=" in rule["summary"]


# --- T028/T030: HermesNtfyStreamDown ---


def test_ntfy_stream_down_rule() -> None:
    rule = _rule("HermesNtfyStreamDown")
    assert rule["enabled"] is True
    assert rule["kind"] == "event"
    assert rule["for"] == "10m"
    assert rule["severity"] == "warning"
    expr = rule["expr"]
    assert 'container="hermes_agent"' in expr
    assert '|= "Stream error"' in expr
    window = re.search(r"\[(\d+)m\]", expr)
    assert window and int(window.group(1)) >= 5, "T008 step 9 measured a 60 s error cadence; keep >= [5m]"
    assert "{host=" in rule["summary"]
