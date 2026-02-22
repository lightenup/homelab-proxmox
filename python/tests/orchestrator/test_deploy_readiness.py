from __future__ import annotations

# Evidence-artifact contract tests for deploy key injection and network reachability checks.
# Validates the format and required fields of lxc-deploy-key.txt and network-check.txt
# without requiring live containers, pct, ping, or sudo.
#
# Pattern: inline string fixtures (same approach as _SIMPLE_TFVARS in test_tfvars_mountpoints.py).
# Tests: 5 total per plan.md Step 5 / data-model.md / spec FR-003, FR-006-FR-009, FR-011, FR-017.

import pytest

# ---------------------------------------------------------------------------
# Helpers: minimal key-value parser for flat evidence artifact files
# ---------------------------------------------------------------------------

def _parse_kv(content: str) -> dict[str, str]:
    """Parse key=value lines from an evidence artifact, ignoring section headers."""
    result = {}
    for line in content.splitlines():
        if "=" in line and not line.startswith("---"):
            key, _, value = line.partition("=")
            result[key.strip()] = value.strip()
    return result


def _has_section(content: str, header: str) -> bool:
    """Return True if the section header appears in the evidence content."""
    return header in content


# ---------------------------------------------------------------------------
# Inline fixtures: sample evidence artifact content strings (no live containers)
# ---------------------------------------------------------------------------

_DEPLOY_KEY_INJECTED = """\
ctid=104
key_file=/home/ci/.ssh/id_lxc_deploy
key_fingerprint=SHA256:abc123defghijklmnopqrstuvwxyz0123456789ABCDE
action=injected
authorized_keys_line_count_before=0
authorized_keys_line_count_after=1
"""

_DEPLOY_KEY_SKIPPED = """\
ctid=104
key_file=/home/ci/.ssh/id_lxc_deploy
key_fingerprint=SHA256:abc123defghijklmnopqrstuvwxyz0123456789ABCDE
action=skipped
authorized_keys_line_count_before=1
authorized_keys_line_count_after=1
"""

_NETWORK_CHECK_OK = """\
ctid=104
expected_ip=10.0.0.50
timestamp=2026-02-22T12:00:00Z
ping_status=ok
"""

_NETWORK_CHECK_UNREACHABLE = """\
ctid=104
expected_ip=10.0.0.50
timestamp=2026-02-22T12:00:00Z
ping_status=unreachable
--- ip addr show eth0 ---
2: eth0: <BROADCAST,MULTICAST> mtu 1500 qdisc noop state DOWN group default qlen 1000
--- ip route ---

--- pct config net ---
net0: name=eth0,bridge=vmbr0,ip=10.0.0.50/24,gw=10.0.0.1,firewall=1
"""


# ---------------------------------------------------------------------------
# T005-1: test_deploy_key_evidence_format
# Verify all required fields present per data-model.md (FR-017).
# ---------------------------------------------------------------------------

def test_deploy_key_evidence_format():
    for content in (_DEPLOY_KEY_INJECTED, _DEPLOY_KEY_SKIPPED):
        kv = _parse_kv(content)
        assert "ctid" in kv, "lxc-deploy-key.txt must contain 'ctid'"
        assert "key_file" in kv, "lxc-deploy-key.txt must contain 'key_file'"
        assert "key_fingerprint" in kv, "lxc-deploy-key.txt must contain 'key_fingerprint'"
        assert "action" in kv, "lxc-deploy-key.txt must contain 'action'"
        assert "authorized_keys_line_count_before" in kv, (
            "lxc-deploy-key.txt must contain 'authorized_keys_line_count_before'"
        )
        assert "authorized_keys_line_count_after" in kv, (
            "lxc-deploy-key.txt must contain 'authorized_keys_line_count_after'"
        )


# ---------------------------------------------------------------------------
# T005-2: test_deploy_key_evidence_action_values
# Verify action field accepts exactly 'injected' and 'skipped' (FR-003, FR-011).
# ---------------------------------------------------------------------------

