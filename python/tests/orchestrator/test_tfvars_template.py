from __future__ import annotations

# Evidence-artifact contract tests for tfvars template separation.
# Validates sentinel detection, evidence format, drift results, and change warnings
# without requiring live Proxmox infrastructure, bash execution, or secrets.
#
# Pattern: inline string fixtures (same approach as test_tfvars_mountpoints.py).
# Tests: 8 total per plan.md Step 10 / data-model.md / spec FRs.

import json
import re
from pathlib import Path

# ---------------------------------------------------------------------------
# Repository root resolution
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[3]
PROD_TFVARS_EXAMPLE = REPO_ROOT / "terraform" / "environments" / "prod.tfvars.example"
PROD_TFVARS_TEMPLATE = REPO_ROOT / "terraform" / "environments" / "prod.tfvars.template"

# ---------------------------------------------------------------------------
# Inline fixtures: sample content strings (no live infrastructure)
# ---------------------------------------------------------------------------

_CI_TEMPLATE_CONTENT = """\
# CI template — real non-secret values. Do not copy for local use; see prod.tfvars.example instead.

proxmox_api_url = "https://192.168.1.112:8006/api2/json"

# Token-based auth — secret injected at runtime via PROXMOX_API_TOKEN_SECRET
proxmox_api_token_id     = "terraform@pve!terraform-token"
proxmox_api_token_secret = "__INJECT_TOKEN_SECRET__"

proxmox_node    = "pve"
network_gateway = "192.168.1.1"
"""

_RENDERED_CONTENT = """\
# CI template — real non-secret values. Do not copy for local use; see prod.tfvars.example instead.

proxmox_api_url = "https://192.168.1.112:8006/api2/json"

# Token-based auth — secret injected at runtime via PROXMOX_API_TOKEN_SECRET
# __INJECT_TOKEN_SECRET__ is a placeholder replaced by the provisioner
proxmox_api_token_id     = "terraform@pve!terraform-token"
proxmox_api_token_secret = "actual-secret-value"

proxmox_node    = "pve"
network_gateway = "192.168.1.1"
"""

_COMMENT_ONLY_SENTINEL_CONTENT = """\
# This is a comment with __INJECT_TOKEN_SECRET__ in it
# Another comment: __INJECT_TOKEN_SECRET__ shows the format

proxmox_api_token_id     = "terraform@pve!terraform-token"
proxmox_api_token_secret = "already-set-value"
"""

_VALIDATION_JSON_WITH_DRIFT = json.dumps({
    "timestamp": "2026-02-23T08:00:00Z",
    "template_source": "file:/repo/terraform/environments/prod.tfvars.template",
    "rendered_path": "/var/lib/homelab-proxmox/tfvars/prod.tfvars",
    "validation_status": "pass",
    "token_id": "terraform@pve!terraform-token",
    "secret_present": True,
    "file_hash": "a1b2c3d4e5f6789012345678901234567890abcdef1234567890abcdef123456",
    "validation_errors": [],
    "drift_results": {
        "provisioning_gaps": ["new_key_in_template"],
        "manual_additions": ["old_manual_key"],
    },
    "change_warnings": [],
})

_VALIDATION_JSON_WITH_CHANGE_WARNINGS = json.dumps({
    "timestamp": "2026-02-23T08:00:00Z",
    "template_source": "file:/repo/terraform/environments/prod.tfvars.template",
    "rendered_path": "/var/lib/homelab-proxmox/tfvars/prod.tfvars",
    "validation_status": "pass",
    "token_id": "terraform@pve!terraform-token",
    "secret_present": True,
    "file_hash": "a1b2c3d4e5f6789012345678901234567890abcdef1234567890abcdef123456",
    "validation_errors": [],
    "drift_results": {
        "provisioning_gaps": [],
        "manual_additions": [],
    },
    "change_warnings": [
        {
            "key": "network_gateway",
            "old_value": "192.168.1.99",
            "new_value": "192.168.1.1",
        },
        {
            "key": "proxmox_api_url",
            "old_value": "https://192.168.1.100:8006/api2/json",
            "new_value": "https://192.168.1.112:8006/api2/json",
        },
    ],
})

