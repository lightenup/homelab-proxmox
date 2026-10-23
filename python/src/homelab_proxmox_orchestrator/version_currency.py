"""Weekly version-currency check for pinned versions (spec 090).

Reads ``ansible/version-sources.yml``, compares each pin with GitHub releases and
endoflife.date support windows, and posts one ntfy message when anything is behind.
Interface: ``specs/090-monitoring-version-currency/contracts/currency-check.md``.

Exit codes: 0 = all sources read and nothing to report, or the report was published;
1 = a source could not be read or parsed, or the publish failed;
2 = bad input (sources file, pin file or variable, or a missing token).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Callable

import yaml

HTTP_TIMEOUT = 20
SUPPORT_WARNING_DAYS = 30
POLICIES = ("lts", "latest", "support-only", "unchecked")
PRERELEASE_MARKERS = ("-rc", "-beta", "-alpha", "-nightly", "-dev")
# Pins in this file are service pins; everything else is a monitoring pin (reported first).
SERVICES_FILE = "ansible/group_vars/services/vars.yml"
DEFAULT_NTFY_URL = "https://ntfy.hus-sky.no"
DEFAULT_NTFY_TOPIC = "versions"

Version = tuple[int, int, int]


class InputError(Exception):
    """Invalid sources file, pin file or variable (exit code 2)."""


@dataclass
class Finding:
    variable: str
    pinned: str
    kind: str  # newer-patch | newer-release | newer-lts-line | support-ending | support-ended
    available: str | None = None
    eol: str | None = None
    line: str | None = None


@dataclass
class CurrencyReport:
    findings: list[Finding] = field(default_factory=list)
    unchecked: list[tuple[str, str]] = field(default_factory=list)
    errors: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class CheckResult:
    exit_code: int
    report: CurrencyReport
    message: str | None = None


# --------------------------------------------------------------------------- parsing


def parse_version_tag(tag: str) -> Version | None:
    """Numeric core of a tag: ``v3.13.5`` -> (3, 13, 5); suffixes are ignored.

    Returns None for tags without a numeric core and for date-style tags such as
    ``2026.9.19-c0014f015`` (a "major" of 1000 or more is a year, not a version).
    """
    if not tag:
        return None
    m = re.match(r"^[vV]?(\d+)(?:\.(\d+))?(?:\.(\d+))?(?![\d])", tag.strip())
    if not m:
        return None
    major = int(m.group(1))
    if major >= 1000:
        return None
    return (major, int(m.group(2) or 0), int(m.group(3) or 0))


def is_prerelease_tag(tag: str, github_prerelease: bool) -> bool:
    if github_prerelease:
        return True
    lowered = tag.lower()
    return any(marker in lowered for marker in PRERELEASE_MARKERS)


def compare_versions(a: Version, b: Version) -> int:
    return (a > b) - (a < b)


def _display(tag: str, pinned: str) -> str:
    """Show an upstream tag in the pin's own style (with or without a leading ``v``)."""
    bare = tag[1:] if tag[:1] in ("v", "V") else tag
    return f"v{bare}" if pinned[:1] in ("v", "V") else bare


def _parse_eol(eol: Any) -> date | None:
    if isinstance(eol, str):
        try:
            return date.fromisoformat(eol)
        except ValueError:
            return None
    return None


def _stable_releases(releases: list[dict[str, Any]]) -> list[tuple[Version, str]]:
    out: list[tuple[Version, str]] = []
    for r in releases:
        tag = str(r.get("tag_name", ""))
        if is_prerelease_tag(tag, bool(r.get("prerelease", False))):
            continue
        core = parse_version_tag(tag)
        if core is not None:
            out.append((core, tag))
    return out


def _find_line(support_lines: list[dict[str, Any]], core: Version) -> dict[str, Any] | None:
    """The support line for a pin: ``major.minor`` first, then ``major`` (Nextcloud, PostgreSQL)."""
    by_cycle = {str(line.get("cycle", "")): line for line in support_lines}
    return by_cycle.get(f"{core[0]}.{core[1]}") or by_cycle.get(str(core[0]))


