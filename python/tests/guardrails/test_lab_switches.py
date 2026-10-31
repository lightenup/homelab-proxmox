"""Lab switches (067, R-011): a lab copy holds no credential that could reach the internet.

Every secret-like variable a role template renders is classified. A new one fails this test until
someone decides what it is; an `internet` one may only appear in a template listed in GATED, each
with the reason it cannot leak into a lab copy.
"""

from __future__ import annotations

import re
from pathlib import Path

import jinja2
import yaml

ROOT = Path(__file__).resolve().parents[3]
ANSIBLE = ROOT / "ansible"
SECRET_NAME = re.compile(r"\b[a-z0-9_]*(?:_token|_key|_secret|_password|_api_[a-z_]+)\b")

CLASSIFICATION = {
    # reach a third party over the internet
    "domeneshop_api_token": "internet", "domeneshop_api_secret": "internet",
    "pushover_user_key": "internet", "pushover_api_token": "internet",
    "alerting_heartbeat_pushover_user_key": "internet", "alerting_heartbeat_pushover_api_token": "internet",
    "smtp_password": "internet",
    # reach another service on the production LAN
    "ntfy_alertmanager_token": "lan", "ntfy_owner_token": "lan", "ntfy_hermes_token": "lan",
    "ntfy_hermes_lab_token": "lan", "proxmox_backup_ntfy_token": "lan",
    "snmp_priv_password": "lan", "snmp_auth_password": "lan",
    # stay inside the service, or are not secrets at all
    "nextcloud_redis_password": "internal", "immich_db_password": "internal",
    "nextcloud_db_root_password": "internal", "nextcloud_db_password": "internal",
    "litellm_db_password": "internal", "litellm_master_key": "internal",
    "llm_router_client_hermes_key": "internal", "llm_router_client_hermes_agent_key": "internal",
    "llm_router_canary_key": "internal", "hermes_searxng_secret": "internal",
    "hermes_agent_api_server_key": "internal", "hermes_webui_secret_key": "internal",
    "hermes_agent_api_base_url": "internal", "eurooffice_jwt_secret": "internal",
    "nextcloud_serverinfo_token": "internal", "nextcloud_admin_password": "internal",
    "grafana_admin_password": "internal", "jellyfin_api_key": "internal", "bearer_token": "internal",
    "proxmox_backup_age_public_key": "internal", "financial_scenario_api_image": "internal",
    "market_model_api_port": "internal",
    # 097 R-011: the memory store's database and its gateway key (embed and rerank only).
    # memory_admin_key and memory_client_open_webui_key are used only in tasks and through
    # lookup('vars', ...), never literally in a template, so they are not classified here.
    "memory_db_password": "internal", "llm_router_client_memory_key": "internal",
    "memory_api_image": "internal", "memory_api_port": "internal", "memory_api_url": "internal",
    # 097 R-003: the agent's memory key (readwrite, no whole-bank operation) and the API URL.
    "memory_client_hermes_key": "internal", "hermes_memory_api_url": "internal",
}

# internet key -> {template (relative to ansible/roles): why a lab copy never renders it}
GATED = {
    "domeneshop_api_token": {"reverse_proxy/templates/domeneshop.env.j2": "task skipped when lab"},
    "domeneshop_api_secret": {"reverse_proxy/templates/domeneshop.env.j2": "task skipped when lab"},
    "pushover_user_key": {"monitoring_stack/templates/alertmanager.yml.j2": "lab renders only the null receiver"},
    "pushover_api_token": {"monitoring_stack/templates/alertmanager.yml.j2": "lab renders only the null receiver"},
    "smtp_password": {
        "monitoring_stack/templates/alertmanager.yml.j2": "lab omits the global block",
        "proxmox_backup/templates/sasl_passwd.j2": "pve-only role",
    },
    "alerting_heartbeat_pushover_user_key": {"alerting_heartbeat/templates/alerting-heartbeat.env.j2": "pve-only role, not run in lab"},
    "alerting_heartbeat_pushover_api_token": {"alerting_heartbeat/templates/alerting-heartbeat.env.j2": "pve-only role, not run in lab"},
}


