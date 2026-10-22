"""Unit tests for the version-currency check (spec 090, tasks T023). No network."""

from __future__ import annotations

import socket
import urllib.error
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from homelab_proxmox_orchestrator import version_currency as vc
from homelab_proxmox_orchestrator.version_currency import (
    CurrencyReport,
    Finding,
    InputError,
    build_message,
    build_priority,
    build_title,
    compare_versions,
    evaluate_pin,
    is_prerelease_tag,
    load_sources,
    main,
    parse_version_tag,
    resolve_pins,
    run_check,
)

TODAY = date(2026, 10, 22)


def rel(tag: str, prerelease: bool = False) -> dict[str, Any]:
    return {"tag_name": tag, "prerelease": prerelease}


PROM_LINES = [
    {"cycle": "3.15", "eol": "2026-11-06", "lts": False, "latest": "3.15.1"},
    {"cycle": "3.13", "eol": "2027-07-31", "lts": True, "latest": "3.13.5"},
    {"cycle": "3.5", "eol": "2026-07-31", "lts": True, "latest": "3.5.4"},
]


def prom_pin(value: str = "v3.13.5") -> dict[str, Any]:
    return {"variable": "prometheus_version", "value": value, "policy": "lts",
            "github": "prometheus/prometheus", "endoflife": "prometheus"}


def grafana_pin(value: str = "13.2.4") -> dict[str, Any]:
    return {"variable": "grafana_version", "value": value, "policy": "latest",
            "github": "grafana/grafana", "endoflife": "grafana"}


# --- 1. tag parsing ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("tag", "core"),
    [
        ("v3.13.5", (3, 13, 5)),
        ("3.13.5", (3, 13, 5)),
        ("13.2.4", (13, 2, 4)),
        ("v1.83.3-stable", (1, 83, 3)),
        ("v9.3.4-hotfix.1", (9, 3, 4)),
        ("1.40", (1, 40, 0)),
        ("34", (34, 0, 0)),
        ("17.11-alpine3.24", (17, 11, 0)),
        ("V2.0.1", (2, 0, 1)),
    ],
)
def test_parse_version_tag(tag: str, core: tuple[int, int, int]) -> None:
    assert parse_version_tag(tag) == core


@pytest.mark.parametrize("tag", ["2026.9.19-c0014f015", "", "latest", "vX.1", "1000.0.0"])
def test_parse_version_tag_rejects(tag: str) -> None:
    assert parse_version_tag(tag) is None


def test_parse_version_tag_accepts_major_999() -> None:
    assert parse_version_tag("999.1.2") == (999, 1, 2)


def test_compare_versions() -> None:
    assert compare_versions((3, 13, 5), (3, 13, 5)) == 0
    assert compare_versions((3, 13, 6), (3, 13, 5)) == 1
    assert compare_versions((3, 13, 4), (3, 13, 5)) == -1


# --- 2. pre-releases ----------------------------------------------------------------


@pytest.mark.parametrize("tag", ["v9.3.6-rc.1", "v3.15.0-rc.0", "v1.0.0-beta", "v1.0.0-alpha.2",
                                 "v1.84.0-nightly", "V1.0.0-RC1"])
def test_prerelease_tags(tag: str) -> None:
    assert is_prerelease_tag(tag, False) is True


def test_prerelease_flag_and_stable() -> None:
    assert is_prerelease_tag("v1.0.0", True) is True
    assert is_prerelease_tag("v1.0.0", False) is False
    assert is_prerelease_tag("v1.83.3-stable", False) is False


def test_prerelease_never_reported() -> None:
    pin = {"variable": "eurooffice_version", "value": "v9.3.5", "policy": "latest",
           "github": "euro-office/documentserver"}
    releases = [rel("v9.3.6-rc.1"), rel("v9.4.0", prerelease=True), rel("v9.3.5")]
    assert evaluate_pin(pin, releases, [], today=TODAY) == []


