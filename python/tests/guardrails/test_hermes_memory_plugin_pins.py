"""Guard test: the Hindsight plugin and its packages are pinned and hashed (spec 097 T029).

FR-002: no runtime install. The deploy fetches exactly these artefacts and checks each one's
sha256 before unpacking it (roles/hermes/tasks/memory_plugin.yml, research R-003).
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
DEFAULTS = yaml.safe_load((ROOT / "ansible/roles/hermes/defaults/main.yml").read_text())
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def test_plugin_tarball_is_the_pinned_tag():
    url = DEFAULTS["hermes_hindsight_plugin_url"]
    assert url.startswith("https://github.com/vectorize-io/hindsight/archive/refs/tags/")
    assert url.endswith("/integrations/hermes/v{{ hermes_hindsight_plugin_version }}.tar.gz")
    assert SHA256.match(DEFAULTS["hermes_hindsight_plugin_sha256"])


def test_plugin_version_is_pinned_in_the_versions_block():
    services = yaml.safe_load((ROOT / "ansible/group_vars/services/vars.yml").read_text())
    assert re.fullmatch(r"\d+\.\d+\.\d+", services["hermes_hindsight_plugin_version"])


def test_every_wheel_is_exact_hashed_and_from_pypi():
    wheels = DEFAULTS["hermes_hindsight_plugin_wheels"]
    assert [w["name"] for w in wheels] == ["hindsight-client", "hindsight-embed", "aiohttp-retry"]
    for wheel in wheels:
        assert re.fullmatch(r"==\d+\.\d+\.\d+", wheel["version"]), wheel
        assert wheel["url"].startswith("https://files.pythonhosted.org/packages/"), wheel
        assert wheel["url"].endswith("-py3-none-any.whl"), "pure-Python wheels only"
        assert wheel["version"][2:] in wheel["url"], wheel
        assert SHA256.match(wheel["sha256"]), wheel


def test_deploy_task_checks_every_hash():
    tasks = (ROOT / "ansible/roles/hermes/tasks/memory_plugin.yml").read_text()
    assert tasks.count('checksum: "sha256:') == 2