def _references() -> dict[str, set[str]]:
    refs: dict[str, set[str]] = {}
    for path in (ANSIBLE / "roles").rglob("templates/**/*.j2"):
        text = path.read_text(errors="ignore")
        for expr in re.findall(r"\{\{(.*?)\}\}", text, re.S):
            for name in SECRET_NAME.findall(expr):
                refs.setdefault(name, set()).add(str(path.relative_to(ANSIBLE / "roles")))
    return refs


def test_every_secret_like_variable_is_classified():
    unknown = sorted(set(_references()) - set(CLASSIFICATION))
    assert not unknown, f"classify these in CLASSIFICATION (internet|lan|internal): {unknown}"


def test_no_stale_classifications():
    stale = sorted(set(CLASSIFICATION) - set(_references()))
    assert not stale, f"no template references these any more: {stale}"


def test_internet_credentials_only_appear_in_gated_templates():
    refs = _references()
    for name, kind in CLASSIFICATION.items():
        if kind != "internet":
            continue
        extra = refs[name] - set(GATED[name])
        assert not extra, f"{name} (internet) is rendered by ungated templates: {sorted(extra)}"


def test_reverse_proxy_renders_local_certs_and_no_acme_dns_in_lab():
    template = (ANSIBLE / "roles/reverse_proxy/templates/Caddyfile.j2").read_text()
    ctx = {"caddy_acme_dns_provider": "x", "caddy_metrics_enabled": False, "caddy_conf_dir": "/c", "caddy_health_port": 1}
    lab = jinja2.Template(template).render(deploy_environment="lab", **ctx)
    prod = jinja2.Template(template).render(deploy_environment="prod", **ctx)
    assert "local_certs" in lab and "acme_dns" not in lab
    assert "acme_dns" in prod and "local_certs" not in prod
    tasks = yaml.safe_load((ANSIBLE / "roles/reverse_proxy/tasks/main.yml").read_text())
    for task in tasks:
        if "domeneshop" in str(task.get("ansible.builtin.template", "")):
            assert "lab" in str(task.get("when")), task["name"]


def test_llm_router_has_no_tailscale_service_and_no_provider_keys_in_lab():
    compose = (ANSIBLE / "roles/llm_router/templates/docker-compose.yml.j2").read_text()
    assert not re.search(r"^  tailscale:", compose, re.M)
    assert "'' if (deploy_environment | default('prod')) == 'lab'" in compose


def _alertmanager(env: str) -> dict:
    environment = jinja2.Environment()
    environment.filters["bool"] = lambda v: str(v).lower() in ("true", "1", "yes")
    template = (ANSIBLE / "roles/monitoring_stack/templates/alertmanager.yml.j2").read_text()
    return yaml.safe_load(environment.from_string(template).render(
        deploy_environment=env, smtp_server="s", smtp_port=25, smtp_from_address="", smtp_username="u",
        smtp_password="p", smtp_require_tls=False, pushover_enabled=True, alertmanager_group_wait="30s",
        alertmanager_group_interval="5m", alertmanager_repeat_interval="4h", pushover_user_key="k",
        pushover_api_token="t", pushover_retry_interval=60, pushover_expire_duration=3600,
        pushover_grafana_url="u", ntfy_enabled=True, caddy_base_domain="d", ntfy_alertmanager_token="x",
        alert_email_recipient=""))


def test_alertmanager_in_lab_has_only_the_null_receiver():
    lab = _alertmanager("lab")
    assert [r["name"] for r in lab["receivers"]] == ["null"]
    assert lab["route"]["receiver"] == "null"
    assert {r["receiver"] for r in lab["route"]["routes"]} == {"null"}
    assert "global" not in lab
    assert len(_alertmanager("prod")["receivers"]) == 4


def test_service_backup_is_skipped_in_lab_by_the_six_playbooks_that_run_it():
    names = ("immich", "hermes", "financial-scenario", "jellyfin", "homeassistant", "nextcloud")
    for name in names:
        plays = yaml.safe_load((ANSIBLE / f"playbooks/{name}.yml").read_text())
        role = next(r for play in plays for r in play.get("roles", [])
                    if isinstance(r, dict) and r.get("role") == "service_backup")
        assert "deploy_environment" in role["when"] and "'lab'" in role["when"], name
