from __future__ import annotations

from pathlib import Path

from homelab_proxmox_orchestrator.terraform_backup import backup_tfstate


def test_backup_tfstate_copies_file_and_hashes(tmp_path: Path) -> None:
    repo_root = tmp_path
    tf_dir = repo_root / "terraform"
    tf_dir.mkdir(parents=True, exist_ok=True)

    state_path = tf_dir / "terraform.tfstate"
    state_path.write_text('{"hello":"world"}\n', encoding="utf-8")

    backup_dir = repo_root / "backups"
    dest, sha = backup_tfstate(
        repo_root=repo_root,
        state_path=Path("terraform/terraform.tfstate"),
        backup_dir=backup_dir,
        prefix="terraform",
    )

    assert dest.exists()
    assert dest.read_text(encoding="utf-8") == state_path.read_text(encoding="utf-8")
    assert len(sha) == 64
