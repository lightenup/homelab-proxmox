from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from homelab_proxmox_orchestrator.version_currency import (
    parse_version_tag,
    is_prerelease_tag,
    compare_versions,
    Finding,
    CurrencyReport,
    load_sources,
    evaluate_pin,
    build_message,
    run_check,
)


# --- parse_version_tag ---

def test_parse_version_tag_v_prefix():
    assert parse_version_tag("v3.13.5") == (3, 13, 5)

def test_parse_version_tag_no_prefix():
    assert parse_version_tag("13.2.4") == (13, 2, 4)

def test_parse_version_tag_two_part():
    assert parse_version_tag("1.40") == (1, 40, 0)

def test_parse_version_tag_with_suffix():
    assert parse_version_tag("v1.83.3-stable") == (1, 83, 3)

def test_parse_version_tag_invalid():
    assert parse_version_tag("not-a-version") is None

def test_parse_version_tag_empty():
    assert parse_version_tag("") is None


# --- is_prerelease_tag ---

def test_prerelease_rc():
    assert is_prerelease_tag("v1.0.0-rc.1", False) is True

def test_prerelease_beta():
    assert is_prerelease_tag("v1.0.0-beta", False) is True

def test_prerelease_alpha():
    assert is_prerelease_tag("v1.0.0-alpha", False) is True

def test_stable_tag():
    assert is_prerelease_tag("v1.0.0", False) is False

def test_prerelease_flag():
    assert is_prerelease_tag("v1.0.0", True) is True

def test_stable_with_flag_false():
    assert is_prerelease_tag("v1.0.0", False) is False


# --- compare_versions ---

def test_compare_equal():
    assert compare_versions((3, 13, 5), (3, 13, 5)) == 0

def test_compare_greater():
    assert compare_versions((3, 13, 6), (3, 13, 5)) > 0

def test_compare_less():
    assert compare_versions((3, 13, 4), (3, 13, 5)) < 0

def test_compare_major():
    assert compare_versions((4, 0, 0), (3, 13, 5)) > 0


# --- Finding / CurrencyReport ---

def test_finding_fields():
    f = Finding(
        variable="prometheus_version",
        pinned="v3.13.5",
        kind="newer-patch",
        available="v3.13.6",
    )
    assert f.variable == "prometheus_version"
    assert f.pinned == "v3.13.5"
    assert f.kind == "newer-patch"
    assert f.available == "v3.13.6"

def test_report_fields():
    r = CurrencyReport(
        findings=[],
        unchecked=[("immich_postgres_image", "digest-pinned")],
        errors=[],
    )
    assert r.findings == []
    assert len(r.unchecked) == 1
    assert r.errors == []


# --- load_sources ---

def test_load_sources_valid(tmp_path: Path):
    src = tmp_path / "version-sources.yml"
    src.write_text(
        "pins:\n"
        "  - variable: test_version\n"
        "    file: some/file.yml\n"
        "    policy: latest\n"
        "    github: owner/repo\n"
    )
    pins = load_sources(src)
    assert len(pins) == 1
    assert pins[0]["variable"] == "test_version"
    assert pins[0]["policy"] == "latest"