# --------------------------------------------------------------------------- evaluation


def evaluate_pin(
    pin: dict[str, Any],
    releases: list[dict[str, Any]],
    support_lines: list[dict[str, Any]],
    today: date | None = None,
) -> list[Finding]:
    """Findings for one pin under its policy (research R-10)."""
    today = today or date.today()
    policy = pin.get("policy", "unchecked")
    if policy == "unchecked":
        return []

    variable = pin["variable"]
    pinned = str(pin.get("value", ""))
    core = parse_version_tag(pinned)
    if core is None:
        return []

    findings: list[Finding] = []
    stable = _stable_releases(releases)

    if policy == "lts":
        same_line = [(c, t) for c, t in stable if c[:2] == core[:2]]
        if same_line:
            best_core, best_tag = max(same_line)
            if compare_versions(best_core, core) > 0:
                findings.append(Finding(variable, pinned, "newer-patch",
                                        available=_display(best_tag, pinned),
                                        line=f"{core[0]}.{core[1]}"))
        newer_lts = []
        for line in support_lines:
            cycle_core = parse_version_tag(str(line.get("cycle", "")))
            if line.get("lts") and cycle_core is not None and cycle_core[:2] > core[:2]:
                newer_lts.append((cycle_core, line))
        if newer_lts:
            cycle_core, line = max(newer_lts, key=lambda item: item[0])
            latest = str(line.get("latest") or line.get("cycle"))
            findings.append(Finding(variable, pinned, "newer-lts-line",
                                    available=_display(latest, pinned),
                                    line=f"{cycle_core[0]}.{cycle_core[1]}"))

    elif policy == "latest" and stable:
        best_core, best_tag = max(stable)
        if compare_versions(best_core, core) > 0:
            findings.append(Finding(variable, pinned, "newer-release",
                                    available=_display(best_tag, pinned)))

    line = _find_line(support_lines, core) if support_lines else None
    eol = _parse_eol(line.get("eol")) if line else None
    if eol is not None:
        if eol < today:
            findings.append(Finding(variable, pinned, "support-ended", eol=eol.isoformat()))
        elif (eol - today).days <= SUPPORT_WARNING_DAYS:
            findings.append(Finding(variable, pinned, "support-ending", eol=eol.isoformat()))

    return findings


# --------------------------------------------------------------------------- report


def build_title(report: CurrencyReport) -> str:
    parts = [f"{len(report.findings)} behind"]
    if report.errors:
        parts.append(f"{len(report.errors)} check errors")
    return "Version pins: " + ", ".join(parts)


def build_priority(report: CurrencyReport) -> str:
    severe = report.errors or any(f.kind == "support-ended" for f in report.findings)
    return "4" if severe else "3"


def _finding_line(f: Finding, today: date) -> str:
    if f.kind == "newer-patch":
        return f"{f.variable} {f.pinned} -> {f.available} (newer patch on LTS {f.line})"
    if f.kind == "newer-lts-line":
        return f"{f.variable} {f.pinned} -> {f.available} (newer LTS line {f.line})"
    if f.kind == "newer-release":
        return f"{f.variable} {f.pinned} -> {f.available} (newer release)"
    if f.kind == "support-ended":
        return f"{f.variable} {f.pinned}: support ended {f.eol}"
    days = (date.fromisoformat(f.eol) - today).days if f.eol else 0
    return f"{f.variable} {f.pinned}: support ends {f.eol} (in {days} days)"


def build_message(
    report: CurrencyReport, today: date | None = None, run_url: str | None = None
) -> str | None:
    """Plain-text body per contract §4, or None when there is nothing to send."""
    if not report.findings and not report.errors:
        return None
    today = today or date.today()
    lines = [_finding_line(f, today) for f in report.findings]
    tail: list[str] = []
    if report.unchecked:
        tail.append("Not checked: " + ", ".join(f"{v} ({r})" for v, r in report.unchecked))
    if report.errors:
        tail.append("Check errors: " + "; ".join(f"{s}: {m}" for s, m in report.errors))
    if run_url:
        tail.append(f"Run: {run_url}")
    if lines and tail:
        lines.append("")
    return "\n".join(lines + tail)


