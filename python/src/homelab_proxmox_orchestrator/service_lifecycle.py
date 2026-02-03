from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
import os
from pathlib import Path
import sys

from .exec import run_checked
from .healthcheck_runner import run_healthcheck
from .inventory import update_inventory

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


def _remove_service_from_services_playbook(*, repo_root: Path, hostname: str) -> bool:
    playbook_path = repo_root / "ansible" / "playbooks" / "services.yml"
    if not playbook_path.exists():
        return False

    lines = playbook_path.read_text(encoding="utf-8").splitlines()
    new_lines: list[str] = []
    buffer: list[str] = []
    in_block = False
    block_has_target = False

    def _flush_block() -> None:
        nonlocal buffer, block_has_target
        if not block_has_target:
            new_lines.extend(buffer)
        buffer = []
        block_has_target = False

    for line in lines:
        if line.startswith("- name:"):
            if in_block:
                _flush_block()
            in_block = True
            buffer = [line]
            block_has_target = False
            continue

        if in_block:
            buffer.append(line)
            if re.match(rf"^\s*hosts:\s*{re.escape(hostname)}\s*$", line):
                block_has_target = True
            continue

        new_lines.append(line)

    if in_block:
        _flush_block()

    if new_lines != lines:
        playbook_path.write_text("\n".join(new_lines).rstrip() + "\n", encoding="utf-8")
        return True

    return False


def remove_service(
    *,
    repo_root: Path,
    hostname: str,
    delete_host_vars: bool = True,
    remove_from_services_playbook: bool = True,
) -> Path:
    host_vars_file = repo_root / "ansible" / "host_vars" / f"{hostname}.yml"
    if not host_vars_file.exists():
        if remove_from_services_playbook:
            _remove_service_from_services_playbook(repo_root=repo_root, hostname=hostname)
        return host_vars_file

    if delete_host_vars:
        host_vars_file.unlink()
        if remove_from_services_playbook:
            _remove_service_from_services_playbook(repo_root=repo_root, hostname=hostname)
        return host_vars_file

    content = host_vars_file.read_text(encoding="utf-8")
    content = _remove_healthcheck_config(content)
    host_vars_file.write_text(content, encoding="utf-8")
    return host_vars_file


def _run_remove_checks(
    *,
    repo_root: Path,
    hostname: str,
    environment: str,
    delete_data: bool,
    confirm_data_delete: str,
) -> None:
    script = repo_root / "scripts" / "lifecycle" / "remove_checks.py"
    if not script.exists():
        raise FileNotFoundError(f"Missing removal checks script: {script}")

    argv = [sys.executable, str(script), "--service", hostname, "--environment", environment]
    if delete_data:
        argv.append("--delete-data")
    if confirm_data_delete:
        argv.extend(["--confirm-data-delete", confirm_data_delete])

    res = run_checked(argv, cwd=str(repo_root), env=dict(os.environ))
    if res.stdout:
        _print(res.stdout.rstrip("\n"))
    if res.stderr:
        _eprint(res.stderr.rstrip("\n"))
    if res.returncode != 0:
        raise RuntimeError("Removal checks failed")


def _run_gap_check(*, output_file: Path) -> None:
    if not output_file.exists():
        raise FileNotFoundError(f"Missing healthcheck output: {output_file}")
    data = json.loads(output_file.read_text(encoding="utf-8"))
    gaps = [entry for entry in data if entry.get("status") == "GAP"]
    if gaps:
        names = ", ".join(sorted({entry.get("hostname", "unknown") for entry in gaps}))
        raise RuntimeError(f"Healthcheck GAP entries detected: {names}")


def verify_removal(
    *,
    repo_root: Path,
    hostname: str,
    environment: str,
    delete_data: bool,
    confirm_data_delete: str,
) -> None:
    inventory_file = update_inventory(repo_root=repo_root)
    _print(f"Inventory regenerated: {inventory_file}")

    drift_run = run_healthcheck(repo_root=repo_root, argv=["--check-drift"])
    if drift_run.exit_code != 0:
        raise RuntimeError("healthcheck:run --check-drift failed")

    gap_run = run_healthcheck(repo_root=repo_root, argv=["--json", "--no-notify"])
    if gap_run.exit_code != 0:
        raise RuntimeError("healthcheck:run failed during GAP check")
    _run_gap_check(output_file=gap_run.output_file)

    _run_remove_checks(
        repo_root=repo_root,
        hostname=hostname,
        environment=environment,
        delete_data=delete_data,
        confirm_data_delete=confirm_data_delete,
    )


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
    remove.add_argument("--keep-host-vars", action="store_true", help="Keep host_vars file (legacy behavior)")
    remove.add_argument("--keep-playbook-entry", action="store_true", help="Keep services.yml entry (legacy behavior)")
    remove.add_argument("--verify", action="store_true", help="Run inventory + drift + removal checks")
    remove.add_argument("--environment", default="all", choices=["lab", "prod", "all"])
    remove.add_argument("--delete-data", action="store_true", help="Delete service data locations")
    remove.add_argument("--confirm-data-delete", default="", help="Required when --delete-data is set")

    delete = sub.add_parser("delete")
    delete.add_argument("hostname")
    delete.add_argument("--keep-host-vars", action="store_true", help="Keep host_vars file (legacy behavior)")
    delete.add_argument("--keep-playbook-entry", action="store_true", help="Keep services.yml entry (legacy behavior)")
    delete.add_argument("--verify", action="store_true", help="Run inventory + drift + removal checks")
    delete.add_argument("--environment", default="all", choices=["lab", "prod", "all"])
    delete.add_argument("--delete-data", action="store_true", help="Delete service data locations")
    delete.add_argument("--confirm-data-delete", default="", help="Required when --delete-data is set")

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

        if args.cmd in {"remove", "delete"}:
            out = remove_service(
                repo_root=repo_root,
                hostname=str(args.hostname),
                delete_host_vars=not bool(getattr(args, "keep_host_vars", False)),
                remove_from_services_playbook=not bool(getattr(args, "keep_playbook_entry", False)),
            )
            if out.exists():
                _print(f"Updated {out}")
            else:
                _print(f"Removed host vars for {args.hostname}")

            if bool(getattr(args, "verify", False)):
                verify_removal(
                    repo_root=repo_root,
                    hostname=str(args.hostname),
                    environment=str(getattr(args, "environment", "all")),
                    delete_data=bool(getattr(args, "delete_data", False)),
                    confirm_data_delete=str(getattr(args, "confirm_data_delete", "")),
                )
                _print("Removal verification complete")
            return 0

        _eprint("Unknown command")
        return 2
    except Exception as exc:  # noqa: BLE001
        _eprint(f"Error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
