from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import subprocess
import sys
from typing import Mapping

import homelab_proxmox_orchestrator

_PKG_ROOT = str(Path(homelab_proxmox_orchestrator.__file__).resolve().parents[1])


@dataclass(frozen=True)
class RunResult:
    returncode: int
    stdout: str
    stderr: str


def _find_repo_root(start: Path) -> Path:
    current = start
    for _ in range(20):
        if (current / "Taskfile.yml").exists() and (current / "python").exists():
            return current
        current = current.parent
    raise RuntimeError("Unable to locate repository root")


def run_ops_cli(
    args: list[str],
    *,
    env: Mapping[str, str] | None = None,
    cwd: Path | None = None,
) -> RunResult:
    repo_root = cwd or _find_repo_root(Path(__file__).resolve())

    merged_env = dict(os.environ)
    merged_env["PYTHONPATH"] = os.pathsep.join(
        [
            _PKG_ROOT,
            merged_env.get("PYTHONPATH", ""),
        ]
    ).strip(os.pathsep)
    if env:
        merged_env.update(env)

    cp = subprocess.run(
        [sys.executable, "-m", "homelab_proxmox_orchestrator.ops_cli", *args],
        cwd=str(repo_root),
        env=merged_env,
        text=True,
        capture_output=True,
        check=False,
    )

    return RunResult(returncode=int(cp.returncode), stdout=cp.stdout or "", stderr=cp.stderr or "")