# --- 3. lts policy ------------------------------------------------------------------


def test_lts_current_ignores_newer_non_lts_minor() -> None:
    releases = [rel("v3.15.1"), rel("v3.13.5"), rel("v3.15.0")]
    assert evaluate_pin(prom_pin(), releases, PROM_LINES, today=TODAY) == []


def test_lts_newer_patch() -> None:
    releases = [rel("v3.15.1"), rel("v3.13.6"), rel("v3.13.5")]
    [f] = evaluate_pin(prom_pin(), releases, PROM_LINES, today=TODAY)
    assert (f.kind, f.available, f.line) == ("newer-patch", "v3.13.6", "3.13")


def test_lts_newer_lts_line() -> None:
    lines = PROM_LINES + [{"cycle": "3.17", "eol": "2028-01-31", "lts": True, "latest": "3.17.2"}]
    [f] = evaluate_pin(prom_pin(), [rel("v3.13.5")], lines, today=TODAY)
    assert (f.kind, f.available, f.line) == ("newer-lts-line", "v3.17.2", "3.17")


def test_lts_older_lts_line_not_reported() -> None:
    lines = [{"cycle": "3.5", "eol": "2027-12-31", "lts": True, "latest": "3.5.9"},
             {"cycle": "3.13", "eol": "2027-07-31", "lts": True, "latest": "3.13.5"}]
    assert evaluate_pin(prom_pin(), [rel("v3.13.5")], lines, today=TODAY) == []


def test_lts_support_ending_within_30_days() -> None:
    [f] = evaluate_pin(prom_pin(), [rel("v3.13.5")], PROM_LINES, today=date(2027, 7, 11))
    assert (f.kind, f.eol) == ("support-ending", "2027-07-31")


def test_lts_support_window_boundaries() -> None:
    at_30 = evaluate_pin(prom_pin(), [rel("v3.13.5")], PROM_LINES, today=date(2027, 7, 1))
    at_31 = evaluate_pin(prom_pin(), [rel("v3.13.5")], PROM_LINES, today=date(2027, 6, 30))
    on_eol = evaluate_pin(prom_pin(), [rel("v3.13.5")], PROM_LINES, today=date(2027, 7, 31))
    assert [f.kind for f in at_30] == ["support-ending"]
    assert at_31 == []
    assert [f.kind for f in on_eol] == ["support-ending"]


def test_lts_support_ended() -> None:
    [f] = evaluate_pin(prom_pin(), [rel("v3.13.5")], PROM_LINES, today=date(2027, 8, 1))
    assert f.kind == "support-ended"


# --- 4. latest policy ---------------------------------------------------------------


def test_latest_current() -> None:
    releases = [rel("v13.2.4"), rel("v13.1.8"), rel("v12.4.13")]
    assert evaluate_pin(grafana_pin(), releases, [], today=TODAY) == []


def test_latest_newer_release_in_pin_style() -> None:
    releases = [rel("v13.2.4"), rel("v13.3.0"), rel("v12.4.13")]
    [f] = evaluate_pin(grafana_pin(), releases, [], today=TODAY)
    assert (f.kind, f.available) == ("newer-release", "13.3.0")


def test_latest_unordered_list_sorted_numerically() -> None:
    pin = {"variable": "alertmanager_version", "value": "v0.34.1", "policy": "latest",
           "github": "prometheus/alertmanager"}
    releases = [rel("v0.9.0"), rel("v0.34.1"), rel("v0.35.0"), rel("v0.34.10")]
    [f] = evaluate_pin(pin, releases, [], today=TODAY)
    assert f.available == "v0.35.0"


def test_latest_with_support_window() -> None:
    lines = [{"cycle": "13.2", "eol": "2026-11-10", "lts": False, "latest": "13.2.4"}]
    [f] = evaluate_pin(grafana_pin(), [rel("v13.2.4")], lines, today=TODAY)
    assert (f.kind, f.eol) == ("support-ending", "2026-11-10")


