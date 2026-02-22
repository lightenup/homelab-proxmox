from __future__ import annotations

from pathlib import Path

import pytest

from homelab_proxmox_orchestrator.tfvars_mountpoints import (
    format_pct_set_arg,
    format_step_summary,
    parse_service_host_path_mounts,
    validate_bind_mount_allowlist,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[3]
PROD_TFVARS_EXAMPLE = REPO_ROOT / "terraform" / "environments" / "prod.tfvars.example"


# ---------------------------------------------------------------------------
# T007: Basic parser tests
# ---------------------------------------------------------------------------

_SIMPLE_TFVARS = """\
service_mountpoints = {
  myservice = {
    data = {
      mp     = "/mnt/data"
      volume = "/mnt/nas/mydata"
    }
  }
}
"""

_STORAGE_BACKED_TFVARS = """\
service_mountpoints = {
  myservice = {
    disk = {
      mp      = "/mnt/disk"
      volume  = "local-lvm:vm-100-disk-0"
      storage = "local-lvm"
    }
  }
}
"""

_READONLY_TFVARS = """\
service_mountpoints = {
  myservice = {
    media = {
      mp       = "/media/video"
      volume   = "/mnt/nas/video"
      readonly = true
    }
  }
}
"""

_READONLY_FALSE_TFVARS = """\
service_mountpoints = {
  myservice = {
    data = {
      mp       = "/mnt/data"
      volume   = "/mnt/nas/mydata"
      readonly = false
    }
  }
}
"""

_MULTI_MOUNT_TFVARS = """\
service_mountpoints = {
  myservice = {
    library = {
      mp     = "/mnt/immich"
      volume = "/mnt/nas/homelab_immich"
    }
    photos = {
      mp       = "/mnt/photos"
      volume   = "/mnt/nas/photo"
      readonly = true
    }
  }
}
"""


def test_parse_service_with_host_path_mounts():
    result = parse_service_host_path_mounts(_SIMPLE_TFVARS, "myservice")
    assert result == [{"mp": "/mnt/data", "volume": "/mnt/nas/mydata", "readonly": False}]


def test_parse_service_no_mounts():
    result = parse_service_host_path_mounts(_SIMPLE_TFVARS, "nonexistent")
    assert result == []


def test_parse_service_storage_backed_only():
    result = parse_service_host_path_mounts(_STORAGE_BACKED_TFVARS, "myservice")
    assert result == []


def test_parse_readonly_true():
    result = parse_service_host_path_mounts(_READONLY_TFVARS, "myservice")
    assert len(result) == 1
    assert result[0]["readonly"] is True


def test_parse_readonly_absent_defaults_false():
    result = parse_service_host_path_mounts(_SIMPLE_TFVARS, "myservice")
    assert len(result) == 1
    assert result[0]["readonly"] is False


def test_parse_multiple_mounts():
    result = parse_service_host_path_mounts(_MULTI_MOUNT_TFVARS, "myservice")
    assert len(result) == 2
    volumes = [m["volume"] for m in result]
    assert "/mnt/nas/homelab_immich" in volumes
    assert "/mnt/nas/photo" in volumes


# ---------------------------------------------------------------------------
# T008: Behavioral equivalence tests (parse prod.tfvars.example)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    not PROD_TFVARS_EXAMPLE.exists(),
    reason="prod.tfvars.example not found",
)
def test_behavioral_equivalence_jellyfin():
    text = PROD_TFVARS_EXAMPLE.read_text(encoding="utf-8")
    result = parse_service_host_path_mounts(text, "jellyfin")

    assert result == [{"mp": "/media/video", "volume": "/mnt/nas/video", "readonly": True}]

    pct_arg = format_pct_set_arg(result[0])
    assert pct_arg == "/mnt/nas/video,mp=/media/video,ro=1"


