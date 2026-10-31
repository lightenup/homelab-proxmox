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


def _tasks() -> list[dict]:
    return yaml.safe_load((ROOT / "ansible/roles/hermes/tasks/memory_plugin.yml").read_text())


def _task(name: str) -> dict:
    return next(t for t in _tasks() if t.get("name") == name)


def test_plugin_is_reextracted_when_the_installed_version_differs():
    """A rollback finds the older tarball cached and plugin.yaml present; only comparing the
    installed manifest with the pin re-extracts it (PR #318 review)."""
    when = _task("Unpack the plugin into a clean directory")["when"]
    assert "hermes_memory_plugin_installed" in when and "hermes_hindsight_plugin_version" in when


def test_packages_are_rebuilt_when_the_marker_differs_from_the_pins():
    """The marker records name, version and sha256 per wheel and is compared, not just stat'ed."""
    pins = _task("Define the expected package marker")["ansible.builtin.set_fact"]["hermes_memory_deps_pins"]
    assert "w.name" in pins and "w.version" in pins and "w.sha256" in pins
    when = _task("Unpack the packages into a clean directory")["when"]
    assert "hermes_memory_deps_installed.content" in when and "!= hermes_memory_deps_pins" in when
