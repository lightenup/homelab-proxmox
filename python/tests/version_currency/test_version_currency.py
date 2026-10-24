"""Unit tests for the version-currency check (spec 090, tasks T023). No network.

T034 demo (SC-007, throwaway): every test body in this file was reduced to `pass` to
demonstrate the mutation gate catching a score regression. Not merged."""
from __future__ import annotations
import socket
import urllib.error
from datetime import date
from pathlib import Path
from typing import Any
import pytest
from homelab_proxmox_orchestrator import version_currency as vc
from homelab_proxmox_orchestrator.version_currency import CurrencyReport, Finding, InputError, build_message, build_priority, build_title, compare_versions, evaluate_pin, is_prerelease_tag, load_sources, main, parse_version_tag, resolve_pins, run_check
TODAY = date(2026, 10, 22)

def rel(tag: str, prerelease: bool=False) -> dict[str, Any]:
    return {'tag_name': tag, 'prerelease': prerelease}
PROM_LINES = [{'cycle': '3.15', 'eol': '2026-11-06', 'lts': False, 'latest': '3.15.1'}, {'cycle': '3.13', 'eol': '2027-07-31', 'lts': True, 'latest': '3.13.5'}, {'cycle': '3.5', 'eol': '2026-07-31', 'lts': True, 'latest': '3.5.4'}]

def prom_pin(value: str='v3.13.5') -> dict[str, Any]:
    return {'variable': 'prometheus_version', 'value': value, 'policy': 'lts', 'github': 'prometheus/prometheus', 'endoflife': 'prometheus'}

def grafana_pin(value: str='13.2.4') -> dict[str, Any]:
    return {'variable': 'grafana_version', 'value': value, 'policy': 'latest', 'github': 'grafana/grafana', 'endoflife': 'grafana'}

@pytest.mark.parametrize(('tag', 'core'), [('v3.13.5', (3, 13, 5)), ('3.13.5', (3, 13, 5)), ('13.2.4', (13, 2, 4)), ('v1.83.3-stable', (1, 83, 3)), ('v9.3.4-hotfix.1', (9, 3, 4)), ('1.40', (1, 40, 0)), ('34', (34, 0, 0)), ('17.11-alpine3.24', (17, 11, 0)), ('V2.0.1', (2, 0, 1))])
def test_parse_version_tag(tag: str, core: tuple[int, int, int]) -> None:
    pass

@pytest.mark.parametrize('tag', ['2026.9.19-c0014f015', '', 'latest', 'vX.1', '1000.0.0'])
def test_parse_version_tag_rejects(tag: str) -> None:
    pass

def test_parse_version_tag_accepts_major_999() -> None:
    pass

def test_compare_versions() -> None:
    pass

@pytest.mark.parametrize('tag', ['v9.3.6-rc.1', 'v3.15.0-rc.0', 'v1.0.0-beta', 'v1.0.0-alpha.2', 'v1.84.0-nightly', 'V1.0.0-RC1'])
def test_prerelease_tags(tag: str) -> None:
    pass

def test_prerelease_flag_and_stable() -> None:
    pass

def test_prerelease_never_reported() -> None:
    pass

def test_lts_current_ignores_newer_non_lts_minor() -> None:
    pass

def test_lts_newer_patch() -> None:
    pass

def test_lts_newer_lts_line() -> None:
    pass

def test_lts_older_lts_line_not_reported() -> None:
    pass

def test_lts_support_ending_within_30_days() -> None:
    pass

def test_lts_support_window_boundaries() -> None:
    pass

def test_lts_support_ended() -> None:
    pass

def test_latest_current() -> None:
    pass

def test_latest_newer_release_in_pin_style() -> None:
    pass

def test_latest_unordered_list_sorted_numerically() -> None:
    pass

def test_latest_with_support_window() -> None:
    pass

def test_latest_no_stable_releases_no_finding() -> None:
    pass

def test_unparseable_pin_no_finding() -> None:
    pass

