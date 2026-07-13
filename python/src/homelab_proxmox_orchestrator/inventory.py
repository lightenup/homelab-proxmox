from __future__ import annotations

import json
import os
from pathlib import Path
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


def render_inventory_yaml(*, services: dict[str, str], ssh_private_key_file: str | None) -> str:
    # Connection vars are emitted per-host (not at the group level) so that when this
    # generated inventory is layered after a committed environment inventory (the monitoring
    # deploy adds `-i inventories/prod/hosts.yml -i inventories/generated/hosts.yml` to make
    # other services' monitoring_contract available via hostvars), the generated host-level
    # connection vars win by precedence. Otherwise the committed inventory's host-level
    # `ansible_user: root` would override a group-level default and the deploy would connect
    # as root instead of the CI user.
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
        lines.append("          ansible_user: ansible")
        lines.append("          ansible_become: true")
        if ssh_private_key_file:
            lines.append(f"          ansible_ssh_private_key_file: {ssh_private_key_file}")

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
    if res.returncode != 0:
        raise RuntimeError("terraform output failed")

    return res.stdout


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
