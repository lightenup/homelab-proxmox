"""Guard tests for the alerting path: who watches the watchers.

Root cause analysis 2026-10-27: Prometheus never scraped Alertmanager (or Grafana), no rule
watched Prometheus->Alertmanager or Alertmanager->receiver delivery, and nothing outside the
monitoring LXC noticed if the whole path died. These tests pin the fix:

1. every monitoring-stack container that serves /metrics has a Prometheus scrape job;
2. delivery failures on both hops raise an alert;
3. an always-firing Watchdog proves rules are evaluated and reach Alertmanager, is never
   routed to a receiver, and is checked from pve by a timer that pages Pushover directly.
"""

from __future__ import annotations

import re
from pathlib import Path

import jinja2
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
STACK = ANSIBLE / "roles/monitoring_stack"
HEARTBEAT = ANSIBLE / "roles/alerting_heartbeat"


def _read(rel: str | Path) -> str:
    return (ANSIBLE / rel).read_text() if not isinstance(rel, Path) else rel.read_text()


class _Loader(yaml.SafeLoader):
    """SafeLoader with YAML 1.1 bools re-pinned: some other test modules mutate
    yaml.SafeLoader's resolvers at import time (see test_log_pipeline.py), which turns
    `no_log: true` into the string 'true' for the rest of the session."""


_Loader.add_implicit_resolver(
    "tag:yaml.org,2002:bool",
    re.compile(r"^(?:yes|Yes|YES|no|No|NO|true|True|TRUE|false|False|FALSE|on|On|ON|off|Off|OFF)$"),
    list("yYnNtTfFoO"),
)


def _yaml(path: Path):
    return yaml.load(path.read_text(), Loader=_Loader)


# ---------------------------------------------------------------------------
# 1. Scrape coverage of the monitoring stack itself
# ---------------------------------------------------------------------------

# Compose services and how Prometheus reaches them. A new service must be added here, with a
# target or an explicit reason, so this list cannot silently fall behind the compose file.
STACK_SCRAPE_TARGETS = {
    "prometheus": "localhost:9090",
    "grafana": "grafana:3000",
    "telegraf": "telegraf:{{ telegraf_port }}",
    "alertmanager": "alertmanager:9093",
    "loki": "loki:3100",
    "blackbox-exporter": "blackbox-exporter:9115",
}


def _compose_services() -> set[str]:
    text = (STACK / "templates/docker-compose.yml.j2").read_text()
    services_block = text.split("\nservices:\n", 1)[1].split("\nvolumes:\n", 1)[0]
    return set(re.findall(r"^  ([a-z][a-z0-9_-]+):\s*$", services_block, re.M))


def test_every_stack_container_is_in_the_scrape_map():
    assert _compose_services() == set(STACK_SCRAPE_TARGETS), (
        "monitoring compose services changed: add the new one to STACK_SCRAPE_TARGETS "
        "and give it a Prometheus scrape job"
    )


def test_every_stack_container_has_a_scrape_job():
    prom = (STACK / "templates/prometheus.yml.j2").read_text()
    for service, target in STACK_SCRAPE_TARGETS.items():
        # Either `targets: ['x:1']` or a `- 'x:1'` list item under `targets:`.
        quoted = rf"['\"]?{re.escape(target)}['\"]?"
        assert re.search(rf"targets:\s*\[\s*{quoted}", prom) or re.search(
            rf"^\s*-\s*{quoted}\s*$", prom, re.M
        ), f"no scrape job targets {service} ({target})"


def test_alertmanager_and_grafana_jobs_are_not_exempt_from_service_down():
    prom = (STACK / "templates/prometheus.yml.j2").read_text()
    for job in ("alertmanager", "grafana"):
        start = prom.index(f"job_name: '{job}'")
        nxt = prom.find("job_name:", start + 1)
        block = prom[start : nxt if nxt != -1 else len(prom)]
        assert "no_down_alert" not in block, f"{job} must stay covered by ServiceDown"