def test_latest_no_stable_releases_no_finding() -> None:
    assert evaluate_pin(grafana_pin(), [rel("v14.0.0-rc.1")], [], today=TODAY) == []


def test_unparseable_pin_no_finding() -> None:
    pin = grafana_pin("main")
    assert evaluate_pin(pin, [rel("v13.3.0")], [], today=TODAY) == []


# --- 5. support-only policy ---------------------------------------------------------


def nextcloud_pin() -> dict[str, Any]:
    return {"variable": "nextcloud_version", "value": "34", "policy": "support-only",
            "endoflife": "nextcloud"}


def test_support_only_major_cycle_ended() -> None:
    lines = [{"cycle": "34", "eol": "2026-10-01"}, {"cycle": "35", "eol": "2027-04-01"}]
    [f] = evaluate_pin(nextcloud_pin(), [], lines, today=TODAY)
    assert (f.kind, f.eol) == ("support-ended", "2026-10-01")


def test_support_only_eol_false() -> None:
    assert evaluate_pin(nextcloud_pin(), [], [{"cycle": "34", "eol": False}], today=TODAY) == []


def test_support_only_unknown_cycle() -> None:
    assert evaluate_pin(nextcloud_pin(), [], [{"cycle": "35", "eol": "2020-01-01"}], today=TODAY) == []


def test_support_only_ignores_releases() -> None:
    lines = [{"cycle": "17", "eol": "2029-11-08"}]
    pin = {"variable": "llm_router_postgres_version", "value": "17.11-alpine3.24",
           "policy": "support-only", "endoflife": "postgresql"}
    assert evaluate_pin(pin, [rel("v18.0.0")], lines, today=TODAY) == []


# --- 6. unchecked ---------------------------------------------------------------------


def test_unchecked_never_finds() -> None:
    pin = {"variable": "immich_postgres_image", "value": "x@sha256:abc", "policy": "unchecked",
           "reason": "digest-pinned"}
    assert evaluate_pin(pin, [rel("v99.0.0")], [], today=TODAY) == []


# --- message, title, priority ---------------------------------------------------------


def test_message_none_when_nothing_to_report() -> None:
    assert build_message(CurrencyReport(unchecked=[("x", "y")]), today=TODAY) is None


def test_message_format_contract() -> None:
    report = CurrencyReport(
        findings=[
            Finding("prometheus_version", "v3.13.5", "newer-patch", available="v3.13.6", line="3.13"),
            Finding("grafana_version", "13.2.4", "newer-release", available="13.3.0"),
            Finding("telegraf_version", "1.40.2", "support-ending", eol="2026-11-16"),
            Finding("prometheus_version", "v3.13.5", "newer-lts-line", available="v3.17.2", line="3.17"),
            Finding("nextcloud_version", "34", "support-ended", eol="2026-10-01"),
        ],
        unchecked=[("immich_postgres_image", "digest-pinned; upgraded with Immich"),
                   ("market_model_version", "internal")],
        errors=[("endoflife.date/grafana", "timeout after 20s")],
    )
    assert build_message(report, today=TODAY, run_url="https://gh/run/1") == "\n".join([
        "prometheus_version v3.13.5 -> v3.13.6 (newer patch on LTS 3.13)",
        "grafana_version 13.2.4 -> 13.3.0 (newer release)",
        "telegraf_version 1.40.2: support ends 2026-11-16 (in 25 days)",
        "prometheus_version v3.13.5 -> v3.17.2 (newer LTS line 3.17)",
        "nextcloud_version 34: support ended 2026-10-01",
        "",
        "Not checked: immich_postgres_image (digest-pinned; upgraded with Immich), "
        "market_model_version (internal)",
        "Check errors: endoflife.date/grafana: timeout after 20s",
        "Run: https://gh/run/1",
    ])