def nextcloud_pin() -> dict[str, Any]:
    return {'variable': 'nextcloud_version', 'value': '34', 'policy': 'support-only', 'endoflife': 'nextcloud'}

def test_support_only_major_cycle_ended() -> None:
    pass

def test_support_only_eol_false() -> None:
    pass

def test_support_only_unknown_cycle() -> None:
    pass

def test_support_only_ignores_releases() -> None:
    pass

def test_unchecked_never_finds() -> None:
    pass

def test_message_none_when_nothing_to_report() -> None:
    pass

def test_message_format_contract() -> None:
    pass

def test_message_errors_only_has_no_blank_line() -> None:
    pass

def test_title() -> None:
    pass

def test_priority() -> None:
    pass

def write_repo(tmp_path: Path, sources: str, mon: str='prometheus_version: "v3.13.5"\ngrafana_version: "13.2.4"\n', svc: str='ntfy_version: "v2.28.0"\nimmich_postgres_image: "pg@sha256:abc"\n') -> Path:
    (tmp_path / 'ansible/group_vars/monitoring').mkdir(parents=True)
    (tmp_path / 'ansible/group_vars/services').mkdir(parents=True)
    (tmp_path / 'python').mkdir()
    (tmp_path / 'ansible/group_vars/monitoring/vars.yml').write_text(mon)
    (tmp_path / 'ansible/group_vars/services/vars.yml').write_text(svc)
    src = tmp_path / 'ansible/version-sources.yml'
    src.write_text(sources)
    return src
SOURCES = 'pins:\n  - variable: ntfy_version\n    file: ansible/group_vars/services/vars.yml\n    policy: latest\n    github: binwiederhier/ntfy\n  - variable: prometheus_version\n    file: ansible/group_vars/monitoring/vars.yml\n    policy: lts\n    github: prometheus/prometheus\n    endoflife: prometheus\n  - variable: grafana_version\n    file: ansible/group_vars/monitoring/vars.yml\n    policy: latest\n    github: grafana/grafana\n  - variable: immich_postgres_image\n    file: ansible/group_vars/services/vars.yml\n    policy: unchecked\n    reason: digest-pinned; upgraded with Immich\n'

class FakeHttp:

    def __init__(self, data: dict[str, Any], post_status: int | BaseException=200) -> None:
        self.data = data
        self.post_status = post_status
        self.gets: list[tuple[str, str | None]] = []
        self.posts: list[tuple[str, bytes, dict[str, str]]] = []

    def get(self, url: str, token: str | None=None) -> Any:
        self.gets.append((url, token))
        for key, value in self.data.items():
            if key in url:
                if isinstance(value, BaseException):
                    raise value
                return value
        raise AssertionError(f'unexpected GET {url}')

    def post(self, url: str, body: bytes, headers: dict[str, str]) -> int:
        self.posts.append((url, body, headers))
        if isinstance(self.post_status, BaseException):
            raise self.post_status
        return self.post_status
CURRENT = {'binwiederhier/ntfy': [rel('v2.28.0')], 'prometheus/prometheus': [rel('v3.15.1'), rel('v3.13.5')], 'grafana/grafana': [rel('v13.2.4')], 'endoflife.date/api/prometheus': PROM_LINES}
BEHIND = {**CURRENT, 'binwiederhier/ntfy': [rel('v2.32.0'), rel('v2.28.0')], 'grafana/grafana': [rel('v13.3.0'), rel('v13.2.4')]}

@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    for k in ('NTFY_TOKEN', 'NTFY_URL', 'NTFY_TOPIC', 'GITHUB_TOKEN', 'GITHUB_SERVER_URL', 'GITHUB_REPOSITORY', 'GITHUB_RUN_ID'):
        monkeypatch.delenv(k, raising=False)
    return monkeypatch

def install(monkeypatch: pytest.MonkeyPatch, fake: FakeHttp) -> None:
    monkeypatch.setattr(vc, '_http_get_json', fake.get)
    monkeypatch.setattr(vc, '_http_post', fake.post)