# ---------------------------------------------------------------------------
# 2. Delivery-failure alerts and the Watchdog rule
# ---------------------------------------------------------------------------

RULES_FILE = STACK / "files/prometheus/alerts/alerting_path_alerts.yml"


def _rules() -> dict[str, dict]:
    groups = _yaml(RULES_FILE)["groups"]
    return {r["alert"]: r for g in groups for r in g["rules"]}


def test_watchdog_always_fires_and_is_never_a_page():
    w = _rules()["Watchdog"]
    assert w["expr"].strip() == "vector(1)"
    assert w["labels"]["severity"] == "none"
    assert "for" not in w or w["for"] in ("0m", "0s")


def test_delivery_failure_rules_cover_both_hops():
    rules = _rules()
    am = rules["AlertmanagerNotificationsFailing"]
    assert "alertmanager_notifications_failed_total" in am["expr"]
    assert "by (integration)" in am["expr"]
    prom = rules["PrometheusNotificationsFailing"]
    assert "prometheus_notifications_errors_total" in prom["expr"]
    assert "prometheus_notifications_dropped_total" in prom["expr"]
    for name in ("AlertmanagerNotificationsFailing", "PrometheusNotificationsFailing"):
        assert rules[name]["labels"]["severity"] == "warning"


def test_rules_file_is_deployed_and_reloads_prometheus():
    tasks = _yaml(STACK / "tasks/compose_stack.yml")
    task = next(
        t for t in tasks
        if isinstance(t.get("ansible.builtin.copy"), dict)
        and t["ansible.builtin.copy"].get("src") == "prometheus/alerts/alerting_path_alerts.yml"
    )
    assert task["ansible.builtin.copy"]["dest"].endswith("/alerts/alerting_path_alerts.yml")
    assert task.get("notify") == "Reload prometheus"


# ---------------------------------------------------------------------------
# 3. Alertmanager routing: Watchdog goes nowhere
# ---------------------------------------------------------------------------

_AM_VARS = {
    "smtp_server": "smtp.invalid", "smtp_port": 587, "smtp_from_address": "", "smtp_username": "u",
    "smtp_password": "p", "smtp_require_tls": True, "alert_email_recipient": "",
    "alertmanager_group_wait": "30s", "alertmanager_group_interval": "5m",
    "alertmanager_repeat_interval": "4h", "pushover_user_key": "STUB-user", "pushover_api_token": "STUB-token",
    "pushover_retry_interval": "60s", "pushover_expire_duration": "1h",
    "pushover_grafana_url": "https://grafana.example.invalid", "caddy_base_domain": "example.invalid",
    "ntfy_alertmanager_token": "STUB-ntfy",
}


def _render_am(**overrides) -> dict:
    env = jinja2.Environment(undefined=jinja2.StrictUndefined)
    env.filters["bool"] = lambda v: v if isinstance(v, bool) else str(v).lower() in ("1", "true", "yes", "on")
    text = env.from_string((STACK / "templates/alertmanager.yml.j2").read_text()).render(
        **{**_AM_VARS, **overrides}
    )
    return yaml.safe_load(text)


def test_watchdog_route_is_first_and_goes_to_a_receiver_with_no_integrations():
    for pushover in (True, False):
        cfg = _render_am(pushover_enabled=pushover, ntfy_enabled=pushover)
        first = cfg["route"]["routes"][0]
        assert first["matchers"] == ['alertname = "Watchdog"'], pushover
        assert "continue" not in first or first["continue"] is False
        receiver = next(r for r in cfg["receivers"] if r["name"] == first["receiver"])
        assert set(receiver) == {"name"}, f"Watchdog receiver must deliver nothing: {receiver}"


def test_pushover_routes_unchanged_after_watchdog():
    cfg = _render_am(pushover_enabled=True, ntfy_enabled=True)
    receivers = [r["receiver"] for r in cfg["route"]["routes"][1:]]
    assert receivers == ["pushover-critical", "pushover-warning", "pushover-info"]
    assert cfg["route"]["receiver"] == "pushover-warning"