_VALIDATION_JSON_BACKWARD_COMPAT = json.dumps({
    "timestamp": "2026-01-09T08:00:00Z",
    "template_source": "heredoc",
    "rendered_path": "/var/lib/homelab-proxmox/tfvars/prod.tfvars",
    "validation_status": "pass",
    "token_id": "terraform@pve!terraform-token",
    "secret_present": True,
    "file_hash": "a1b2c3d4e5f6789012345678901234567890abcdef1234567890abcdef123456",
    "validation_errors": [],
})

# ---------------------------------------------------------------------------
# Helper: detect sentinels on non-comment lines
# ---------------------------------------------------------------------------

def _sentinels_in_value_positions(content: str) -> list[str]:
    """Return all __INJECT_*__ markers found on non-comment lines."""
    sentinels = []
    for line in content.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        found = re.findall(r"__INJECT_[A-Z_]+__", line)
        sentinels.extend(found)
    return sentinels


# ---------------------------------------------------------------------------
# Test 1: sentinel appears exactly once in a value position in the CI template
# ---------------------------------------------------------------------------

def test_sentinel_detection_in_template():
    found = _sentinels_in_value_positions(_CI_TEMPLATE_CONTENT)
    assert len(found) == 1, (
        f"CI template must contain exactly one sentinel in a value position; found {found}"
    )
    assert found[0] == "__INJECT_TOKEN_SECRET__", (
        f"Sentinel must be __INJECT_TOKEN_SECRET__; got {found[0]!r}"
    )


# ---------------------------------------------------------------------------
# Test 2: no sentinels remain in value positions after injection
# ---------------------------------------------------------------------------

def test_sentinel_detection_after_injection():
    # The rendered content has a sentinel in a comment but not in a value position
    found = _sentinels_in_value_positions(_RENDERED_CONTENT)
    assert found == [], (
        f"Rendered output must contain no sentinels in value positions; found {found}"
    )


# ---------------------------------------------------------------------------
# Test 3: sentinels in comments are ignored (not detected as value-position sentinels)
# ---------------------------------------------------------------------------

def test_sentinel_ignored_in_comments():
    found = _sentinels_in_value_positions(_COMMENT_ONLY_SENTINEL_CONTENT)
    assert found == [], (
        "Sentinels appearing only in comments must NOT be detected as value-position sentinels; "
        f"found {found}"
    )


# ---------------------------------------------------------------------------
# Test 4: evidence format with drift_results fields
# ---------------------------------------------------------------------------

def test_evidence_format_with_drift():
    data = json.loads(_VALIDATION_JSON_WITH_DRIFT)

    # Required top-level fields must be present
    required_fields = [
        "timestamp", "template_source", "rendered_path", "validation_status",
        "token_id", "secret_present", "file_hash", "validation_errors",
    ]
    for field in required_fields:
        assert field in data, f"validation.json must contain required field {field!r}"

    # drift_results must be present and well-formed
    assert "drift_results" in data, "validation.json must contain 'drift_results'"
    drift = data["drift_results"]
    assert isinstance(drift.get("provisioning_gaps"), list), (
        "drift_results.provisioning_gaps must be a list"
    )
    assert isinstance(drift.get("manual_additions"), list), (
        "drift_results.manual_additions must be a list"
    )
    assert "new_key_in_template" in drift["provisioning_gaps"], (
        "provisioning_gaps must contain the expected key"
    )
    assert "old_manual_key" in drift["manual_additions"], (
        "manual_additions must contain the expected key"
    )


# ---------------------------------------------------------------------------
# Test 5: evidence format with change_warnings entries
# ---------------------------------------------------------------------------