@pytest.mark.skipif(
    not PROD_TFVARS_EXAMPLE.exists(),
    reason="prod.tfvars.example not found",
)
def test_behavioral_equivalence_immich():
    text = PROD_TFVARS_EXAMPLE.read_text(encoding="utf-8")
    result = parse_service_host_path_mounts(text, "immich")

    assert len(result) == 2

    library = next(m for m in result if m["volume"] == "/mnt/nas/homelab_immich")
    assert library == {"mp": "/mnt/immich", "volume": "/mnt/nas/homelab_immich", "readonly": False}

    photo = next(m for m in result if m["volume"] == "/mnt/nas/photo")
    assert photo == {
        "mp": "/mnt/immich-external/photo",
        "volume": "/mnt/nas/photo",
        "readonly": True,
    }

    library_arg = format_pct_set_arg(library)
    assert library_arg == "/mnt/nas/homelab_immich,mp=/mnt/immich"

    photo_arg = format_pct_set_arg(photo)
    assert photo_arg == "/mnt/nas/photo,mp=/mnt/immich-external/photo,ro=1"


# ---------------------------------------------------------------------------
# T009: Step summary format test
# ---------------------------------------------------------------------------

def test_step_summary_format():
    results = [
        {"volume": "/mnt/nas/video", "mp": "/media/video", "readonly": True, "result": "applied"},
        {
            "volume": "/mnt/nas/homelab_nextcloud",
            "mp": "/mnt/nextcloud",
            "readonly": False,
            "result": "skipped",
        },
        {"volume": "/mnt/nas/bad", "mp": "/mnt/bad", "readonly": False, "result": "failed"},
    ]
    output = format_step_summary(results)
    expected = (
        "| Host Path | Container Path | Permission | Result |\n"
        "|-----------|----------------|------------|--------|\n"
        "| /mnt/nas/video | /media/video | ro | applied |\n"
        "| /mnt/nas/homelab_nextcloud | /mnt/nextcloud | rw | skipped |\n"
        "| /mnt/nas/bad | /mnt/bad | rw | failed |\n"
        "\n"
        "**Container reboot**: stopped → mounts applied → started\n"
        "**Overall**: failure (1 applied, 1 skipped, 1 failed)\n"
    )
    assert output == expected


def test_step_summary_all_applied():
    results = [
        {"volume": "/mnt/nas/data", "mp": "/mnt/data", "readonly": False, "result": "applied"},
    ]
    output = format_step_summary(results)
    assert "**Container reboot**: stopped → mounts applied → started" in output
    assert "**Overall**: success (1 applied, 0 skipped, 0 failed)" in output


def test_step_summary_all_skipped():
    results = [
        {"volume": "/mnt/nas/data", "mp": "/mnt/data", "readonly": False, "result": "skipped"},
    ]
    output = format_step_summary(results)
    assert "**Container reboot**" not in output
    assert "**Overall**: success (0 applied, 1 skipped, 0 failed)" in output


# ---------------------------------------------------------------------------
# T022: Allowlist unit tests
# ---------------------------------------------------------------------------

def test_allowlist_valid_path():
    mounts = [{"volume": "/mnt/nas/nextcloud", "mp": "/mnt/nextcloud", "readonly": False}]
    allowed, rejected = validate_bind_mount_allowlist(mounts)
    assert len(allowed) == 1
    assert len(rejected) == 0


def test_allowlist_reject_outside():
    mounts = [{"volume": "/etc/shadow", "mp": "/mnt/shadow", "readonly": True}]
    allowed, rejected = validate_bind_mount_allowlist(mounts)
    assert len(allowed) == 0
    assert len(rejected) == 1
    assert rejected[0]["volume"] == "/etc/shadow"


def test_allowlist_directory_boundary():
    # /mnt/nasty-trick must NOT be allowed — it does not start with /mnt/nas/
    mounts = [{"volume": "/mnt/nasty-trick", "mp": "/mnt/trick", "readonly": False}]
    allowed, rejected = validate_bind_mount_allowlist(mounts)
    assert len(allowed) == 0
    assert len(rejected) == 1
    assert rejected[0]["volume"] == "/mnt/nasty-trick"


def test_allowlist_multiple_mounts_mixed():
    mounts = [
        {"volume": "/mnt/nas/video", "mp": "/media/video", "readonly": True},
        {"volume": "/etc/passwd", "mp": "/mnt/passwd", "readonly": True},
    ]
    allowed, rejected = validate_bind_mount_allowlist(mounts)
    assert len(allowed) == 1
    assert allowed[0]["volume"] == "/mnt/nas/video"
    assert len(rejected) == 1
    assert rejected[0]["volume"] == "/etc/passwd"
