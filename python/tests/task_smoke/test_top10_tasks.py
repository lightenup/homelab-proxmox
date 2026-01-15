from __future__ import annotations

from task_smoke.helpers import run_ops_cli


_FAKE_ENV = {"HOMELAB_PROXMOX_OPS_FAKE": "1"}


def test_service_add_smoke_success() -> None:
    r = run_ops_cli(["service", "add"], env=_FAKE_ENV)
    assert r.returncode == 0
    assert "FAKE" in (r.stdout + r.stderr)


def test_inventory_update_smoke_success() -> None:
    r = run_ops_cli(["inventory", "update"], env=_FAKE_ENV)
    assert r.returncode == 0
    assert "inventory:update" in (r.stdout + r.stderr)


def test_terraform_apply_requires_confirmation_failure() -> None:
    r = run_ops_cli(["terraform", "apply"], env=_FAKE_ENV)
    assert r.returncode != 0
    assert "confirm" in (r.stdout + r.stderr).lower()


def test_terraform_apply_with_confirmation_success() -> None:
    r = run_ops_cli(["terraform", "apply", "--confirm"], env=_FAKE_ENV)
    assert r.returncode == 0
    assert "terraform:apply" in (r.stdout + r.stderr)


def test_summary_render_real_success() -> None:
    r = run_ops_cli([
        "summary",
        "render",
        "--evidence-pack",
        "scripts/lab/fixtures/evidence-packs/valid",
    ])
    assert r.returncode == 0
    assert "## Evidence Summary" in r.stdout