# --------------------------------------------------------------------------- input


def load_sources(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"sources file not found: {path}")
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict) or not isinstance(data.get("pins"), list):
        raise ValueError(f"sources file must have a 'pins' list: {path}")
    return data["pins"]


def resolve_pins(pins: list[dict[str, Any]], repo_root: Path) -> list[dict[str, Any]]:
    """Validate every entry and attach its current ``value``. Raises InputError."""
    file_cache: dict[str, dict[str, Any]] = {}
    resolved: list[dict[str, Any]] = []
    for raw in pins:
        if not isinstance(raw, dict) or not raw.get("variable"):
            raise InputError(f"entry without 'variable': {raw!r}")
        pin = dict(raw)
        var, policy = pin["variable"], pin.get("policy")
        if policy not in POLICIES:
            raise InputError(f"{var}: unknown policy {policy!r}")
        if policy in ("lts", "latest") and not pin.get("github"):
            raise InputError(f"{var}: policy {policy} needs 'github'")
        if policy in ("lts", "support-only") and not pin.get("endoflife"):
            raise InputError(f"{var}: policy {policy} needs 'endoflife'")
        if policy == "unchecked" and not pin.get("reason"):
            raise InputError(f"{var}: policy unchecked needs 'reason'")
        rel = str(pin.get("file", ""))
        if rel not in file_cache:
            path = repo_root / rel
            if not rel or not path.is_file():
                raise InputError(f"{var}: file not found: {rel!r}")
            try:
                data = yaml.safe_load(path.read_text())
            except yaml.YAMLError as exc:
                raise InputError(f"{var}: cannot parse {rel}: {exc}") from exc
            file_cache[rel] = data if isinstance(data, dict) else {}
        if var not in file_cache[rel]:
            raise InputError(f"{var}: not assigned in {rel}")
        pin["value"] = str(file_cache[rel][var])
        resolved.append(pin)
    return resolved


# --------------------------------------------------------------------------- HTTP


