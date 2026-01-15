from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import shutil
import sys
from datetime import datetime, timezone


def _print(msg: str) -> None:
    sys.stdout.write(msg)
    if not msg.endswith("\n"):
        sys.stdout.write("\n")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="backup-tfstate")
    p.add_argument(
        "--state-path",
        default=str(Path("terraform") / "terraform.tfstate"),
        help="Path to terraform.tfstate (default: terraform/terraform.tfstate)",
    )
    p.add_argument(
        "--backup-dir",
        default="/mnt/synology/terraform-backups",
        help="Backup directory (default: /mnt/synology/terraform-backups)",
    )
    p.add_argument("--prefix", default="terraform", help="Backup filename prefix (default: terraform)")
    return p


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def backup_tfstate(*, repo_root: Path, state_path: Path, backup_dir: Path, prefix: str) -> tuple[Path, str]:
    if not state_path.is_absolute():
        state_path = repo_root / state_path

    if not state_path.exists():
        raise FileNotFoundError(f"State file does not exist: {state_path}")

    backup_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    dest = backup_dir / f"{prefix}.terraform.tfstate.{ts}"

    shutil.copyfile(state_path, dest)
    sha = _sha256_file(dest)
    return dest, sha


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    repo_root = Path.cwd()
    try:
        dest, sha = backup_tfstate(
            repo_root=repo_root,
            state_path=Path(args.state_path),
            backup_dir=Path(args.backup_dir),
            prefix=str(args.prefix),
        )
    except Exception as exc:  # noqa: BLE001
        _print(f"ERROR: {exc}")
        return 1

    _print(f"backup_file={dest}")
    _print(f"backup_sha256={sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
