"""One-off state migration (067, R-012): copy first, plan each service, stop on the first non-clean plan."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts/lab/migrate-state-067"
ORDER = [
    "ntfy", "market-model", "financial-scenario", "eurooffice", "llm-router", "jellyfin",
    "homeassistant", "nextcloud", "immich", "hermes", "monitoring", "reverse_proxy",
]
SYMLINKED = {"homeassistant", "immich", "jellyfin", "monitoring", "reverse_proxy"}


def _tree(tmp_path: Path) -> dict[str, Path]:
    state = tmp_path / "state"
    old = state / "services"
    nas = tmp_path / "nas/infra_state"
    (nas / "lab").mkdir(parents=True)
    (nas / "prod").mkdir()
    old.mkdir(parents=True)
    for svc in ORDER:
        target = (nas / "lab" / svc) if svc in SYMLINKED else (old / svc)
        target.mkdir(parents=True)
        (target / "terraform.tfstate").write_text(f'{{"service": "{svc}"}}\n')
        (target / "terraform.tfstate.backup").write_text("{}\n")
        if svc in SYMLINKED:
            (old / svc).symlink_to(target)
    runs = tmp_path / "runs"
    runs.mkdir()
    rc_dir = tmp_path / "rc"
    rc_dir.mkdir()
    fake = tmp_path / "pve-service-deploy"
    fake.write_text(
        "#!/bin/bash\n"
        'svc=""; while [ $# -gt 0 ]; do [ "$1" = "--service" ] && svc="$2"; shift; done\n'
        f'echo "$svc" >> "{tmp_path}/planned.txt"\n'
        f'd="{runs}/prod-$svc-abc-$(date +%s%N)/reports/plan"\n'
        'mkdir -p "$d"\n'
        f'cat "{rc_dir}/$svc" 2>/dev/null > "$d/exitcode.txt" || echo 0 > "$d/exitcode.txt"\n'
        "exit 0\n"
    )
    fake.chmod(0o755)
    return {"state": state, "old": old, "nas": nas, "runs": runs, "rc": rc_dir, "fake": fake, "backup": tmp_path / "backup"}


def _run(tmp_path: Path, t: dict[str, Path], *args: str) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "STATE_ROOT": str(t["state"]),
        "NAS_OLD_ROOT": str(t["nas"]),
        "BACKUP_ROOT": str(t["backup"]),
        "DEPLOY_BIN": str(t["fake"]),
        "RUNS_DIR": str(t["runs"]),
    }
    return subprocess.run([str(SCRIPT), *args], env=env, capture_output=True, text=True, check=False)


def test_migrates_all_twelve_resolving_symlinks_and_keeps_old_layout(tmp_path):
    t = _tree(tmp_path)
    proc = _run(tmp_path, t)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "12/12 No changes" in proc.stdout
    for svc in ORDER:
        dest = t["state"] / "prod" / svc / "terraform.tfstate"
        assert dest.read_text() == f'{{"service": "{svc}"}}\n'
        assert oct(dest.stat().st_mode & 0o777) == "0o600"
        assert not (t["backup"] / svc).is_symlink()
        assert (t["backup"] / svc / "terraform.tfstate").is_file()
    assert (tmp_path / "planned.txt").read_text().split() == ORDER
    assert t["old"].exists() and (t["nas"] / "lab").exists(), "old layout stays without the flag"


def test_stops_at_first_service_that_does_not_plan_clean(tmp_path):
    t = _tree(tmp_path)
    (t["rc"] / "llm-router").write_text("2\n")
    proc = _run(tmp_path, t)
    assert proc.returncode != 0
    assert "llm-router" in proc.stdout
    assert (tmp_path / "planned.txt").read_text().split() == ORDER[: ORDER.index("llm-router") + 1]
    assert (t["state"] / "prod/eurooffice/terraform.tfstate").is_file(), "services already done stay done"
    assert not (t["state"] / "prod/jellyfin").exists()
    assert t["old"].exists()


def test_remove_old_layout_only_after_twelve_of_twelve(tmp_path):
    t = _tree(tmp_path)
    (t["rc"] / "hermes").write_text("2\n")
    assert _run(tmp_path, t, "--remove-old-layout").returncode != 0
    assert t["old"].exists() and (t["nas"] / "lab").exists()

    (t["rc"] / "hermes").unlink()
    proc = _run(tmp_path, t, "--remove-old-layout")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert not t["old"].exists()
    assert not (t["nas"] / "lab").exists() and not (t["nas"] / "prod").exists()
    for svc in ORDER:
        assert (t["state"] / "prod" / svc / "terraform.tfstate").is_file()


def test_refuses_to_overwrite_a_different_prod_state(tmp_path):
    t = _tree(tmp_path)
    (t["state"] / "prod/ntfy").mkdir(parents=True)
    (t["state"] / "prod/ntfy/terraform.tfstate").write_text('{"newer": true}\n')
    proc = _run(tmp_path, t)
    assert proc.returncode != 0
    assert "not overwriting" in proc.stdout
    assert (t["state"] / "prod/ntfy/terraform.tfstate").read_text() == '{"newer": true}\n'


def test_dry_run_changes_nothing(tmp_path):
    t = _tree(tmp_path)
    proc = _run(tmp_path, t, "--dry-run", "--remove-old-layout")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert not (t["state"] / "prod").exists()
    assert not t["backup"].exists()
    assert not (tmp_path / "planned.txt").exists()
    assert t["old"].exists() and (t["nas"] / "lab").exists()
