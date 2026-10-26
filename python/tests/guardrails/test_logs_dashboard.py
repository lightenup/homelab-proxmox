"""Guard tests for the provisioned Loki "Logs" dashboard (day-to-day saved queries).

The dashboard is the git-backed home for everyday LogQL: grafana.db is not backed up (the
monitoring LXC is rebuildable, spec 092), so queries kept only in Grafana's UI are lost on
rebuild. These tests pin its shape and keep its selectors in step with the sources they read
(Alloy's file paths, the Hermes alert rules), so a renamed path or label breaks CI instead of
leaving a silently empty panel.
"""

from __future__ import annotations

import json
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
DASHBOARD = ANSIBLE / "roles/monitoring_stack/files/grafana/dashboards/logs.json"
LOKI_DS = {"type": "loki", "uid": "loki"}

REQUIRED_ROWS = [
    "Estate errors",
    "Service logs",
    "Hermes / ntfy",
    "Security / access",
    "Backups and jobs",
    "Kernel, OOM and unit failures",
]


class _Loader(yaml.SafeLoader):
    """SafeLoader that accepts Ansible's !unsafe and re-pins bool resolution (same cross-test
    workaround as test_log_pipeline.py)."""


_Loader.add_constructor("!unsafe", lambda loader, node: loader.construct_scalar(node))
_Loader.add_implicit_resolver(
    "tag:yaml.org,2002:bool",
    re.compile(r"^(?:yes|Yes|YES|no|No|NO|true|True|TRUE|false|False|FALSE|on|On|ON|off|Off|OFF)$"),
    list("yYnNtTfFoO"),
)


def _load_yaml(rel: str):
    return yaml.load((ANSIBLE / rel).read_text(), Loader=_Loader)


def _dashboard() -> dict:
    return json.loads(DASHBOARD.read_text())


def _panels() -> list[dict]:
    return [p for p in _dashboard()["panels"] if p.get("type") != "row"]


def _exprs() -> list[str]:
    return [t["expr"] for p in _panels() for t in p.get("targets", [])]


def _hermes_rule_expr(name: str) -> str:
    rules = _load_yaml("host_vars/hermes.yml")["monitoring_contract"]["log_alert_rules"]
    return next(r["expr"] for r in rules if r["alert"] == name)


def test_dashboard_parses_with_stable_identity():
    d = _dashboard()
    assert d["uid"] == "logs"
    assert d["title"] == "Logs"
    # Provisioned dashboards must not carry a numeric id (Grafana assigns it).
    assert d.get("id") is None


def test_required_rows_present_in_order():
    rows = [p["title"] for p in _dashboard()["panels"] if p.get("type") == "row"]
    assert rows == REQUIRED_ROWS


def test_panel_ids_unique_and_laid_out():
    panels = _dashboard()["panels"]
    ids = [p["id"] for p in panels]
    assert len(ids) == len(set(ids))
    for p in panels:
        assert {"x", "y", "w", "h"} <= set(p["gridPos"]), p["title"]


def test_every_query_panel_uses_the_provisioned_loki_datasource():
    datasource_file = ANSIBLE / "roles/monitoring_stack/files/grafana/provisioning/datasources/loki.yml"
    assert "uid: loki" in datasource_file.read_text()
    for p in _panels():
        assert p.get("targets"), f"panel without a query: {p['title']}"
        assert p["datasource"] == LOKI_DS, p["title"]
        for t in p["targets"]:
            assert t["datasource"] == LOKI_DS, p["title"]
            assert t["expr"].strip(), p["title"]


def test_every_query_is_scoped_to_prod():
    # An unscoped selector scans every stream; env="prod" keeps queries cheap and matches the
    # label every Alloy stream carries (alloy config.alloy.j2 static_labels).
    for expr in _exprs():
        assert 'env="prod"' in expr, expr


def test_hermes_audit_panel_reads_the_file_alloy_collects():
    paths = [f["path_glob"] for f in _load_yaml("host_vars/hermes.yml")["alloy_file_logs"]]
    assert len(paths) == 1
    audit = [e for e in _exprs() if "via /approve" in e]
    assert audit, "no Hermes approval audit query"
    for expr in audit:
        assert f'filename="{paths[0]}"' in expr


def test_hermes_stream_error_panels_match_the_alert_selector():
    # Same selector as HermesNtfyStreamDown and the T061 (SC-004) seven-day check.
    rule = _hermes_rule_expr("HermesNtfyStreamDown")
    selector = '{env="prod", host="hermes", container="hermes_agent"} |= "Stream error"'
    assert selector in rule
    assert sum(selector in e for e in _exprs()) >= 2  # trend + 7-day total


def test_seven_day_stream_error_stat_is_pinned_to_seven_days():
    stat = next(p for p in _panels() if "7 days" in p["title"] and p["type"] == "stat")
    assert stat["timeFrom"] == "7d"
    assert "[7d]" in stat["targets"][0]["expr"]
    assert stat["fieldConfig"]["defaults"]["noValue"] == "0"


def test_backup_unit_queries_exclude_debian_dpkg_backup_unit():
    # `-backup\.service:` also matches Debian's dpkg-db-backup.service on every LXC (seen live:
    # three a day per host), which is not one of ours.
    backup = [e for e in _exprs() if r"-backup\.service" in e]
    assert backup
    for expr in backup:
        assert '!= "dpkg-db-backup"' in expr


def test_dashboard_is_deployed_by_the_role():
    tasks = (ANSIBLE / "roles/monitoring_stack/tasks/grafana_provision.yml").read_text()
    assert "src: grafana/dashboards/logs.json" in tasks
    assert 'dest: "{{ grafana_dashboards_path }}/logs.json"' in tasks
