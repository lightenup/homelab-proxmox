from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys

from .exec import run_checked


def _print(msg: str) -> None:
    sys.stdout.write(msg)
    if not msg.endswith("\n"):
        sys.stdout.write("\n")


def _eprint(msg: str) -> None:
    sys.stderr.write(msg)
    if not msg.endswith("\n"):
        sys.stderr.write("\n")


def _strip_cidr(value: str) -> str:
    return value.split("/", 1)[0]


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _strip_comments(line: str) -> str:
    if "#" in line:
        return line.split("#", 1)[0]
    return line


def _extract_service_ips(text: str) -> dict[str, str]:
    services: dict[str, str] = {}
    in_map = False
    depth = 0

    for raw_line in text.splitlines():
        line = _strip_comments(raw_line).rstrip()
        if not line.strip():
            continue

        if not in_map:
            if re.match(r"^\s*service_ips\s*=\s*{\s*$", line):
                in_map = True
                depth = 1
            continue

        depth += line.count("{")
        depth -= line.count("}")
        if depth <= 0:
            in_map = False
            continue

        match = re.match(r"^\s*([A-Za-z0-9_-]+)\s*=\s*\"([^\"]+)\"\s*$", line)
        if not match:
            match = re.match(r"^\s*([A-Za-z0-9_-]+)\s*=\s*'([^']+)'\s*$", line)
        if match:
            services[match.group(1)] = match.group(2)

    return services


def _resolve_tfvars_path(*, repo_root: Path) -> Path | None:
    tfvars_path = os.environ.get("TFVARS_PATH", "").strip()
    if tfvars_path:
        p = Path(tfvars_path)
        if p.exists():
            return p

    env = os.environ.get("ENVIRONMENT", "").strip()
    tfvars_dir = os.environ.get("TFVARS_DIR", "").strip()
    if env and tfvars_dir:
        candidate = Path(tfvars_dir) / f"{env}.tfvars"
        if candidate.exists():
            return candidate

    if env:
        candidate = repo_root / "terraform" / "environments" / f"{env}.tfvars"
        if candidate.exists():
            return candidate

    return None


def render_inventory_yaml(*, services: dict[str, str], ssh_private_key_file: str | None) -> str:
    lines: list[str] = [
        "all:",
        "  children:",
        "    services:",
        "      hosts:",
    ]

    for service_name in sorted(services.keys()):
        host_value = services[service_name]
        ip = _strip_cidr(str(host_value))
        lines.append(f"        {service_name}:")
        lines.append(f"          ansible_host: {ip}")

    lines.extend(
        [
            "      vars:",
            "        ansible_user: ansible",
            "        ansible_become: true",
        ]
    )
    if ssh_private_key_file:
        lines.append(f"        ansible_ssh_private_key_file: {ssh_private_key_file}")

    return "\n".join(lines) + "\n"


def _load_tf_output_json(*, repo_root: Path) -> str:
    if os.environ.get("ANSIBLE_INVENTORY_JSON", "").strip():
        return os.environ["ANSIBLE_INVENTORY_JSON"]

    json_path = os.environ.get("ANSIBLE_INVENTORY_JSON_PATH", "").strip()
    if json_path:
        p = Path(json_path)
        if not p.exists():
            raise FileNotFoundError(f"ANSIBLE_INVENTORY_JSON_PATH does not exist: {json_path}")
        return p.read_text(encoding="utf-8")

    # Fall back to terraform output.
    res = run_checked(
        ["terraform", "-chdir=terraform", "output", "-json", "ansible_inventory"],
        cwd=str(repo_root),
        env=dict(os.environ),
    )
    if res.returncode == 0 and res.stdout.strip():
        return res.stdout

    tfvars_path = _resolve_tfvars_path(repo_root=repo_root)
    if tfvars_path is None:
        raise RuntimeError("terraform output failed")

    services = _extract_service_ips(_read_text(tfvars_path))
    if not services:
        raise RuntimeError("terraform output failed")

    return json.dumps({"services": services}, sort_keys=True)


def update_inventory(*, repo_root: Path) -> Path:
    tf_output = _load_tf_output_json(repo_root=repo_root)
    if not tf_output.strip():
        raise ValueError("Terraform output is empty")

    data = json.loads(tf_output)
    services = data.get("services")
    if not isinstance(services, dict):
        raise ValueError("Expected JSON object with a 'services' mapping")

    inventory_dir = repo_root / "ansible" / "inventories" / "generated"
    inventory_file = inventory_dir / "hosts.yml"
    inventory_dir.mkdir(parents=True, exist_ok=True)

    ssh_key_file = os.environ.get("ANSIBLE_SSH_PRIVATE_KEY_FILE", "").strip() or None
    yaml_text = render_inventory_yaml(services=services, ssh_private_key_file=ssh_key_file)

    inventory_file.write_text(yaml_text, encoding="utf-8")
    return inventory_file


def main(argv: list[str] | None = None) -> int:
    # Keep CLI minimal: rely on env vars for inputs to remain compatible with existing callers.
    _ = argv
    try:
        repo_root = Path.cwd()
        inventory_file = update_inventory(repo_root=repo_root)
        _print(f"Inventory generated successfully: {inventory_file}")
        _print(inventory_file.read_text(encoding='utf-8').rstrip("\n"))
        return 0
    except Exception as exc:  # noqa: BLE001
        _eprint(f"Error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
