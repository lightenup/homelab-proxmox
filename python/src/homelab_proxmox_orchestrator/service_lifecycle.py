from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
import sys


def _print(msg: str) -> None:
    sys.stdout.write(msg)
    if not msg.endswith("\n"):
        sys.stdout.write("\n")


def _eprint(msg: str) -> None:
    sys.stderr.write(msg)
    if not msg.endswith("\n"):
        sys.stderr.write("\n")


def _sanitize_yaml_string(value: str) -> str:
    # Minimal quoting/escaping to preserve the legacy behavior.
    return value.replace('"', '\\"')


def _remove_healthcheck_config(content: str) -> str:
    # Remove healthcheck_url block (key + indented lines)
    content = re.sub(r"^healthcheck_url:\s*\n(\s+.*\n)*", "", content, flags=re.MULTILINE)
    # Remove flat healthcheck keys
    content = re.sub(r"^healthcheck_\w+:.*\n?", "", content, flags=re.MULTILINE)
    # Clean up multiple newlines
    content = re.sub(r"\n{3,}", "\n\n", content)
    content = content.rstrip() + "\n"
    return content


def _append_healthcheck_config(
    *,
    content: str,
    scheme: str,
    port: str,
    path: str,
    profile: str,
    verify_ssl: str,
    expect_status: str,
    verification_command: str,
) -> str:
    new_config = (
        "\n"
        "healthcheck_url:\n"
        f"  scheme: {scheme}\n"
        f"  port: {port}\n"
        f"  path: {path}\n"
        f"healthcheck_profile: {profile}\n"
        f"healthcheck_verify_ssl: {verify_ssl}\n"
        f"healthcheck_expect_status: {expect_status}\n"
    )

    if profile == "none" and verification_command:
        new_config += f"healthcheck_verification_command: \"{_sanitize_yaml_string(verification_command)}\"\n"

    return content + new_config


@dataclass(frozen=True)
class ServiceConfig:
    scheme: str = "http"
    port: str = "80"
    path: str = "/"
    profile: str = "both"
    verify_ssl: str = "true"
    expect_status: str = "200"
    verification_command: str = ""


def add_service(*, repo_root: Path, hostname: str, cfg: ServiceConfig) -> Path:
    host_vars_dir = repo_root / "ansible" / "host_vars"
    host_vars_dir.mkdir(parents=True, exist_ok=True)

    host_vars_file = host_vars_dir / f"{hostname}.yml"

    if host_vars_file.exists():
        content = host_vars_file.read_text(encoding="utf-8")
    else:
        content = "---\n"

    content = _remove_healthcheck_config(content)
    content = _append_healthcheck_config(
        content=content,
        scheme=cfg.scheme,
        port=cfg.port,
        path=cfg.path,
        profile=cfg.profile,
        verify_ssl=cfg.verify_ssl,
        expect_status=cfg.expect_status,
        verification_command=cfg.verification_command,
    )

    host_vars_file.write_text(content, encoding="utf-8")
    return host_vars_file


def change_service(*, repo_root: Path, hostname: str, cfg: ServiceConfig) -> Path:
    host_vars_file = repo_root / "ansible" / "host_vars" / f"{hostname}.yml"
    if not host_vars_file.exists():
        raise FileNotFoundError(
            f"Service {hostname} does not exist (file {host_vars_file} missing). Use service:add to create a new service."
        )

    return add_service(repo_root=repo_root, hostname=hostname, cfg=cfg)


def remove_service(*, repo_root: Path, hostname: str) -> Path:
    host_vars_file = repo_root / "ansible" / "host_vars" / f"{hostname}.yml"
    if not host_vars_file.exists():
        raise FileNotFoundError(f"File {host_vars_file} does not exist.")

    content = host_vars_file.read_text(encoding="utf-8")
    content = _remove_healthcheck_config(content)
    host_vars_file.write_text(content, encoding="utf-8")
    return host_vars_file


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="service")
    sub = p.add_subparsers(dest="cmd", required=True)

    def _add_common_flags(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("hostname")
        sp.add_argument("--scheme", default="http")
        sp.add_argument("--port", default="80")
        sp.add_argument("--path", dest="path_val", default="/")
        sp.add_argument("--profile", default="both")
        sp.add_argument("--verify-ssl", default="true")
        sp.add_argument("--expect-status", default="200")
        sp.add_argument("--verification-command", default="")

    add = sub.add_parser("add")
    _add_common_flags(add)

    change = sub.add_parser("change")
    _add_common_flags(change)

    remove = sub.add_parser("remove")
    remove.add_argument("hostname")

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = Path.cwd()

    try:
        if args.cmd == "add":
            out = add_service(
                repo_root=repo_root,
                hostname=str(args.hostname),
                cfg=ServiceConfig(
                    scheme=str(args.scheme),
                    port=str(args.port),
                    path=str(args.path_val),
                    profile=str(args.profile),
                    verify_ssl=str(args.verify_ssl),
                    expect_status=str(args.expect_status),
                    verification_command=str(args.verification_command),
                ),
            )
            _print(f"Successfully updated {out}")
            return 0

        if args.cmd == "change":
            out = change_service(
                repo_root=repo_root,
                hostname=str(args.hostname),
                cfg=ServiceConfig(
                    scheme=str(args.scheme),
                    port=str(args.port),
                    path=str(args.path_val),
                    profile=str(args.profile),
                    verify_ssl=str(args.verify_ssl),
                    expect_status=str(args.expect_status),
                    verification_command=str(args.verification_command),
                ),
            )
            _print(f"Successfully updated {out}")
            return 0

        if args.cmd == "remove":
            out = remove_service(repo_root=repo_root, hostname=str(args.hostname))
            _print(f"Removed healthcheck configuration from {out}")
            return 0

        _eprint("Unknown command")
        return 2
    except Exception as exc:  # noqa: BLE001
        _eprint(f"Error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
