"""Guard tests for Alloy's Docker read-position key (RCA 2026-10-27).

loki.source.docker saves each container's read position under the container id *and* the
full target label set (alloy v1.21.2 tailer.go: positions.Get(CursorKey(id), labels.String())).
discovery.docker puts the container's bridge IP and port in that set (__address__,
__meta_docker_network_ip, __meta_docker_port_*). When a container came back with another IP,
the key changed, the old position was deleted (tailer.stop) and the new tailer read the whole
log from the start: 45,008 duplicate lines rejected by Loki as too_far_behind on 2026-10-26,
and two false alarms. Reproduced 2026-10-27 by swapping two test containers' IPs.

The fix drops the volatile labels in discovery.relabel "docker", so the key depends only on
the container. Upstream grafana/alloy#7036 (stop/start deletes the position) is a second
trigger this cannot fix; the alert changes below keep its replays from paging.
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
ALLOY_CONFIG = ROOT / "ansible/roles/alloy/templates/config.alloy.j2"
PIPELINE_ALERTS = ROOT / "ansible/roles/monitoring_stack/templates/log_pipeline_alerts.yml.j2"


def _relabel_docker_block() -> str:
    text = ALLOY_CONFIG.read_text()
    start = text.index('discovery.relabel "docker" {')
    depth, i = 0, start
    while True:
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
        i += 1


def _labeldrop_regex() -> re.Pattern:
    block = _relabel_docker_block()
    rules = re.findall(r"rule\s*\{(.*?)\}", block, re.S)
    drops = [r for r in rules if re.search(r'action\s*=\s*"labeldrop"', r)]
    assert len(drops) == 1, "discovery.relabel \"docker\" needs exactly one labeldrop rule"
    pattern = re.search(r'regex\s*=\s*"((?:[^"\\]|\\.)*)"', drops[0]).group(1)
    return re.compile(rf"^(?:{pattern.encode().decode('unicode_escape')})$")  # relabel regexes are anchored


# Two target label sets for the same container, as discovery.docker produced them before and
# after the 2026-10-27 IP swap (trimmed to the labels that exist on our hosts).
_BEFORE = {
    "__address__": "172.18.0.8:80",
    "__meta_docker_container_id": "e265db1c6285",
    "__meta_docker_container_name": "/rca-a",
    "__meta_docker_container_network_mode": "monitoring_default",
    "__meta_docker_container_label_com_docker_compose_service": "rca-a",
    "__meta_docker_network_id": "9f2c",
    "__meta_docker_network_name": "monitoring_default",
    "__meta_docker_network_ip": "172.18.0.8",
    "__meta_docker_network_scope": "local",
    "__meta_docker_port_private": "80",
    "container": "rca-a",
    "source": "docker",
}
_AFTER = {**_BEFORE, "__address__": "172.18.0.9:80", "__meta_docker_network_ip": "172.18.0.9"}
# A second target for the same container (another published port): ReconcileWithDedup keeps
# one tailer per container id, so whichever target wins must give the same key.
_OTHER_PORT = {**_BEFORE, "__address__": "172.18.0.8:9273", "__meta_docker_port_private": "9273",
               "__meta_docker_port_public": "9273", "__meta_docker_port_public_ip": "0.0.0.0"}


def _after_relabel(labels: dict) -> dict:
    drop = _labeldrop_regex()
    return {k: v for k, v in labels.items() if not drop.match(k)}


def test_key_survives_an_ip_change():
    assert _after_relabel(_BEFORE) == _after_relabel(_AFTER)


def test_key_is_the_same_for_every_target_of_one_container():
    assert _after_relabel(_BEFORE) == _after_relabel(_OTHER_PORT)


def test_container_identity_and_stream_labels_are_kept():
    kept = _after_relabel(_BEFORE)
    for label in ("__meta_docker_container_id", "__meta_docker_container_name", "container", "source"):
        assert label in kept


def test_labeldrop_runs_after_the_container_label_is_derived():
    block = _relabel_docker_block()
    assert block.index("__meta_docker_container_name") < block.index('"labeldrop"')


def test_config_explains_the_upstream_issue():
    block = _relabel_docker_block()
    assert "7036" in block


# --- Alert side: replays (duplicates) inform, they do not page as connectivity loss --------

def _rules() -> dict[str, dict]:
    text = re.sub(r"\{%.*?%\}|\{#.*?#\}", "", PIPELINE_ALERTS.read_text(), flags=re.S)
    text = text.replace("{{ log_rules_expected_count }}", "5")
    groups = yaml.safe_load(text)["groups"]
    return {r["alert"]: r for g in groups for r in g["rules"]}


def test_lines_discarded_excludes_replay_rejections():
    expr = _rules()["LogLinesDiscarded"]["expr"]
    assert 'reason!="too_far_behind"' in expr.replace(" ", "")


def test_replay_rejections_have_their_own_informational_alert():
    r = _rules()["LogReplayRejected"]
    assert 'reason="too_far_behind"' in r["expr"].replace(" ", "")
    assert r["labels"]["severity"] == "info"
    assert "7036" in r["annotations"]["description"]


def test_sustained_discards_still_include_every_reason():
    expr = _rules()["LogLinesDiscardedSustained"]["expr"]
    assert "too_far_behind" not in expr  # a 1h too_far_behind stream is clock skew, not a replay


def test_collector_dropping_ignores_drops_explained_by_replay_rejections():
    r = _rules()["LogCollectorDropping"]
    expr = " ".join(r["expr"].split())
    assert "unless on()" in expr
    assert 'loki_discarded_samples_total{reason="too_far_behind"}' in expr
    assert "should not happen" not in r["annotations"]["description"]
