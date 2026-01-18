#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import shutil
from pathlib import Path
import sys

ALLOWED_DATA_ROOTS = (
    "/mnt/",
    "/volume/",
    "/srv/",
    "/data/",
)


def _print(msg: str) -> None:
    sys.stdout.write(msg)
    if not msg.endswith("\n"):
        sys.stdout.write("\n")


def _eprint(msg: str) -> None:
    sys.stderr.write(msg)
    if not msg.endswith("\n"):
        sys.stderr.write("\n")


def _find_repo_root(start: Path) -> Path:
    current = start
    for _ in range(20):
        if (current / "Taskfile.yml").exists() and (current / "python").exists():
            return current
        current = current.parent
    raise RuntimeError("Unable to locate repository root (expected Taskfile.yml + python/)")


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _strip_comments(line: str) -> str:
    if "#" in line:
        return line.split("#", 1)[0]
    return line


def _extract_map_keys(text: str, map_name: str) -> set[str]:
    keys: set[str] = set()
    in_map = False
    depth = 0

    for raw_line in text.splitlines():
        line = _strip_comments(raw_line).rstrip()
        if not line.strip():
            continue
        if not in_map:
            if re.match(rf"^\s*{re.escape(map_name)}\s*=\s*{{\s*$", line):
                in_map = True
                depth = 1
            continue

        depth += line.count("{")
        depth -= line.count("}")
        if depth <= 0:
            in_map = False
            continue

        key_match = re.match(r"^\s*([A-Za-z0-9_-]+)\s*=\s*", line)
        if key_match:
            keys.add(key_match.group(1))

    return keys


def _extract_service_mountpoints(text: str, service: str) -> list[str]:
    volumes: list[str] = []
    in_map = False
    in_service = False
    depth = 0
    service_depth = 0

    for raw_line in text.splitlines():
        line = _strip_comments(raw_line).rstrip()
        if not line.strip():
            continue

        if not in_map:
            if re.match(r"^\s*service_mountpoints\s*=\s*{\s*$", line):
                in_map = True
                depth = 1
            continue

        depth += line.count("{")
        depth -= line.count("}")
        if depth <= 0:
            in_map = False
            in_service = False
            continue

        if not in_service:
            if re.match(rf"^\s*{re.escape(service)}\s*=\s*{{\s*$", line):
                in_service = True
                service_depth = depth
            continue

        if in_service and depth < service_depth:
            in_service = False
            continue

        if in_service:
            match = re.match(r"^\s*volume\s*=\s*\"([^\"]+)\"\s*$", line)
            if not match:
                match = re.match(r"^\s*volume\s*=\s*'([^']+)'\s*$", line)
            if match:
                volumes.append(match.group(1))

    return volumes


def _check_tfvars(
    *,
    tfvars_path: Path,
    service: str,
    errors: list[str],
) -> list[str]:
    if not tfvars_path.exists():
        return []

    text = _read_text(tfvars_path)
    service_ips_keys = _extract_map_keys(text, "service_ips")
    if service in service_ips_keys:
        errors.append(f"service_ips contains '{service}' in {tfvars_path}")

    mountpoints_keys = _extract_map_keys(text, "service_mountpoints")
    if service in mountpoints_keys:
        errors.append(f"service_mountpoints contains '{service}' in {tfvars_path}")

    return _extract_service_mountpoints(text, service)


def _check_allowlisted_path(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in ALLOWED_DATA_ROOTS)