def test_message_errors_only_has_no_blank_line() -> None:
    report = CurrencyReport(errors=[("github/a/b", "HTTP 500"), ("github/c/d", "HTTP 404")])
    assert build_message(report, today=TODAY) == "Check errors: github/a/b: HTTP 500; github/c/d: HTTP 404"


def test_title() -> None:
    assert build_title(CurrencyReport(findings=[Finding("a", "1", "newer-release")])) == \
        "Version pins: 1 behind"
    assert build_title(CurrencyReport(errors=[("s", "m"), ("t", "n")])) == \
        "Version pins: 0 behind, 2 check errors"


# --- 12. priority ---------------------------------------------------------------------


def test_priority() -> None:
    assert build_priority(CurrencyReport(findings=[Finding("a", "1", "newer-release")])) == "3"
    assert build_priority(CurrencyReport(findings=[Finding("a", "1", "support-ending")])) == "3"
    assert build_priority(CurrencyReport(findings=[Finding("a", "1", "support-ended")])) == "4"
    assert build_priority(CurrencyReport(errors=[("s", "m")])) == "4"


# --- input ------------------------------------------------------------------------------


def write_repo(tmp_path: Path, sources: str, mon: str = 'prometheus_version: "v3.13.5"\n'
               'grafana_version: "13.2.4"\n',
               svc: str = 'ntfy_version: "v2.28.0"\nimmich_postgres_image: "pg@sha256:abc"\n') -> Path:
    (tmp_path / "ansible/group_vars/monitoring").mkdir(parents=True)
    (tmp_path / "ansible/group_vars/services").mkdir(parents=True)
    (tmp_path / "python").mkdir()
    (tmp_path / "ansible/group_vars/monitoring/vars.yml").write_text(mon)
    (tmp_path / "ansible/group_vars/services/vars.yml").write_text(svc)
    src = tmp_path / "ansible/version-sources.yml"
    src.write_text(sources)
    return src


SOURCES = """pins:
  - variable: ntfy_version
    file: ansible/group_vars/services/vars.yml
    policy: latest
    github: binwiederhier/ntfy
  - variable: prometheus_version
    file: ansible/group_vars/monitoring/vars.yml
    policy: lts
    github: prometheus/prometheus
    endoflife: prometheus
  - variable: grafana_version
    file: ansible/group_vars/monitoring/vars.yml
    policy: latest
    github: grafana/grafana
  - variable: immich_postgres_image
    file: ansible/group_vars/services/vars.yml
    policy: unchecked
    reason: digest-pinned; upgraded with Immich
"""


class FakeHttp:
    def __init__(self, data: dict[str, Any], post_status: int | BaseException = 200) -> None:
        self.data = data
        self.post_status = post_status
        self.gets: list[tuple[str, str | None]] = []
        self.posts: list[tuple[str, bytes, dict[str, str]]] = []

    def get(self, url: str, token: str | None = None) -> Any:
        self.gets.append((url, token))
        for key, value in self.data.items():
            if key in url:
                if isinstance(value, BaseException):
                    raise value
                return value
        raise AssertionError(f"unexpected GET {url}")

    def post(self, url: str, body: bytes, headers: dict[str, str]) -> int:
        self.posts.append((url, body, headers))
        if isinstance(self.post_status, BaseException):
            raise self.post_status
        return self.post_status


CURRENT = {
    "binwiederhier/ntfy": [rel("v2.28.0")],
    "prometheus/prometheus": [rel("v3.15.1"), rel("v3.13.5")],
    "grafana/grafana": [rel("v13.2.4")],
    "endoflife.date/api/prometheus": PROM_LINES,
}
BEHIND = {**CURRENT, "binwiederhier/ntfy": [rel("v2.32.0"), rel("v2.28.0")],
          "grafana/grafana": [rel("v13.3.0"), rel("v13.2.4")]}


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    for k in ("NTFY_TOKEN", "NTFY_URL", "NTFY_TOPIC", "GITHUB_TOKEN",
              "GITHUB_SERVER_URL", "GITHUB_REPOSITORY", "GITHUB_RUN_ID"):
        monkeypatch.delenv(k, raising=False)
    return monkeypatch