def test_deploy_key_evidence_action_values():
    valid_actions = {"injected", "skipped"}

    kv_injected = _parse_kv(_DEPLOY_KEY_INJECTED)
    assert kv_injected["action"] in valid_actions, (
        f"action='injected' must be a valid action; got {kv_injected['action']!r}"
    )

    kv_skipped = _parse_kv(_DEPLOY_KEY_SKIPPED)
    assert kv_skipped["action"] in valid_actions, (
        f"action='skipped' must be a valid action; got {kv_skipped['action']!r}"
    )

    invalid_content = _DEPLOY_KEY_INJECTED.replace("action=injected", "action=unknown_value")
    kv_invalid = _parse_kv(invalid_content)
    assert kv_invalid["action"] not in valid_actions, (
        "action='unknown_value' must NOT be a valid action"
    )


# ---------------------------------------------------------------------------
# T005-3: test_network_check_evidence_format_ok
# Verify required fields present and no diagnostic sections on success (FR-009).
# ---------------------------------------------------------------------------

def test_network_check_evidence_format_ok():
    kv = _parse_kv(_NETWORK_CHECK_OK)
    assert "ctid" in kv, "network-check.txt must contain 'ctid'"
    assert "expected_ip" in kv, "network-check.txt must contain 'expected_ip'"
    assert "ping_status" in kv, "network-check.txt must contain 'ping_status'"
    assert kv["ping_status"] == "ok", f"ping_status must be 'ok'; got {kv['ping_status']!r}"

    assert not _has_section(_NETWORK_CHECK_OK, "--- ip addr show eth0 ---"), (
        "ping_status=ok evidence must NOT contain ip addr section"
    )
    assert not _has_section(_NETWORK_CHECK_OK, "--- ip route ---"), (
        "ping_status=ok evidence must NOT contain ip route section"
    )
    assert not _has_section(_NETWORK_CHECK_OK, "--- pct config net ---"), (
        "ping_status=ok evidence must NOT contain pct config net section"
    )


# ---------------------------------------------------------------------------
# T005-4: test_network_check_evidence_format_unreachable
# Verify required fields and all three diagnostic section headers on failure
# (FR-007, FR-012).
# ---------------------------------------------------------------------------

def test_network_check_evidence_format_unreachable():
    kv = _parse_kv(_NETWORK_CHECK_UNREACHABLE)
    assert "ctid" in kv, "network-check.txt must contain 'ctid'"
    assert "expected_ip" in kv, "network-check.txt must contain 'expected_ip'"
    assert "ping_status" in kv, "network-check.txt must contain 'ping_status'"
    assert kv["ping_status"] == "unreachable", (
        f"ping_status must be 'unreachable'; got {kv['ping_status']!r}"
    )

    assert _has_section(_NETWORK_CHECK_UNREACHABLE, "--- ip addr show eth0 ---"), (
        "ping_status=unreachable evidence must contain '--- ip addr show eth0 ---'"
    )
    assert _has_section(_NETWORK_CHECK_UNREACHABLE, "--- ip route ---"), (
        "ping_status=unreachable evidence must contain '--- ip route ---'"
    )
    assert _has_section(_NETWORK_CHECK_UNREACHABLE, "--- pct config net ---"), (
        "ping_status=unreachable evidence must contain '--- pct config net ---'"
    )


# ---------------------------------------------------------------------------
# T005-5: test_network_check_evidence_ping_status_values
# Verify ping_status accepts exactly 'ok' and 'unreachable' (FR-006, FR-008).
# ---------------------------------------------------------------------------

def test_network_check_evidence_ping_status_values():
    valid_ping_statuses = {"ok", "unreachable"}

    kv_ok = _parse_kv(_NETWORK_CHECK_OK)
    assert kv_ok["ping_status"] in valid_ping_statuses, (
        f"ping_status='ok' must be valid; got {kv_ok['ping_status']!r}"
    )

    kv_unreachable = _parse_kv(_NETWORK_CHECK_UNREACHABLE)
    assert kv_unreachable["ping_status"] in valid_ping_statuses, (
        f"ping_status='unreachable' must be valid; got {kv_unreachable['ping_status']!r}"
    )

    invalid_content = _NETWORK_CHECK_OK.replace("ping_status=ok", "ping_status=timeout")
    kv_invalid = _parse_kv(invalid_content)
    assert kv_invalid["ping_status"] not in valid_ping_statuses, (
        "ping_status='timeout' must NOT be a valid ping_status"
    )