def test_evidence_format_with_change_warnings():
    data = json.loads(_VALIDATION_JSON_WITH_CHANGE_WARNINGS)

    assert "change_warnings" in data, "validation.json must contain 'change_warnings'"
    warnings = data["change_warnings"]
    assert isinstance(warnings, list), "change_warnings must be a list"
    assert len(warnings) > 0, "test fixture must have at least one change warning"

    for entry in warnings:
        assert isinstance(entry.get("key"), str), (
            f"change_warnings entry must have string 'key'; got {entry!r}"
        )
        assert isinstance(entry.get("old_value"), str), (
            f"change_warnings entry must have string 'old_value'; got {entry!r}"
        )
        assert isinstance(entry.get("new_value"), str), (
            f"change_warnings entry must have string 'new_value'; got {entry!r}"
        )

    # Verify the specific gateway change warning
    gateway_warning = next(
        (w for w in warnings if w["key"] == "network_gateway"), None
    )
    assert gateway_warning is not None, (
        "change_warnings must contain an entry for 'network_gateway'"
    )
    assert gateway_warning["old_value"] == "192.168.1.99"
    assert gateway_warning["new_value"] == "192.168.1.1"


# ---------------------------------------------------------------------------
# Test 6: backward compatibility — old format without drift/warnings is valid
# ---------------------------------------------------------------------------

def test_evidence_format_backward_compatible():
    data = json.loads(_VALIDATION_JSON_BACKWARD_COMPAT)

    # Core required fields must be present
    required_fields = ["timestamp", "template_source", "rendered_path",
                       "validation_status", "token_id", "secret_present", "file_hash"]
    for field in required_fields:
        assert field in data, (
            f"Old-format validation.json must still contain required field {field!r}"
        )

    # New optional fields must be absent (this is the backward-compat format)
    assert "drift_results" not in data, (
        "Old-format validation.json should not have drift_results"
    )
    assert "change_warnings" not in data, (
        "Old-format validation.json should not have change_warnings"
    )

    # Basic value checks
    assert data["validation_status"] == "pass"
    assert data["secret_present"] is True
    assert data["token_id"] == "terraform@pve!terraform-token"


# ---------------------------------------------------------------------------
# Test 7: prod.tfvars.example contains no real infrastructure values
# ---------------------------------------------------------------------------

def test_example_file_no_real_values():
    assert PROD_TFVARS_EXAMPLE.exists(), (
        f"prod.tfvars.example must exist at {PROD_TFVARS_EXAMPLE}"
    )
    content = PROD_TFVARS_EXAMPLE.read_text(encoding="utf-8")

    # No real IP addresses
    real_ip_matches = re.findall(r"192\.168\.", content)
    assert real_ip_matches == [], (
        f"prod.tfvars.example must not contain real IP addresses (192.168.x.x); "
        f"found {len(real_ip_matches)} occurrence(s)"
    )

    # No real SSH public key (ECDSA key prefix)
    ssh_key_matches = re.findall(r"AAAAC3NzaC1", content)
    assert ssh_key_matches == [], (
        "prod.tfvars.example must not contain real SSH public keys (AAAAC3NzaC1); "
        f"found {len(ssh_key_matches)} occurrence(s)"
    )

    # No sentinel markers
    sentinel_matches = re.findall(r"__INJECT_", content)
    assert sentinel_matches == [], (
        "prod.tfvars.example must not contain sentinel markers (__INJECT_); "
        f"found {len(sentinel_matches)} occurrence(s)"
    )


# ---------------------------------------------------------------------------
# Test 8: prod.tfvars.template has exactly one sentinel and the literal token ID
# ---------------------------------------------------------------------------

def test_template_file_has_sentinel():
    assert PROD_TFVARS_TEMPLATE.exists(), (
        f"prod.tfvars.template must exist at {PROD_TFVARS_TEMPLATE}"
    )
    content = PROD_TFVARS_TEMPLATE.read_text(encoding="utf-8")

    # Exactly one sentinel in the entire file
    all_sentinels = re.findall(r"__INJECT_TOKEN_SECRET__", content)
    assert len(all_sentinels) == 1, (
        f"prod.tfvars.template must contain exactly one __INJECT_TOKEN_SECRET__; "
        f"found {len(all_sentinels)}"
    )

    # The literal token ID must be present
    assert "terraform@pve!terraform-token" in content, (
        "prod.tfvars.template must contain the literal token ID 'terraform@pve!terraform-token'"
    )