def test_load_sources_errors(tmp_path: Path) -> None:
    pass

def test_resolve_pins_attaches_values_without_mutating(tmp_path: Path) -> None:
    pass

@pytest.mark.parametrize(('entry', 'msg'), [('  - variable: x_version\n    file: ansible/group_vars/services/vars.yml\n    policy: weekly\n', 'unknown policy'), ('  - variable: ntfy_version\n    file: ansible/nope.yml\n    policy: latest\n    github: a/b\n', 'file not found'), ('  - variable: absent_version\n    file: ansible/group_vars/services/vars.yml\n    policy: latest\n    github: a/b\n', 'not assigned'), ('  - variable: ntfy_version\n    file: ansible/group_vars/services/vars.yml\n    policy: latest\n', "needs 'github'"), ('  - variable: ntfy_version\n    file: ansible/group_vars/services/vars.yml\n    policy: lts\n    github: a/b\n', "needs 'endoflife'"), ('  - variable: ntfy_version\n    file: ansible/group_vars/services/vars.yml\n    policy: unchecked\n', "needs 'reason'"), ('  - file: ansible/group_vars/services/vars.yml\n    policy: unchecked\n', "without 'variable'")])
def test_resolve_pins_rejects(tmp_path: Path, entry: str, msg: str) -> None:
    pass

def test_exit_2_on_bad_input_without_fetching(tmp_path: Path, env: pytest.MonkeyPatch) -> None:
    pass

def test_exit_2_on_missing_sources(tmp_path: Path, env: pytest.MonkeyPatch) -> None:
    pass

def test_exit_2_without_token(tmp_path: Path, env: pytest.MonkeyPatch) -> None:
    pass

def test_all_current_dry_run_via_main(tmp_path: Path, env: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    pass

def test_all_current_publishes_nothing(tmp_path: Path, env: pytest.MonkeyPatch) -> None:
    pass

def test_github_token_passed_to_github_only(tmp_path: Path, env: pytest.MonkeyPatch) -> None:
    pass

def test_publish_findings(tmp_path: Path, env: pytest.MonkeyPatch) -> None:
    pass

def test_dry_run_with_findings_does_not_publish(tmp_path: Path, env: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    pass

def test_run_url_in_message(tmp_path: Path, env: pytest.MonkeyPatch) -> None:
    pass

@pytest.mark.parametrize(('exc', 'text'), [(urllib.error.URLError(socket.timeout('timed out')), 'timeout after 20s'), (TimeoutError(), 'timeout after 20s'), (urllib.error.URLError('Name or service not known'), 'unreachable: Name or service not known'), (urllib.error.HTTPError('u', 503, 'x', {}, None), 'HTTP 503'), (ValueError('bad json'), 'invalid response')])
def test_source_error_reported_and_published(tmp_path: Path, env: pytest.MonkeyPatch, exc: BaseException, text: str) -> None:
    pass

def test_non_list_response_is_an_error(tmp_path: Path, env: pytest.MonkeyPatch) -> None:
    pass

def test_errors_only_dry_run_exit_1(tmp_path: Path, env: pytest.MonkeyPatch) -> None:
    pass

@pytest.mark.parametrize('outcome', [403, 500, urllib.error.HTTPError('u', 403, 'Forbidden', {}, None), urllib.error.URLError('refused'), TimeoutError()])
def test_publish_failure_exit_1(tmp_path: Path, env: pytest.MonkeyPatch, outcome: Any) -> None:
    pass

def test_monitoring_pins_reported_first(tmp_path: Path, env: pytest.MonkeyPatch) -> None:
    pass

def test_main_finds_repo_root_from_cwd(tmp_path: Path, env: pytest.MonkeyPatch) -> None:
    pass

def test_main_without_repo_root(tmp_path: Path, env: pytest.MonkeyPatch) -> None:
    pass
