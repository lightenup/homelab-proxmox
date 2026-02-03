from __future__ import annotations

import os
from pathlib import Path
import stat

from homelab_proxmox_orchestrator.healthcheck_runner import run_healthcheck


def _make_executable(path: Path) -> None:
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def test_healthcheck_run_writes_output_and_latest_symlink(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path

    # Minimal repo markers for repo_root detection in callers.
    (repo_root / "Taskfile.yml").write_text("version: '3'\n", encoding="utf-8")
    (repo_root / "python").mkdir()

    scripts_dir = repo_root / "scripts" / "healthcheck"
    scripts_dir.mkdir(parents=True)

    hc = scripts_dir / "healthcheck.py"
    hc.write_text(
        """#!/usr/bin/env python3
import argparse
import json

p = argparse.ArgumentParser()
p.add_argument('--output-json', required=True)
p.add_argument('--profile')
p.add_argument('--inventory')
p.add_argument('--json', action='store_true')
args, rest = p.parse_known_args()

with open(args.output_json, 'w') as f:
    json.dump([{'ok': True, 'profile': args.profile}], f)

if args.json:
    print('[{"ok": true}]')
""",
        encoding="utf-8",
    )
    _make_executable(hc)

    monkeypatch.chdir(repo_root)

    r = run_healthcheck(repo_root=repo_root, argv=["--profile", "lan", "--json"], timestamp="20260114-120000")
    assert r.exit_code == 0

    history_dir = repo_root / "artifacts" / "healthcheck" / "history"
    assert (history_dir / "20260114-120000.json").exists()

    latest = history_dir / "latest.json"
    assert latest.is_symlink()
    assert os.readlink(latest) == "20260114-120000.json"


def test_healthcheck_rotation_keeps_last_50(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path
    (repo_root / "Taskfile.yml").write_text("version: '3'\n", encoding="utf-8")
    (repo_root / "python").mkdir()

    scripts_dir = repo_root / "scripts" / "healthcheck"
    scripts_dir.mkdir(parents=True)

    hc = scripts_dir / "healthcheck.py"
    hc.write_text(
        """#!/usr/bin/env python3
import argparse
p = argparse.ArgumentParser()
p.add_argument('--output-json', required=True)
args, rest = p.parse_known_args()
open(args.output_json, 'w').write('[]')
""",
        encoding="utf-8",
    )
    _make_executable(hc)

    history_dir = repo_root / "artifacts" / "healthcheck" / "history"
    history_dir.mkdir(parents=True)

    # Create 52 old entries.
    for i in range(52):
        p = history_dir / f"old-{i:03d}.json"
        p.write_text("[]", encoding="utf-8")
        os.utime(p, (10_000 + i, 10_000 + i))

    monkeypatch.chdir(repo_root)
    run_healthcheck(repo_root=repo_root, argv=[], timestamp="20260114-120001")

    remaining = [p for p in history_dir.glob("*.json") if p.name != "latest.json"]
    assert len(remaining) == 50