def _http_get_json(url: str, token: str | None = None) -> Any:
    headers = {"Accept": "application/json", "User-Agent": "homelab-version-currency"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _http_post(url: str, body: bytes, headers: dict[str, str]) -> int:
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        return int(resp.status)


def _describe_error(exc: BaseException) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        return f"HTTP {exc.code}"
    if isinstance(exc, (socket.timeout, TimeoutError)):
        return f"timeout after {HTTP_TIMEOUT}s"
    if isinstance(exc, urllib.error.URLError):
        reason = exc.reason
        if isinstance(reason, (socket.timeout, TimeoutError)):
            return f"timeout after {HTTP_TIMEOUT}s"
        return f"unreachable: {reason}"
    if isinstance(exc, (ValueError, json.JSONDecodeError)):
        return "invalid response"
    return f"{type(exc).__name__}: {exc}"


def _run_url() -> str | None:
    server, repo, run_id = (os.environ.get(k) for k in
                            ("GITHUB_SERVER_URL", "GITHUB_REPOSITORY", "GITHUB_RUN_ID"))
    if server and repo and run_id:
        return f"{server}/{repo}/actions/runs/{run_id}"
    return None


# --------------------------------------------------------------------------- run


def collect_report(
    pins: list[dict[str, Any]],
    github_token: str | None = None,
    today: date | None = None,
    fetch: Callable[[str, str | None], Any] | None = None,
) -> CurrencyReport:
    fetch = fetch or _http_get_json
    report = CurrencyReport()
    cache: dict[str, Any] = {}

    def get(source: str, url: str, token: str | None) -> Any:
        if url not in cache:
            cache[url] = fetch(url, token)
        data = cache[url]
        if not isinstance(data, list):
            raise ValueError(f"{source}: expected a list")
        return data

    findings: list[Finding] = []
    services_vars: set[str] = set()
    for pin in pins:
        var, policy = pin["variable"], pin["policy"]
        if pin.get("file") == SERVICES_FILE:
            services_vars.add(var)
        if policy == "unchecked":
            report.unchecked.append((var, str(pin["reason"])))
            continue

        failed = False
        releases: list[dict[str, Any]] = []
        support: list[dict[str, Any]] = []
        if policy in ("lts", "latest"):
            source = f"github/{pin['github']}"
            try:
                releases = get(source, f"https://api.github.com/repos/{pin['github']}/releases?per_page=100",
                               github_token)
            except Exception as exc:  # noqa: BLE001 - every failure is reported, never swallowed
                report.errors.append((source, _describe_error(exc)))
                failed = True
        if pin.get("endoflife"):
            source = f"endoflife.date/{pin['endoflife']}"
            try:
                support = get(source, f"https://endoflife.date/api/{pin['endoflife']}.json", None)
            except Exception as exc:  # noqa: BLE001
                report.errors.append((source, _describe_error(exc)))
                failed = True
        if failed:
            continue  # a pin with a failed source is never reported as current
        findings.extend(evaluate_pin(pin, releases, support, today=today))

    findings.sort(key=lambda f: f.variable in services_vars)  # stable: monitoring pins first
    report.findings = findings
    return report


def run_check(
    sources_path: Path,
    repo_root: Path,
    dry_run: bool = False,
    today: date | None = None,
) -> CheckResult:
    ntfy_token = os.environ.get("NTFY_TOKEN")
    try:
        pins = resolve_pins(load_sources(sources_path), repo_root)
    except (FileNotFoundError, ValueError, InputError, yaml.YAMLError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return CheckResult(exit_code=2, report=CurrencyReport())
    if not dry_run and not ntfy_token:
        print("error: NTFY_TOKEN is not set (use --dry-run to skip publishing)", file=sys.stderr)
        return CheckResult(exit_code=2, report=CurrencyReport())

    report = collect_report(pins, github_token=os.environ.get("GITHUB_TOKEN"), today=today)
    message = build_message(report, today=today, run_url=_run_url())
    exit_code = 1 if report.errors else 0

    if message is None or dry_run:
        return CheckResult(exit_code=exit_code, report=report, message=message)

    url = f"{os.environ.get('NTFY_URL', DEFAULT_NTFY_URL).rstrip('/')}/" \
          f"{os.environ.get('NTFY_TOPIC', DEFAULT_NTFY_TOPIC)}"
    headers = {
        "Authorization": f"Bearer {ntfy_token}",
        "Title": build_title(report),
        "Priority": build_priority(report),
        "Tags": "package",
        "Content-Type": "text/plain; charset=utf-8",
    }
    try:
        status = _http_post(url, message.encode("utf-8"), headers)
    except Exception as exc:  # noqa: BLE001
        print(f"error: publish failed: {_describe_error(exc)}", file=sys.stderr)
        return CheckResult(exit_code=1, report=report, message=message)
    if status != 200:
        print(f"error: publish returned HTTP {status}", file=sys.stderr)
        return CheckResult(exit_code=1, report=report, message=message)
    return CheckResult(exit_code=exit_code, report=report, message=message)


def _find_repo_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / "ansible").is_dir() and (candidate / "python").is_dir():
            return candidate
    raise InputError(f"cannot locate the repository root from {start}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report version pins that are behind (spec 090)")
    parser.add_argument("--dry-run", action="store_true", help="print the report, do not publish")
    parser.add_argument("--sources", type=Path, default=None, help="path to version-sources.yml")
    parser.add_argument("--repo-root", type=Path, default=None, help="repository root")
    args = parser.parse_args(argv)

    try:
        repo_root = args.repo_root or _find_repo_root(Path.cwd().resolve())
    except InputError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    sources = args.sources or repo_root / "ansible" / "version-sources.yml"
    result = run_check(sources_path=sources, repo_root=repo_root, dry_run=args.dry_run)

    if result.message:
        print(result.message)
    elif result.exit_code == 0:
        print("All checked pins are current.")
    return result.exit_code


if __name__ == "__main__":
    sys.exit(main())
