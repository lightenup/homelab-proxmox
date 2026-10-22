from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import yaml

HTTP_TIMEOUT = 20
SUPPORT_ENDING_DAYS = 90


@dataclass
class Finding:
    variable: str
    pinned: str
    kind: str
    available: str | None = None
    eol: str | None = None


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


def parse_version_tag(tag: str) -> tuple[int, int, int] | None:
    if not tag:
        return None
    cleaned = tag.lstrip("v")
    m = re.match(r"^(\d+)(?:\.(\d+))?(?:\.(\d+))?", cleaned)
    if not m or not any(m.groups()):
        return None
    major = int(m.group(1))
    minor = int(m.group(2)) if m.group(2) else 0
    patch = int(m.group(3)) if m.group(3) else 0
    return (major, minor, patch)


def is_prerelease_tag(tag: str, github_prerelease: bool) -> bool:
    if github_prerelease:
        return True
    lowered = tag.lower()
    for marker in ("-rc", "-beta", "-alpha"):
        if marker in lowered:
            return True
    return False


def compare_versions(a: tuple[int, int, int], b: tuple[int, int, int]) -> int:
    if a > b:
        return 1
    if a < b:
        return -1
    return 0


def load_sources(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"sources file not found: {path}")
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict) or "pins" not in data:
        raise ValueError(f"sources file missing 'pins' key: {path}")
    pins = data["pins"]
    if not isinstance(pins, list):
        raise ValueError(f"'pins' must be a list: {path}")
    return pins


def _http_get_json(url: str, headers: dict[str, str] | None = None) -> Any:
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _http_post(url: str, body: bytes, headers: dict[str, str]) -> int:
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        return resp.status


def _fetch_releases(github_repo: str, token: str | None) -> list[dict[str, Any]]:
    url = f"https://api.github.com/repos/{github_repo}/releases?per_page=30"
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return _http_get_json(url, headers)


def _fetch_endoflife(product: str) -> list[dict[str, Any]]:
    url = f"https://endoflife.date/api/{product}.json"
    return _http_get_json(url)


def _parse_eol(eol: Any) -> date | None:
    if eol is False or eol is None:
        return None
    if isinstance(eol, str):
        return date.fromisoformat(eol)
    return None


def evaluate_pin(
    pin: dict[str, Any],
    releases: list[dict[str, Any]],
    support_lines: list[dict[str, Any]],
    today: date | None = None,
) -> list[Finding]:
    if today is None:
        today = date.today()

    policy = pin.get("policy", "unchecked")
    if policy == "unchecked":
        return []

    pinned_value = pin.get("value", "")
    pinned_core = parse_version_tag(pinned_value)
    if pinned_core is None:
        return []

    findings: list[Finding] = []

    if policy in ("lts", "latest"):
        stable_releases = [
            r for r in releases
            if not is_prerelease_tag(r.get("tag_name", ""), r.get("prerelease", False))
        ]
        best: tuple[int, int, int] | None = None
        best_tag: str | None = None
        for r in stable_releases:
            core = parse_version_tag(r.get("tag_name", ""))
            if core is None:
                continue
            if best is None or compare_versions(core, best) > 0:
                best = core
                best_tag = r.get("tag_name", "")

        if best is not None and best_tag is not None:
            if compare_versions(best, pinned_core) > 0:
                if best[:2] == pinned_core[:2]:
                    findings.append(Finding(
                        variable=pin["variable"],
                        pinned=pinned_value,
                        kind="newer-patch",
                        available=best_tag,
                    ))
                else:
                    findings.append(Finding(
                        variable=pin["variable"],
                        pinned=pinned_value,
                        kind="newer-release",
                        available=best_tag,
                    ))

    if policy in ("lts", "support-only", "latest") and support_lines:
        pinned_cycle = f"{pinned_core[0]}.{pinned_core[1]}" if pinned_core[1] else str(pinned_core[0])
        for line in support_lines:
            cycle = str(line.get("cycle", ""))
            if cycle == pinned_cycle or cycle == str(pinned_core[0]):
                eol = _parse_eol(line.get("eol"))
                if eol is not None:
                    if eol < today:
                        findings.append(Finding(
                            variable=pin["variable"],
                            pinned=pinned_value,
                            kind="support-ended",
                            eol=eol.isoformat(),
                        ))
                    elif (eol - today).days <= SUPPORT_ENDING_DAYS:
                        findings.append(Finding(
                            variable=pin["variable"],
                            pinned=pinned_value,
                            kind="support-ending",
                            eol=eol.isoformat(),
                        ))
                break

    return findings


def build_message(report: CurrencyReport) -> str | None:
    if not report.findings and not report.errors:
        return None

    lines: list[str] = []
    for f in report.findings:
        if f.kind in ("newer-patch", "newer-release"):
            suffix = " (newer patch on LTS)" if f.kind == "newer-patch" else " (newer release)"
            lines.append(f"{f.variable} {f.pinned} -> {f.available}{suffix}")
        elif f.kind == "support-ended":
            lines.append(f"{f.variable} {f.pinned}: support ended {f.eol}")
        elif f.kind == "support-ending":
            days = (date.fromisoformat(f.eol) - date.today()).days if f.eol else "?"
            lines.append(f"{f.variable} {f.pinned}: support ends {f.eol} (in {days} days)")
        elif f.kind == "newer-lts-line":
            lines.append(f"{f.variable} {f.pinned} -> {f.available} (newer LTS line)")

    if report.unchecked:
        unchecked_str = ", ".join(f"{v} ({r})" for v, r in report.unchecked)
        lines.append(f"\nNot checked: {unchecked_str}")

    if report.errors:
        err_str = "; ".join(f"{src}: {msg}" for src, msg in report.errors)
        lines.append(f"Check errors: {err_str}")

    return "\n".join(lines)