def install(monkeypatch: pytest.MonkeyPatch, fake: FakeHttp) -> None:
    monkeypatch.setattr(vc, "_http_get_json", fake.get)
    monkeypatch.setattr(vc, "_http_post", fake.post)


def test_load_sources_errors(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_sources(tmp_path / "missing.yml")
    (tmp_path / "a.yml").write_text("other: []\n")
    with pytest.raises(ValueError):
        load_sources(tmp_path / "a.yml")
    (tmp_path / "b.yml").write_text("pins: {}\n")
    with pytest.raises(ValueError):
        load_sources(tmp_path / "b.yml")


def test_resolve_pins_attaches_values_without_mutating(tmp_path: Path) -> None:
    src = write_repo(tmp_path, SOURCES)
    raw = load_sources(src)
    pins = resolve_pins(raw, tmp_path)
    assert [p["value"] for p in pins] == ["v2.28.0", "v3.13.5", "13.2.4", "pg@sha256:abc"]
    assert "value" not in raw[0]


@pytest.mark.parametrize(
    ("entry", "msg"),
    [
        ("  - variable: x_version\n    file: ansible/group_vars/services/vars.yml\n    policy: weekly\n",
         "unknown policy"),
        ("  - variable: ntfy_version\n    file: ansible/nope.yml\n    policy: latest\n    github: a/b\n",
         "file not found"),
        ("  - variable: absent_version\n    file: ansible/group_vars/services/vars.yml\n    policy: latest\n"
         "    github: a/b\n", "not assigned"),
        ("  - variable: ntfy_version\n    file: ansible/group_vars/services/vars.yml\n    policy: latest\n",
         "needs 'github'"),
        ("  - variable: ntfy_version\n    file: ansible/group_vars/services/vars.yml\n    policy: lts\n"
         "    github: a/b\n", "needs 'endoflife'"),
        ("  - variable: ntfy_version\n    file: ansible/group_vars/services/vars.yml\n    policy: unchecked\n",
         "needs 'reason'"),
        ("  - file: ansible/group_vars/services/vars.yml\n    policy: unchecked\n", "without 'variable'"),
    ],
)
def test_resolve_pins_rejects(tmp_path: Path, entry: str, msg: str) -> None:
    src = write_repo(tmp_path, "pins:\n" + entry)
    with pytest.raises(InputError, match=msg):
        resolve_pins(load_sources(src), tmp_path)


# --- 11. bad input -> exit 2 ------------------------------------------------------------


def test_exit_2_on_bad_input_without_fetching(tmp_path: Path, env: pytest.MonkeyPatch) -> None:
    src = write_repo(tmp_path, SOURCES.replace("policy: lts", "policy: often"))
    fake = FakeHttp(CURRENT)
    install(env, fake)
    assert run_check(src, tmp_path, dry_run=True, today=TODAY).exit_code == 2
    assert fake.gets == []


def test_exit_2_on_missing_sources(tmp_path: Path, env: pytest.MonkeyPatch) -> None:
    assert run_check(tmp_path / "none.yml", tmp_path, dry_run=True).exit_code == 2


def test_exit_2_without_token(tmp_path: Path, env: pytest.MonkeyPatch) -> None:
    src = write_repo(tmp_path, SOURCES)
    fake = FakeHttp(CURRENT)
    install(env, fake)
    assert run_check(src, tmp_path, dry_run=False, today=TODAY).exit_code == 2
    assert fake.gets == [] and fake.posts == []


# --- 7. all current ---------------------------------------------------------------------


def test_all_current_dry_run_via_main(tmp_path: Path, env: pytest.MonkeyPatch,
                                      capsys: pytest.CaptureFixture[str]) -> None:
    write_repo(tmp_path, SOURCES)
    env.setenv("NTFY_TOKEN", "tk_secret")
    fake = FakeHttp(CURRENT)
    install(env, fake)
    assert main(["--dry-run", "--repo-root", str(tmp_path)]) == 0
    assert fake.posts == []
    assert capsys.readouterr().out.strip() == "All checked pins are current."


def test_all_current_publishes_nothing(tmp_path: Path, env: pytest.MonkeyPatch) -> None:
    src = write_repo(tmp_path, SOURCES)
    env.setenv("NTFY_TOKEN", "tk_secret")
    fake = FakeHttp(CURRENT)
    install(env, fake)
    result = run_check(src, tmp_path, dry_run=False, today=TODAY)
    assert (result.exit_code, result.message, fake.posts) == (0, None, [])
    assert [u for u, _ in fake.gets if "endoflife" in u] == ["https://endoflife.date/api/prometheus.json"]


def test_github_token_passed_to_github_only(tmp_path: Path, env: pytest.MonkeyPatch) -> None:
    src = write_repo(tmp_path, SOURCES)
    env.setenv("GITHUB_TOKEN", "ghs_x")
    fake = FakeHttp(CURRENT)
    install(env, fake)
    run_check(src, tmp_path, dry_run=True, today=TODAY)
    assert {(("github" in u), t) for u, t in fake.gets} == {(True, "ghs_x"), (False, None)}


# --- 8. findings + publish --------------------------------------------------------------


def test_publish_findings(tmp_path: Path, env: pytest.MonkeyPatch) -> None:
    src = write_repo(tmp_path, SOURCES)
    env.setenv("NTFY_TOKEN", "tk_secret")
    env.setenv("NTFY_URL", "https://ntfy.example/")
    env.setenv("NTFY_TOPIC", "versions-test")
    fake = FakeHttp(BEHIND)
    install(env, fake)
    result = run_check(src, tmp_path, dry_run=False, today=TODAY)
    assert result.exit_code == 0
    [(url, body, headers)] = fake.posts
    assert url == "https://ntfy.example/versions-test"
    assert headers["Authorization"] == "Bearer tk_secret"
    assert headers["Title"] == "Version pins: 2 behind"
    assert headers["Priority"] == "3"
    assert headers["Tags"] == "package"
    text = body.decode()
    assert "tk_secret" not in text
    assert text.splitlines() == [
        "grafana_version 13.2.4 -> 13.3.0 (newer release)",
        "ntfy_version v2.28.0 -> v2.32.0 (newer release)",
        "",
        "Not checked: immich_postgres_image (digest-pinned; upgraded with Immich)",
    ]


def test_dry_run_with_findings_does_not_publish(tmp_path: Path, env: pytest.MonkeyPatch,
                                               capsys: pytest.CaptureFixture[str]) -> None:
    write_repo(tmp_path, SOURCES)
    env.setenv("NTFY_TOKEN", "tk_secret")
    fake = FakeHttp(BEHIND)
    install(env, fake)
    assert main(["--dry-run", "--repo-root", str(tmp_path)]) == 0
    assert fake.posts == []
    out = capsys.readouterr().out
    assert "grafana_version 13.2.4 -> 13.3.0" in out and "tk_secret" not in out


def test_run_url_in_message(tmp_path: Path, env: pytest.MonkeyPatch) -> None:
    src = write_repo(tmp_path, SOURCES)
    env.setenv("GITHUB_SERVER_URL", "https://github.com")
    env.setenv("GITHUB_REPOSITORY", "o/r")
    env.setenv("GITHUB_RUN_ID", "42")
    install(env, FakeHttp(BEHIND))
    result = run_check(src, tmp_path, dry_run=True, today=TODAY)
    assert result.message is not None
    assert result.message.splitlines()[-1] == "Run: https://github.com/o/r/actions/runs/42"


# --- 9. source errors -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("exc", "text"),
    [
        (urllib.error.URLError(socket.timeout("timed out")), "timeout after 20s"),
        (TimeoutError(), "timeout after 20s"),
        (urllib.error.URLError("Name or service not known"), "unreachable: Name or service not known"),
        (urllib.error.HTTPError("u", 503, "x", {}, None), "HTTP 503"),  # type: ignore[arg-type]
        (ValueError("bad json"), "invalid response"),
    ],
)
def test_source_error_reported_and_published(tmp_path: Path, env: pytest.MonkeyPatch,
                                             exc: BaseException, text: str) -> None:
    src = write_repo(tmp_path, SOURCES)
    env.setenv("NTFY_TOKEN", "tk_secret")
    fake = FakeHttp({**BEHIND, "endoflife.date/api/prometheus": exc})
    install(env, fake)
    result = run_check(src, tmp_path, dry_run=False, today=TODAY)
    assert result.exit_code == 1
    assert result.report.errors == [("endoflife.date/prometheus", text)]
    assert "prometheus_version" not in [f.variable for f in result.report.findings]
    [(_, body, headers)] = fake.posts
    assert headers["Title"] == "Version pins: 2 behind, 1 check errors"
    assert headers["Priority"] == "4"
    assert f"Check errors: endoflife.date/prometheus: {text}" in body.decode()