def test_load_sources_missing_file(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_sources(tmp_path / "nonexistent.yml")

def test_load_sources_invalid_yaml(tmp_path: Path):
    src = tmp_path / "bad.yml"
    src.write_text(":::not yaml:::")
    with pytest.raises(Exception):
        load_sources(src)

def test_load_sources_no_pins_key(tmp_path: Path):
    src = tmp_path / "nopins.yml"
    src.write_text("other: []\n")
    with pytest.raises(ValueError):
        load_sources(src)


# --- evaluate_pin ---

def test_evaluate_pin_newer_patch():
    pin = {
        "variable": "prometheus_version",
        "value": "v3.13.5",
        "policy": "lts",
        "github": "prometheus/prometheus",
        "endoflife": "prometheus",
    }
    releases = [
        {"tag_name": "v3.13.6", "prerelease": False},
        {"tag_name": "v3.13.5", "prerelease": False},
    ]
    support_lines = [
        {"cycle": "3.13", "eol": "2027-07-31", "lts": True, "latest": "3.13.6"},
    ]
    findings = evaluate_pin(pin, releases, support_lines)
    assert len(findings) == 1
    assert findings[0].kind == "newer-patch"
    assert findings[0].available == "v3.13.6"

def test_evaluate_pin_current():
    pin = {
        "variable": "grafana_version",
        "value": "13.2.4",
        "policy": "latest",
        "github": "grafana/grafana",
    }
    releases = [
        {"tag_name": "13.2.4", "prerelease": False},
    ]
    findings = evaluate_pin(pin, releases, [])
    assert findings == []

def test_evaluate_pin_newer_release():
    pin = {
        "variable": "grafana_version",
        "value": "13.2.4",
        "policy": "latest",
        "github": "grafana/grafana",
    }
    releases = [
        {"tag_name": "13.3.0", "prerelease": False},
        {"tag_name": "13.2.4", "prerelease": False},
    ]
    findings = evaluate_pin(pin, releases, [])
    assert len(findings) == 1
    assert findings[0].kind == "newer-release"

def test_evaluate_pin_support_ended():
    pin = {
        "variable": "nextcloud_version",
        "value": "34",
        "policy": "support-only",
        "endoflife": "nextcloud",
    }
    support_lines = [
        {"cycle": "34", "eol": "2026-10-01", "lts": False, "latest": "34.1.0"},
    ]
    findings = evaluate_pin(pin, releases=[], support_lines=support_lines)
    assert len(findings) == 1
    assert findings[0].kind == "support-ended"

def test_evaluate_pin_support_ending_soon():
    pin = {
        "variable": "telegraf_version",
        "value": "1.40.2",
        "policy": "latest",
        "github": "influxdata/telegraf",
        "endoflife": "telegraf",
    }
    releases = [
        {"tag_name": "1.40.2", "prerelease": False},
    ]
    support_lines = [
        {"cycle": "1.40", "eol": "2026-12-07", "lts": False, "latest": "1.40.2"},
    ]
    findings = evaluate_pin(pin, releases, support_lines)
    assert any(f.kind == "support-ending" for f in findings)

def test_evaluate_pin_excludes_prerelease():
    pin = {
        "variable": "test_version",
        "value": "1.0.0",
        "policy": "latest",
        "github": "owner/repo",
    }
    releases = [
        {"tag_name": "2.0.0-rc.1", "prerelease": False},
        {"tag_name": "1.0.0", "prerelease": False},
    ]
    findings = evaluate_pin(pin, releases, [])
    assert findings == []

def test_evaluate_pin_unchecked():
    pin = {
        "variable": "immich_postgres_image",
        "value": "sha256:abc",
        "policy": "unchecked",
        "reason": "digest-pinned",
    }
    findings = evaluate_pin(pin, [], [])
    assert findings == []


# --- build_message ---

def test_build_message_no_findings():
    report = CurrencyReport(findings=[], unchecked=[], errors=[])
    assert build_message(report) is None

def test_build_message_with_findings():
    report = CurrencyReport(
        findings=[
            Finding(variable="prometheus_version", pinned="v3.13.5", kind="newer-patch", available="v3.13.6"),
            Finding(variable="grafana_version", pinned="13.2.4", kind="newer-release", available="13.3.0"),
        ],
        unchecked=[("immich_postgres_image", "digest-pinned")],
        errors=[],
    )
    msg = build_message(report)
    assert msg is not None
    assert "prometheus_version" in msg
    assert "grafana_version" in msg
    assert "v3.13.6" in msg
    assert "13.3.0" in msg
    assert "immich_postgres_image" in msg

def test_build_message_with_errors():
    report = CurrencyReport(
        findings=[],
        unchecked=[],
        errors=[("endoflife.date/grafana", "timeout after 20s")],
    )
    msg = build_message(report)
    assert msg is not None
    assert "timeout after 20s" in msg

def test_build_message_priority_support_ended():
    report = CurrencyReport(
        findings=[Finding(variable="x", pinned="1", kind="support-ended", eol="2026-01-01")],
        unchecked=[],
        errors=[],
    )
    msg = build_message(report)
    assert msg is not None

def test_build_message_no_token_in_output():
    report = CurrencyReport(
        findings=[Finding(variable="x", pinned="1", kind="newer-patch", available="2")],
        unchecked=[],
        errors=[],
    )
    msg = build_message(report)
    assert "token" not in msg.lower() or "NTFY_TOKEN" not in msg


# --- run_check (integration with mocked HTTP) ---

def _make_sources_file(tmp_path: Path) -> Path:
    src = tmp_path / "version-sources.yml"
    src.write_text(
        "pins:\n"
        "  - variable: test_version\n"
        "    file: test_vars.yml\n"
        "    policy: latest\n"
        "    github: owner/repo\n"
    )
    var_file = tmp_path / "test_vars.yml"
    var_file.write_text('test_version: "1.0.0"\n')
    return src

def test_run_check_dry_run_no_findings(tmp_path: Path):
    src = _make_sources_file(tmp_path)
    with patch("homelab_proxmox_orchestrator.version_currency._http_get_json") as mock_http:
        mock_http.return_value = [
            {"tag_name": "1.0.0", "prerelease": False},
        ]
        result = run_check(sources_path=src, repo_root=tmp_path, dry_run=True)
    assert result.exit_code == 0

def test_run_check_dry_run_with_findings(tmp_path: Path):
    src = _make_sources_file(tmp_path)
    with patch("homelab_proxmox_orchestrator.version_currency._http_get_json") as mock_http:
        mock_http.return_value = [
            {"tag_name": "2.0.0", "prerelease": False},
            {"tag_name": "1.0.0", "prerelease": False},
        ]
        result = run_check(sources_path=src, repo_root=tmp_path, dry_run=True)
    assert result.exit_code == 0
    assert result.report.findings

def test_run_check_missing_token_not_dry_run(tmp_path: Path):
    src = _make_sources_file(tmp_path)
    with patch.dict("os.environ", {}, clear=True):
        with patch("homelab_proxmox_orchestrator.version_currency._http_get_json") as mock_http:
            mock_http.return_value = [{"tag_name": "1.0.0", "prerelease": False}]
            result = run_check(sources_path=src, repo_root=tmp_path, dry_run=False)
    assert result.exit_code == 2

def test_run_check_publish_failure(tmp_path: Path):
    src = _make_sources_file(tmp_path)
    with patch.dict("os.environ", {"NTFY_TOKEN": "test-token"}, clear=True):
        with patch("homelab_proxmox_orchestrator.version_currency._http_get_json") as mock_http:
            mock_http.return_value = [
                {"tag_name": "2.0.0", "prerelease": False},
                {"tag_name": "1.0.0", "prerelease": False},
            ]
        with patch("homelab_proxmox_orchestrator.version_currency._http_post") as mock_post:
            mock_post.return_value = 500
            result = run_check(sources_path=src, repo_root=tmp_path, dry_run=False)
    assert result.exit_code == 1

def test_run_check_source_fetch_error(tmp_path: Path):
    src = _make_sources_file(tmp_path)
    with patch.dict("os.environ", {"NTFY_TOKEN": "test-token"}, clear=True):
        with patch("homelab_proxmox_orchestrator.version_currency._http_get_json") as mock_http:
            mock_http.side_effect = Exception("connection refused")
            result = run_check(sources_path=src, repo_root=tmp_path, dry_run=False)
    assert result.exit_code == 1
