"""Guard test: the harness gate ran against today's memory configuration (spec 097 T037, FR-021).

FR-021: no PROD promotion that changes memory without the spike harness passing against the
production-rendered configuration (research R-017). This test computes a fingerprint over the
pins and files that decide memory behaviour and fails unless a committed
docs/backlog/097-spike/results/*-prod-render/fingerprint.txt carries the same value.

docs/backlog/097-spike/render-prod.sh writes that file with compute_fingerprint() below, so the
test and the harness cannot disagree on what is hashed.

Fingerprinted: the Hindsight, Postgres, plugin and agent pins (the plugin's behaviour depends on
the agent, G2), the wheel pins and the plugin tarball hash, and the server env, the plugin config,
the policy module, the shim and the Open WebUI filter (once it exists). Not fingerprinted: the
Claude Code hook. It lives in dotfiles, and the harness replays its turn format without running
it, so hashing it would force re-runs that test nothing (I2). The turn-format contract and
quickstart § 6 cover it.

Deliberately stdlib + PyYAML only, so render-prod.sh can import it without pytest.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
RESULTS = ROOT / "docs" / "backlog" / "097-spike" / "results"

PINS = ("hindsight_version", "memory_postgres_version", "hermes_hindsight_plugin_version", "hermes_agent_version")
FILES = (
    "ansible/roles/memory/templates/server.env.j2",
    "ansible/roles/hermes/templates/hindsight-config.json.j2",
    "python/src/homelab_proxmox_orchestrator/memory_access.py",
    "ansible/roles/memory/files/hindsight_ext/shim.py",
)
OPTIONAL_FILES = ("ansible/roles/hermes/files/open_webui/memory_filter.py",)


def fingerprint_inputs(root: Path = ROOT) -> list[str]:
    """One line per input, in a fixed order: `pin <name>=<value>` or `file <path> <sha256>`."""
    services = yaml.safe_load((root / "ansible/group_vars/services/vars.yml").read_text())
    hermes = yaml.safe_load((root / "ansible/roles/hermes/defaults/main.yml").read_text())
    lines = [f"pin {name}={services[name]}" for name in PINS]
    lines.append(f"pin hermes_hindsight_plugin_sha256={hermes['hermes_hindsight_plugin_sha256']}")
    for wheel in hermes["hermes_hindsight_plugin_wheels"]:
        lines.append(f"pin wheel {wheel['name']}{wheel['version']} {wheel['sha256']}")
    for rel in FILES + tuple(f for f in OPTIONAL_FILES if (root / f).exists()):
        lines.append(f"file {rel} {hashlib.sha256((root / rel).read_bytes()).hexdigest()}")
    return lines


def compute_fingerprint(root: Path = ROOT) -> str:
    return hashlib.sha256("\n".join(fingerprint_inputs(root)).encode()).hexdigest()


def fingerprint_file(root: Path = ROOT) -> str:
    """The content render-prod.sh writes: the fingerprint, then the inputs for a reviewer."""
    return "\n".join([compute_fingerprint(root), *fingerprint_inputs(root)]) + "\n"


def _recorded() -> dict[str, str]:
    return {
        path.read_text().splitlines()[0].strip(): str(path.parent.name)
        for path in sorted(RESULTS.glob("*-prod-render/fingerprint.txt"))
    }


def test_inputs_cover_every_pin_and_file():
    lines = fingerprint_inputs()
    assert sum(line.startswith("pin wheel ") for line in lines) == 3
    for rel in FILES:
        assert any(line.startswith(f"file {rel} ") for line in lines), rel


def test_harness_gate_ran_against_this_configuration():
    current = compute_fingerprint()
    recorded = _recorded()
    assert current in recorded, (
        "Memory configuration changed since the last harness gate run (FR-021). Run "
        "docs/backlog/097-spike/render-prod.sh and run.sh prod-render (quickstart § 1), and commit "
        f"results/<YYYY-MM-DD>-prod-render/ with its fingerprint.txt. Current: {current}; "
        f"recorded: {sorted(recorded.values()) or 'none'}"
    )