# ---------------------------------------------------------------------------
# 4. The out-of-band heartbeat on pve
# ---------------------------------------------------------------------------


def test_heartbeat_role_runs_on_pve_only_outside_lab_and_is_tagged():
    play = _yaml(ANSIBLE / "playbooks/host_proxmox.yml")[0]
    role = next(r for r in play["roles"] if isinstance(r, dict) and r.get("role") == "alerting_heartbeat")
    assert "lab" in str(role.get("when", ""))
    assert "alerting_heartbeat" in role.get("tags", [])
    alloy = next(r for r in play["roles"] if isinstance(r, dict) and r.get("role") == "alloy")
    assert "alloy" in alloy.get("tags", [])


def test_heartbeat_checks_monitorings_alertmanager_and_pages_pushover():
    defaults = _yaml(HEARTBEAT / "defaults/main.yml")
    assert "hostvars['monitoring'].ansible_host" in defaults["alerting_heartbeat_alertmanager_url"]
    env = (HEARTBEAT / "templates/alerting-heartbeat.env.j2").read_text()
    for var in ("AM_URL", "PUSHOVER_USER_KEY", "PUSHOVER_API_TOKEN", "FAIL_THRESHOLD", "REPEAT_SECONDS"):
        assert f"{var}=" in env


def test_heartbeat_reads_pushover_from_the_monitoring_vault_file_namespaced():
    # `monitoring` is a host, not a group, so group_vars/monitoring/ is never loaded
    # automatically (monitoring.yml include_vars it explicitly) and
    # hostvars['monitoring'].pushover_user_key is undefined from pve. The role loads the vault
    # file itself, under a name, so none of monitoring's other vars leak into the pve play.
    tasks = _yaml(HEARTBEAT / "tasks/main.yml")
    inc = next(t for t in tasks if "ansible.builtin.include_vars" in t)
    args = inc["ansible.builtin.include_vars"]
    assert args["file"] == "{{ alerting_heartbeat_monitoring_vault_file }}"
    vault_file = _yaml(HEARTBEAT / "defaults/main.yml")["alerting_heartbeat_monitoring_vault_file"]
    # role_path is ansible/roles/alerting_heartbeat, so ../../group_vars is ansible/group_vars.
    assert vault_file == "{{ role_path }}/../../group_vars/monitoring/vault.yml"
    assert (ANSIBLE / "group_vars/monitoring/vault.yml").exists()
    assert args["name"] == "alerting_heartbeat_monitoring_vault"
    assert inc.get("no_log") is True
    defaults = (HEARTBEAT / "defaults/main.yml").read_text()
    assert "alerting_heartbeat_monitoring_vault.pushover_user_key" in defaults
    assert "alerting_heartbeat_monitoring_vault.pushover_api_token" in defaults
    assert "hostvars['monitoring'].pushover" not in defaults


def test_heartbeat_secrets_file_is_root_only_and_not_logged():
    tasks = _yaml(HEARTBEAT / "tasks/main.yml")
    t = next(
        t for t in tasks
        if isinstance(t.get("ansible.builtin.template"), dict)
        and t["ansible.builtin.template"]["src"] == "alerting-heartbeat.env.j2"
    )
    assert t["ansible.builtin.template"]["mode"] == "0600"
    assert t["ansible.builtin.template"]["owner"] == "root"
    assert t.get("no_log") is True


def test_heartbeat_timer_runs_every_five_minutes_and_after_boot():
    timer = (HEARTBEAT / "templates/alerting-heartbeat.timer.j2").read_text()
    assert "OnBootSec=" in timer
    assert "OnUnitActiveSec={{ alerting_heartbeat_interval }}" in timer
    assert _yaml(HEARTBEAT / "defaults/main.yml")["alerting_heartbeat_interval"] == "5min"
    service = (HEARTBEAT / "templates/alerting-heartbeat.service.j2").read_text()
    assert "EnvironmentFile=/etc/default/alerting-heartbeat" in service
    assert "Type=oneshot" in service
