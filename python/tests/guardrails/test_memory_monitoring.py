"""Guard test: the memory server's monitoring contract (spec 097 T053, T054; research R-015).

What it pins, in ansible/host_vars/memory.yml `monitoring_contract`:

- a scrape target for the Hindsight API's /metrics on memory_api_port. The monitoring stack
  builds the address from the host's ansible_host, so the inventory must put memory at
  memory_ip;
- a blackbox http_2xx probe of https://memory-api.<domain>/health, the route every client uses;
- MemoryDown (probe failing 5 minutes, critical), MemoryRetainFailures (failed async retains for
  30 minutes) and MemoryWritesStalled (no retains in 12 hours while the gateway serves chats),
  built on the metric names read from Hindsight 1.1.0 (R-015) and from the gateway's own rules.
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
SEVERITIES = {"critical", "warning", "info"}


class _Loader(yaml.SafeLoader):
    """SafeLoader that accepts Ansible's !unsafe tag (alert text)."""


_Loader.add_constructor("!unsafe", lambda loader, node: loader.construct_scalar(node))


def _load(rel: str):
    return yaml.load((ANSIBLE / rel).read_text(), Loader=_Loader)


def _contract() -> dict:
    return _load("host_vars/memory.yml")["monitoring_contract"]


def _alert(name: str) -> dict:
    matches = [r for r in _contract()["alert_rules"] if r["alert"] == name]
    assert len(matches) == 1, f"expected exactly one {name}"
    return matches[0]


def _compact(expr: str) -> str:
    return re.sub(r"\s+", " ", expr).strip()


def test_contract_is_enabled() -> None:
    assert str(_contract()["enabled"]).lower() == "true"


def test_scrape_target_is_the_api_metrics_endpoint() -> None:
    targets = _contract()["scrape_targets"]
    assert len(targets) == 1
    target = targets[0]
    assert target["job_name"] == "memory"
    assert target["port"] == "{{ memory_api_port }}"
    assert target["path"] == "/metrics"
    assert "bearer_token" not in target, "Hindsight's /metrics needs no key"


def test_scrape_address_is_memory_ip() -> None:
    # prometheus.yml.j2 scrapes '{{ hostvars[host].ansible_host }}:{{ target.port }}'.
    services = _load("group_vars/services/vars.yml")
    hosts = _load("inventories/prod/hosts.yml")
    memory_host = None
    stack = [hosts]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            if "memory" in node and isinstance(node["memory"], dict) and "ansible_host" in node["memory"]:
                memory_host = node["memory"]
                break
            stack.extend(node.values())
    assert memory_host is not None, "memory missing from the prod inventory"
    assert str(memory_host["ansible_host"]) == services["memory_ip"]
    assert int(services["memory_api_port"]) == 8888


def test_liveness_probe_uses_the_client_route() -> None:
    targets = _contract()["liveness_targets"]
    assert targets == [
        {
            "job_name": "memory-health",
            "url": "https://memory-api.{{ caddy_base_domain }}/health",
            "module": "http_2xx",
        }
    ]


def test_every_alert_is_complete() -> None:
    rules = _contract()["alert_rules"]
    assert {r["alert"] for r in rules} == {"MemoryDown", "MemoryRetainFailures", "MemoryWritesStalled"}
    for rule in rules:
        for field in ("alert", "expr", "for", "severity", "summary", "description"):
            assert rule.get(field), f"{rule['alert']}: missing {field!r}"
        assert rule["severity"] in SEVERITIES


def test_memory_down() -> None:
    rule = _alert("MemoryDown")
    assert _compact(rule["expr"]) == 'probe_success{job="memory-health"} == 0'
    assert rule["for"] == "5m"
    assert rule["severity"] == "critical"


def test_memory_retain_failures() -> None:
    rule = _alert("MemoryRetainFailures")
    expr = _compact(rule["expr"])
    # Backlog gauge, verified against Hindsight 1.1.0 (R-015): failed = stranded operations.
    assert "hindsight_async_operations{" in expr
    assert 'job="memory"' in expr
    assert 'status="failed"' in expr
    assert re.search(r'operation_type=~"[^"]*retain[^"]*"', expr)
    assert expr.endswith("> 0")
    assert rule["for"] == "30m"
    assert "Runbook: failed retains" in rule["description"]
    assert "quickstart.md" in rule["description"]


def test_memory_writes_stalled() -> None:
    rule = _alert("MemoryWritesStalled")
    expr = _compact(rule["expr"])
    assert 'hindsight_operation_operations_total{job="memory", operation="retain", success="true"}[12h]' in expr
    # An absent counter (no retain since a restart) must count as zero, or the rule never fires.
    assert "or on() vector(0)) == 0" in expr
    # increase() reads 0 until Prometheus holds a sample from before the window, so on a fresh
    # scrape (first deploy, a new Prometheus, a renamed job) the rule fired at once although
    # retains were happening (2026-10-31, T055). It only judges with ~11 of 12 hours of data.
    assert 'and on() count_over_time(up{job="memory"}[12h]) > 1300' in expr
    assert "and on()" in expr
    assert re.search(r"litellm_deployment_success_responses_total\{[^}]*\}\[12h\]\)\) > 20$", expr)
    # Chats only: the canary, health checks, scout probes and memory's own embed/rerank calls
    # are gateway traffic that is not a conversation.
    alias_filter = re.search(r'api_key_alias!~"([^"]+)"', expr)
    assert alias_filter
    assert set(alias_filter.group(1).split("|")) >= {
        "canary",
        "litellm-internal-health-check",
        "memory",
        "scout_probe",
    }
    assert rule["severity"] == "warning"


def test_gateway_metric_name_is_the_one_the_gateway_rules_use() -> None:
    llm_router = (ANSIBLE / "host_vars/llm-router.yml").read_text()
    assert "litellm_deployment_success_responses_total{api_key_alias" in llm_router
    services = _load("group_vars/services/vars.yml")
    aliases = {c["alias"] for c in services["llm_router_clients"]}
    assert {"memory", "scout_probe", "canary"} <= aliases