def _find_repo_root(start: Path) -> Path:
    current = start
    for _ in range(20):
        if (current / ".git").exists() and (current / "python").exists():
            return current
        if (current / "Taskfile.yml").exists() and (current / "python").exists():
            return current
        current = current.parent
    raise RuntimeError("Unable to locate repository root")


def run_check(
    sources_path: Path,
    repo_root: Path,
    dry_run: bool = False,
    ntfy_url: str | None = None,
    ntfy_topic: str | None = None,
) -> CheckResult:
    ntfy_url = ntfy_url or os.environ.get("NTFY_URL", "https://ntfy.hus-sky.no")
    ntfy_topic = ntfy_topic or os.environ.get("NTFY_TOPIC", "versions")
    ntfy_token = os.environ.get("NTFY_TOKEN")
    github_token = os.environ.get("GITHUB_TOKEN")

    if not dry_run and not ntfy_token:
        return CheckResult(exit_code=2, report=CurrencyReport())

    try:
        pins = load_sources(sources_path)
    except (FileNotFoundError, ValueError) as e:
        return CheckResult(exit_code=2, report=CurrencyReport(errors=[("sources", str(e))]))

    report = CurrencyReport()
    monitoring_vars = {
        "prometheus_version", "grafana_version", "telegraf_version",
        "alertmanager_version", "blackbox_exporter_version", "node_exporter_version",
    }

    for pin in pins:
        var = pin.get("variable", "")
        policy = pin.get("policy", "unchecked")

        if policy == "unchecked":
            report.unchecked.append((var, pin.get("reason", "not checked")))
            continue

        file_path = repo_root / pin.get("file", "")
        if not file_path.exists():
            report.errors.append((var, f"file not found: {pin.get('file')}"))
            continue

        try:
            file_data = yaml.safe_load(file_path.read_text())
        except Exception as e:
            report.errors.append((var, f"cannot parse {pin.get('file')}: {e}"))
            continue

        if not isinstance(file_data, dict) or var not in file_data:
            report.errors.append((var, f"variable not found in {pin.get('file')}"))
            continue

        pin["value"] = str(file_data[var])

        releases: list[dict[str, Any]] = []
        support_lines: list[dict[str, Any]] = []

        if policy in ("lts", "latest") and "github" in pin:
            try:
                releases = _fetch_releases(pin["github"], github_token)
            except Exception as e:
                report.errors.append((f"github/{pin['github']}", str(e)))

        if policy in ("lts", "support-only") and "endoflife" in pin:
            try:
                support_lines = _fetch_endoflife(pin["endoflife"])
            except Exception as e:
                report.errors.append((f"endoflife.date/{pin['endoflife']}", str(e)))
        elif policy == "latest" and "endoflife" in pin:
            try:
                support_lines = _fetch_endoflife(pin["endoflife"])
            except Exception as e:
                report.errors.append((f"endoflife.date/{pin['endoflife']}", str(e)))

        pin_findings = evaluate_pin(pin, releases, support_lines)
        for f in pin_findings:
            f.variable = var
        report.findings.extend(pin_findings)

    report.findings.sort(key=lambda f: (f.variable not in monitoring_vars, f.variable))

    message = build_message(report)

    if not report.findings and not report.errors:
        return CheckResult(exit_code=0, report=report, message=None)

    if dry_run:
        return CheckResult(exit_code=0, report=report, message=message)

    if message is None:
        return CheckResult(exit_code=0, report=report, message=None)

    title_parts = []
    if report.findings:
        title_parts.append(f"{len(report.findings)} behind")
    if report.errors:
        title_parts.append(f"{len(report.errors)} check errors")
    title = f"Version pins: {', '.join(title_parts)}"

    has_severe = any(
        f.kind in ("support-ended",) for f in report.findings
    ) or bool(report.errors)
    priority = "4" if has_severe else "3"

    headers = {
        "Authorization": f"Bearer {ntfy_token}",
        "Title": title,
        "Priority": priority,
        "Tags": "package",
        "Content-Type": "text/plain",
    }

    try:
        status = _http_post(f"{ntfy_url}/{ntfy_topic}", message.encode("utf-8"), headers)
        if status != 200:
            report.errors.append(("ntfy", f"publish returned {status}"))
            return CheckResult(exit_code=1, report=report, message=message)
    except Exception as e:
        report.errors.append(("ntfy", str(e)))
        return CheckResult(exit_code=1, report=report, message=message)

    exit_code = 1 if report.errors else 0
    return CheckResult(exit_code=exit_code, report=report, message=message)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check version pin currency")
    parser.add_argument("--dry-run", action="store_true", help="Print report, do not publish")
    parser.add_argument("--sources", type=Path, default=None, help="Path to version-sources.yml")
    parser.add_argument("--repo-root", type=Path, default=None, help="Repository root")
    args = parser.parse_args()

    repo_root = args.repo_root or _find_repo_root(Path.cwd())
    sources = args.sources or repo_root / "ansible" / "version-sources.yml"

    result = run_check(
        sources_path=sources,
        repo_root=repo_root,
        dry_run=args.dry_run,
    )

    if result.message:
        print(result.message)

    return result.exit_code


if __name__ == "__main__":
    sys.exit(main())
