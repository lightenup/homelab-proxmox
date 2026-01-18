from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import sys
import tempfile

from .exec import run_checked


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


def _load_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    out: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        key = k.strip()
        value = v.strip().strip('"').strip("'")
        if key:
            out[key] = value
    return out


def _safe_symlink_latest(*, latest_link: Path, target: Path) -> None:
    try:
        if latest_link.is_symlink() or latest_link.exists():
            latest_link.unlink()
    except FileNotFoundError:
        pass
    latest_link.symlink_to(target.name)


def _rotate_history(*, history_dir: Path, keep: int = 50) -> None:
    json_files = [p for p in history_dir.glob("*.json") if p.name != "latest.json"]
    json_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    for p in json_files[keep:]:
        try:
            p.unlink()
        except FileNotFoundError:
            continue


@dataclass(frozen=True)
class HealthcheckRun:
    output_file: Path
    exit_code: int


def run_healthcheck(
    *,
    repo_root: Path,
    argv: list[str],
    timestamp: str | None = None,
) -> HealthcheckRun:
    # Mirrors scripts/healthcheck/run.sh behavior while running via Python.
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--profile", default="lan")
    p.add_argument("--inventory", default="")
    known, rest = p.parse_known_args(argv)

    profile = str(known.profile)
    inventory = str(known.inventory)

    scripts_dir = repo_root / "scripts" / "healthcheck"
    hc_script = scripts_dir / "healthcheck.py"
    if not hc_script.exists():
        raise FileNotFoundError(f"Missing healthcheck script: {hc_script}")

    history_dir = repo_root / "artifacts" / "healthcheck" / "history"
    history_dir.mkdir(parents=True, exist_ok=True)

    ts = timestamp or datetime.now().strftime("%Y%m%d-%H%M%S")
    output_file = history_dir / f"{ts}.json"

    cmd_args = [
        str(hc_script),
        "--profile",
        profile,
        "--output-json",
        str(output_file),
    ]
    if inventory:
        cmd_args.extend(["--inventory", inventory])

    env = dict(os.environ)
    temp_pw_path: str | None = None
    if not env.get("ANSIBLE_VAULT_PASSWORD_FILE", "").strip():
        default_vault_path = env.get(
            "PVE_VAULT_PASSWORD_FILE",
            "/var/lib/homelab-proxmox/vault/.ansible_vault_pass",
        )
        if Path(default_vault_path).exists():
            env["ANSIBLE_VAULT_PASSWORD_FILE"] = default_vault_path

    if not env.get("ANSIBLE_VAULT_PASSWORD_FILE", "").strip():
        raw_pw = env.get("ANSIBLE_VAULT_PASSWORD", "").strip()
        if raw_pw:
            handle = tempfile.NamedTemporaryFile(prefix="ansible-vault-", delete=False)
            temp_pw_path = handle.name
            handle.write(raw_pw.encode("utf-8"))
            handle.flush()
            handle.close()
            os.chmod(temp_pw_path, 0o600)
            env["ANSIBLE_VAULT_PASSWORD_FILE"] = temp_pw_path

    if env.get("ANSIBLE_VAULT_PASSWORD_FILE", "").strip() and not env.get(
        "ANSIBLE_VAULT_IDENTITY_LIST", ""
    ).strip():
        vault_id = env.get("VAULT_ID", "").strip() or env.get("ENVIRONMENT", "").strip()
        vault_file = env["ANSIBLE_VAULT_PASSWORD_FILE"]
        default_entry = f"default@{vault_file}"
        if vault_id and vault_id != "default":
            env["ANSIBLE_VAULT_IDENTITY_LIST"] = f"{default_entry},{vault_id}@{vault_file}"
        else:
            env["ANSIBLE_VAULT_IDENTITY_LIST"] = default_entry

    env.update(_load_env_file(scripts_dir / ".env"))

    try:
        res = run_checked(cmd_args + list(rest), cwd=str(repo_root), env=env)
    finally:
        if temp_pw_path:
            try:
                Path(temp_pw_path).unlink()
            except FileNotFoundError:
                pass

    if res.stdout:
        sys.stdout.write(res.stdout)
        if not res.stdout.endswith("\n"):
            sys.stdout.write("\n")
    if res.stderr:
        sys.stderr.write(res.stderr)
        if not res.stderr.endswith("\n"):
            sys.stderr.write("\n")

    _safe_symlink_latest(latest_link=history_dir / "latest.json", target=output_file)
    _rotate_history(history_dir=history_dir, keep=50)

    return HealthcheckRun(output_file=output_file, exit_code=int(res.returncode))


def main(argv: list[str] | None = None) -> int:
    args = list(argv or sys.argv[1:])
    repo_root = _find_repo_root(Path.cwd())

    _print("Running healthchecks...")
    try:
        r = run_healthcheck(repo_root=repo_root, argv=args)
    except Exception as exc:  # noqa: BLE001
        _eprint(f"healthcheck:run failed: {exc}")
        return 2

    return int(r.exit_code)


if __name__ == "__main__":
    raise SystemExit(main())