def test_non_list_response_is_an_error(tmp_path: Path, env: pytest.MonkeyPatch) -> None:
    src = write_repo(tmp_path, SOURCES)
    install(env, FakeHttp({**CURRENT, "grafana/grafana": {"message": "rate limited"}}))
    result = run_check(src, tmp_path, dry_run=True, today=TODAY)
    assert result.exit_code == 1
    assert result.report.errors == [("github/grafana/grafana", "invalid response")]


def test_errors_only_dry_run_exit_1(tmp_path: Path, env: pytest.MonkeyPatch) -> None:
    src = write_repo(tmp_path, SOURCES)
    fake = FakeHttp({**CURRENT, "binwiederhier/ntfy": RuntimeError("boom")})
    install(env, fake)
    result = run_check(src, tmp_path, dry_run=True, today=TODAY)
    assert result.exit_code == 1 and fake.posts == []
    assert result.report.errors == [("github/binwiederhier/ntfy", "RuntimeError: boom")]


# --- 10. publish failures -----------------------------------------------------------------


@pytest.mark.parametrize(
    "outcome",
    [403, 500, urllib.error.HTTPError("u", 403, "Forbidden", {}, None),  # type: ignore[arg-type]
     urllib.error.URLError("refused"), TimeoutError()],
)
def test_publish_failure_exit_1(tmp_path: Path, env: pytest.MonkeyPatch, outcome: Any) -> None:
    src = write_repo(tmp_path, SOURCES)
    env.setenv("NTFY_TOKEN", "tk_secret")
    install(env, FakeHttp(BEHIND, post_status=outcome))
    assert run_check(src, tmp_path, dry_run=False, today=TODAY).exit_code == 1


# --- ordering and repo root ---------------------------------------------------------------


def test_monitoring_pins_reported_first(tmp_path: Path, env: pytest.MonkeyPatch) -> None:
    src = write_repo(tmp_path, SOURCES)
    install(env, FakeHttp(BEHIND))
    result = run_check(src, tmp_path, dry_run=True, today=TODAY)
    assert [f.variable for f in result.report.findings] == ["grafana_version", "ntfy_version"]


def test_main_finds_repo_root_from_cwd(tmp_path: Path, env: pytest.MonkeyPatch) -> None:
    write_repo(tmp_path, SOURCES)
    (tmp_path / "ansible/roles").mkdir()
    env.chdir(tmp_path / "ansible/roles")
    install(env, FakeHttp(CURRENT))
    assert main(["--dry-run"]) == 0


def test_main_without_repo_root(tmp_path: Path, env: pytest.MonkeyPatch) -> None:
    env.chdir(tmp_path)
    assert main(["--dry-run"]) == 2
