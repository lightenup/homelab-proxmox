"""LAN isolation of the vmbr99 lab bridge (067, contracts/lab-network.md).

The nftables table is host configuration owned by root Ansible. These tests pin its shape so a
rewrite cannot quietly open a path from a lab copy to the production LAN.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TEMPLATE = ROOT / "ansible/playbooks/templates/lab-isolation.nft.j2"
PLAYBOOK = ROOT / "ansible/playbooks/lab_setup.yml"


def _chain(text: str, name: str) -> str:
    match = re.search(rf"chain {name} \{{(.*?)\n  \}}", text, re.DOTALL)
    assert match, f"chain {name} missing"
    return match.group(1)


def _lines(chain: str) -> list[str]:
    return [" ".join(line.split()) for line in chain.splitlines() if line.strip().startswith(("iifname", "ip "))]


def test_table_defined():
    assert "table inet lab_isolation {" in TEMPLATE.read_text()


def test_lan_private_set():
    text = TEMPLATE.read_text()
    match = re.search(r"set lan_private \{(.*?)\}\s*\}", text, re.DOTALL) or re.search(
        r"set lan_private \{.*?elements = \{([^}]*)\}", text, re.DOTALL
    )
    assert match
    body = match.group(0)
    for cidr in ("10.0.0.0/8", "100.64.0.0/10", "172.16.0.0/12", "192.168.0.0/16"):
        assert cidr in body


def test_forward_chain_order():
    rules = _lines(_chain(TEMPLATE.read_text(), "forward"))
    est = 'iifname "vmbr99" ct state established,related accept'
    lab = 'iifname "vmbr99" ip daddr 10.99.0.0/24 accept'
    drop = 'iifname "vmbr99" ip daddr @lan_private drop'
    for rule in (est, lab, drop):
        assert rule in rules, rule
    assert rules.index(est) < rules.index(lab) < rules.index(drop)


def test_exceptions_are_source_scoped_and_precede_the_drop():
    rules = _lines(_chain(TEMPLATE.read_text(), "forward"))
    drop_at = rules.index('iifname "vmbr99" ip daddr @lan_private drop')
    exceptions = [r for r in rules if r.startswith("ip saddr")]
    assert exceptions, "lab-rig exceptions (T002) missing"
    for rule in exceptions:
        assert rule.startswith("ip saddr { 10.99.0.10, 10.99.0.11 }"), rule
        assert " tcp dport " in rule and rule.endswith(" accept"), rule
        assert rules.index(rule) < drop_at
    # No exception may name the lab-copy range.
    assert not re.search(r"10\.99\.0\.(2\d\d)", "\n".join(exceptions))


def test_input_chain_drops_everything_else():
    rules = _lines(_chain(TEMPLATE.read_text(), "input"))
    assert rules == [
        'iifname "vmbr99" ct state established,related accept',
        'iifname "vmbr99" drop',
    ]


def test_bridge_stanza_loads_and_removes_the_table():
    text = PLAYBOOK.read_text()
    assert "post-up   nft -f /etc/nftables.d/lab-isolation.nft" in text
    assert "post-down nft delete table inet lab_isolation" in text
    assert "lab-network" in text
