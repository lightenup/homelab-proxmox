from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

from .exec import run_checked
from .healthcheck_runner import run_healthcheck
from .inventory import update_inventory
from .service_lifecycle import main as service_main


def _is_fake_mode() -> bool:
    return os.environ.get("HOMELAB_PROXMOX_OPS_FAKE", "").strip() in {"1", "true", "yes"}


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


def _run_repo_command(repo_root: Path, argv: list[str]) -> int:
    res = run_checked(argv, cwd=str(repo_root), env=dict(os.environ))
    if res.stdout:
        sys.stdout.write(res.stdout)
        if not res.stdout.endswith("\n"):
            sys.stdout.write("\n")
    if res.stderr:
        sys.stderr.write(res.stderr)
        if not res.stderr.endswith("\n"):
            sys.stderr.write("\n")
    return int(res.returncode)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="homelab-proxmox-ops")
    sub = p.add_subparsers(dest="command", required=True)

    service = sub.add_parser("service")
    service_sub = service.add_subparsers(dest="service_cmd", required=True)
    for cmd in ("add", "change", "remove"):
        p_cmd = service_sub.add_parser(cmd)
        p_cmd.add_argument("args", nargs=argparse.REMAINDER, help="Args forwarded to legacy script")

    inventory = sub.add_parser("inventory")
    inventory_sub = inventory.add_subparsers(dest="inventory_cmd", required=True)
    inv_update = inventory_sub.add_parser("update")
    inv_update.add_argument("args", nargs=argparse.REMAINDER, help="Args forwarded to legacy script")

    healthcheck = sub.add_parser("healthcheck")
    healthcheck_sub = healthcheck.add_subparsers(dest="healthcheck_cmd", required=True)
    hc_run = healthcheck_sub.add_parser("run")
    hc_run.add_argument("args", nargs=argparse.REMAINDER, help="Args forwarded to legacy script")

    terraform = sub.add_parser("terraform")
    terraform_sub = terraform.add_subparsers(dest="terraform_cmd", required=True)
    tf_validate = terraform_sub.add_parser("validate")
    tf_validate.add_argument("args", nargs=argparse.REMAINDER, help="Args forwarded to legacy script")
    tf_plan = terraform_sub.add_parser("plan")
    tf_plan.add_argument("args", nargs=argparse.REMAINDER, help="Args forwarded to legacy script")
    tf_apply = terraform_sub.add_parser("apply")
    tf_apply.add_argument("--confirm", action="store_true", help="Required to run apply")
    tf_apply.add_argument("args", nargs=argparse.REMAINDER, help="Args forwarded to legacy script")

    deploy = sub.add_parser("deploy")
    deploy_sub = deploy.add_subparsers(dest="deploy_cmd", required=True)
    deploy_lab = deploy_sub.add_parser("lab")
    deploy_lab.add_argument("args", nargs=argparse.REMAINDER, help="Args forwarded to legacy script")

    summary = sub.add_parser("summary")
    summary_sub = summary.add_subparsers(dest="summary_cmd", required=True)
    summary_render = summary_sub.add_parser("render")
    summary_render.add_argument("--evidence-pack", required=False)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    fake = _is_fake_mode()
    repo_root = _find_repo_root(Path.cwd())

    # Service lifecycle
    if args.command == "service":
        task = f"service:{args.service_cmd}"
        if fake:
            _print(f"FAKE {task}: ok")
            return 0
        forwarded = list(getattr(args, "args", []) or [])
        if forwarded and forwarded[0] == "--":
            forwarded = forwarded[1:]

        # Delegate to Python implementation (arg contract matches the legacy scripts).
        return int(service_main([args.service_cmd, *forwarded]))

    # Inventory
    if args.command == "inventory" and args.inventory_cmd == "update":
        if fake:
            _print("FAKE inventory:update: ok")
            return 0

        forwarded = list(getattr(args, "args", []) or [])
        if forwarded and forwarded[0] == "--":
            forwarded = forwarded[1:]
        if forwarded:
            _print("inventory:update does not accept positional args; use env vars (ANSIBLE_INVENTORY_JSON/ANSIBLE_INVENTORY_JSON_PATH/ANSIBLE_SSH_PRIVATE_KEY_FILE).")
            return 2

        try:
            inventory_file = update_inventory(repo_root=repo_root)
        except Exception as exc:  # noqa: BLE001
            _eprint(f"inventory:update failed: {exc}")
            return 2

        _print(f"Inventory generated successfully: {inventory_file}")
        return 0

    # Healthcheck
    if args.command == "healthcheck" and args.healthcheck_cmd == "run":
        if fake:
            _print("FAKE healthcheck:run: ok")
            return 0
        forwarded = list(getattr(args, "args", []) or [])
        if forwarded and forwarded[0] == "--":
            forwarded = forwarded[1:]

        try:
            r = run_healthcheck(repo_root=repo_root, argv=forwarded)
        except Exception as exc:  # noqa: BLE001
            _eprint(f"healthcheck:run failed: {exc}")
            return 2

        return int(r.exit_code)

    # Terraform
    if args.command == "terraform":
        task = f"terraform:{args.terraform_cmd}"

        if args.terraform_cmd == "apply" and not bool(getattr(args, "confirm", False)):
            _print(
                "terraform:apply requires explicit confirmation. Re-run with --confirm (or use: task terraform:apply CONFIRM=yes -- [args])."
            )
            return 2

        if fake:
            _print(f"FAKE {task}: ok")
            return 0

        if args.terraform_cmd == "validate":
            script = repo_root / "scripts" / "ci" / "terraform-validate.sh"
            if not script.exists():
                _eprint(f"Missing terraform validate script: {script}")
                return 2

            forwarded = list(getattr(args, "args", []) or [])
            if forwarded and forwarded[0] == "--":
                forwarded = forwarded[1:]
            return _run_repo_command(repo_root, [str(script), *forwarded])

        _print(
            f"{task} is not yet wired to a safe local implementation. "
            "Use the existing lab/prod deploy workflows (GitHub Actions) or run scripts/lab/pve-service-deploy on PVE."
        )
        return 2

    # Deploy
    if args.command == "deploy" and args.deploy_cmd == "lab":
        if fake:
            _print("FAKE deploy:lab: ok")
            return 0
        _print(
            "deploy:lab is not implemented locally yet. "
            "Use the GitHub Actions lab deploy workflow or run scripts/lab/pve-service-deploy on the Proxmox host."
        )
        return 2

    # Summary
    if args.command == "summary" and args.summary_cmd == "render":
        evidence_pack = str(getattr(args, "evidence_pack", "") or "")
        if fake:
            _print(f"FAKE summary:render: ok (evidence-pack={evidence_pack or 'N/A'})")
            return 0
        if not evidence_pack:
            _print("summary:render requires --evidence-pack")
            return 2

        from .cli import main as cli_main

        return int(cli_main(["summary", "--evidence-pack", evidence_pack]))

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