def _delete_data_locations(*, volumes: list[str], confirm_token: str | None) -> list[str]:
    if not volumes:
        return []

    if confirm_token != "delete-data":
        return ["Data deletion confirmation missing. Provide --confirm-data-delete delete-data to proceed."]

    errors: list[str] = []
    for raw in volumes:
        target = Path(raw).expanduser()
        if not _check_allowlisted_path(str(target)):
            errors.append(f"Refusing to delete data outside allowed roots: {target}")
            continue
        if not target.exists():
            continue
        try:
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Failed to delete {target}: {exc}")

    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate service removal cleanup")
    parser.add_argument("--service", required=True)
    parser.add_argument("--environment", choices=["lab", "prod", "all"], default="all")
    parser.add_argument("--confirm-data-delete", dest="confirm_data_delete", default="")
    parser.add_argument("--delete-data", action="store_true")
    args = parser.parse_args(argv)

    service = str(args.service)
    repo_root = _find_repo_root(Path.cwd())

    errors: list[str] = []

    terraform_root = repo_root / "terraform"
    tf_main = terraform_root / "main.tf"
    tf_outputs = terraform_root / "outputs.tf"
    service_tf_root = terraform_root / "services" / service

    if service_tf_root.exists():
        errors.append(f"Terraform service root still present: {service_tf_root}")

    for tf_path in (tf_main, tf_outputs):
        if tf_path.exists():
            text = _read_text(tf_path)
            if re.search(rf"\b{re.escape(service)}\b", text):
                errors.append(f"Found '{service}' in {tf_path}")

    env_paths = []
    if args.environment in {"lab", "all"}:
        env_paths.append(terraform_root / "environments" / "lab.tfvars")
    if args.environment in {"prod", "all"}:
        env_paths.append(terraform_root / "environments" / "prod.tfvars")

    data_locations: list[str] = []
    for tfvars_path in env_paths:
        data_locations.extend(_check_tfvars(tfvars_path=tfvars_path, service=service, errors=errors))

    host_vars_file = repo_root / "ansible" / "host_vars" / f"{service}.yml"
    if host_vars_file.exists():
        errors.append(f"Host vars still present: {host_vars_file}")

    services_playbook = repo_root / "ansible" / "playbooks" / "services.yml"
    if services_playbook.exists():
        text = _read_text(services_playbook)
        if re.search(rf"^\s*hosts:\s*{re.escape(service)}\s*$", text, flags=re.MULTILINE):
            errors.append(f"Service still referenced in {services_playbook}")

    service_playbook = repo_root / "ansible" / "playbooks" / f"{service}.yml"
    if service_playbook.exists():
        errors.append(f"Service playbook still present: {service_playbook}")

    service_role = repo_root / "ansible" / "roles" / service
    if service_role.exists():
        errors.append(f"Service role still present: {service_role}")

    reverse_proxy_template = repo_root / "ansible" / "roles" / "reverse_proxy" / "templates" / f"{service}.caddy.j2"
    if reverse_proxy_template.exists():
        errors.append(f"Reverse proxy template still present: {reverse_proxy_template}")

    reverse_proxy_tasks = repo_root / "ansible" / "roles" / "reverse_proxy" / "tasks" / "main.yml"
    if reverse_proxy_tasks.exists():
        text = _read_text(reverse_proxy_tasks)
        if re.search(rf"\b{re.escape(service)}\b", text):
            errors.append(f"Reverse proxy tasks still reference '{service}' in {reverse_proxy_tasks}")

    reverse_proxy_doc = repo_root / "docs" / "reverse-proxy.md"
    if reverse_proxy_doc.exists():
        text = _read_text(reverse_proxy_doc)
        if re.search(rf"\b{re.escape(service)}\b", text):
            errors.append(f"Reverse proxy documentation still references '{service}' in {reverse_proxy_doc}")

    inventory_file = repo_root / "ansible" / "inventories" / "generated" / "hosts.yml"
    if inventory_file.exists():
        text = _read_text(inventory_file)
        if re.search(rf"^\s*{re.escape(service)}:\s*$", text, flags=re.MULTILINE):
            errors.append(f"Inventory still contains '{service}' in {inventory_file}")

    if data_locations:
        if args.delete_data:
            delete_errors = _delete_data_locations(volumes=data_locations, confirm_token=args.confirm_data_delete)
            errors.extend(delete_errors)

            for raw in data_locations:
                path = Path(raw).expanduser()
                if path.exists():
                    errors.append(f"Data location still exists after deletion attempt: {path}")
        else:
            errors.append(
                "Service has data locations that must be removed. "
                "Re-run with --delete-data and --confirm-data-delete delete-data to remove: "
                + ", ".join(sorted(set(data_locations)))
            )

    if errors:
        _eprint("Removal validation failed:")
        for err in errors:
            _eprint(f"- {err}")
        return 2

    _print("Removal validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
