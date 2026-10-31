"""Tests for scripts/memory/generate-vault-entries.py (spec 097, task T002).

The pure functions run everywhere. The end-to-end test uses a real ansible-vault on a throwaway
vault with its own password file, and is skipped where ansible-vault is not installed (CI).
"""

from __future__ import annotations

import importlib.util
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "memory" / "generate-vault-entries.py"
_spec = importlib.util.spec_from_file_location("generate_vault_entries", SCRIPT)
gve = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gve)

PREFLIGHT_KEY = re.compile(r"^hmem_[A-Za-z0-9_-]{43,}$")  # roles/memory/tasks/preflight.yml
PREFLIGHT_DB = re.compile(r"^[A-Za-z0-9_-]{24,}$")


def test_every_entry_the_deploy_needs_is_covered():
    defaults = (ROOT / "ansible/roles/memory/defaults/main.yml").read_text()
    vault_vars = set(re.findall(r"vault_var: (\w+)", defaults))
    assert vault_vars | {"memory_ui_access_key", "memory_db_password", "llm_router_client_memory_key"} == set(gve.ENTRIES)


@pytest.mark.parametrize("name", gve.MEMORY_KEYS)
def test_memory_keys_meet_the_preflight_format(name):
    value = gve.generate(name)
    assert PREFLIGHT_KEY.match(value) and gve.valid(name, value)


def test_db_password_meets_the_preflight_format():
    value = gve.generate("memory_db_password")
    assert PREFLIGHT_DB.match(value) and gve.valid("memory_db_password", value)


def test_gateway_key_uses_the_sk_convention():
    value = gve.generate("llm_router_client_memory_key")
    assert value.startswith("sk-") and len(value) == 51 and gve.valid("llm_router_client_memory_key", value)


def test_values_are_fresh_each_time():
    assert len({gve.generate("memory_admin_key") for _ in range(20)}) == 20


def test_missing_reads_top_level_keys_only():
    text = 'other_key: "x"\nmemory_admin_key: "hmem_x"\nnested:\n  memory_db_password: "y"\n'
    todo = gve.missing(text)
    assert "memory_admin_key" not in todo
    assert "memory_db_password" in todo  # nested, so not a top-level vault entry


def test_merge_appends_and_keeps_existing_content_byte_for_byte():
    old = 'litellm_master_key: "sk-old"\n# a comment\n'
    values = {"memory_admin_key": "hmem_" + "a" * 43, "memory_db_password": "b" * 32}
    new = gve.merged(old, values, "2026-10-31")
    assert new.startswith(old)
    assert 'memory_admin_key: "hmem_' in new and 'memory_db_password: "' in new
    assert gve.missing(new) == [n for n in gve.ENTRIES if n not in values]


def test_merge_without_trailing_newline_keeps_the_last_line():
    new = gve.merged('a: "1"', {"memory_admin_key": "hmem_" + "a" * 43}, "2026-10-31")
    assert new.startswith('a: "1"\n')


def test_merge_with_nothing_missing_is_a_no_op():
    assert gve.merged('a: "1"\n', {}, "2026-10-31") == 'a: "1"\n'


@pytest.mark.skipif(shutil.which("ansible-vault") is None, reason="ansible-vault not installed")
def test_end_to_end_adds_only_missing_entries_and_prints_no_value(tmp_path, monkeypatch, capsys):
    password = tmp_path / "pw"
    password.write_text("test-only-password")
    monkeypatch.setenv("ANSIBLE_VAULT_PASSWORD_FILE", str(password))
    plain = tmp_path / "plain.yml"
    plain.write_text('existing_secret: "keep-me"\nmemory_admin_key: "hmem_' + "k" * 43 + '"\n')
    vault = tmp_path / "vault.yml"
    subprocess.run(["ansible-vault", "encrypt", "--output", str(vault), str(plain)], check=True, capture_output=True)

    assert gve.main(["--vault", str(vault), "--check"]) == 1
    assert gve.main(["--vault", str(vault)]) == 0
    out = capsys.readouterr().out
    after = subprocess.run(["ansible-vault", "view", str(vault)], check=True, capture_output=True, text=True).stdout

    assert after.startswith(plain.read_text())  # earlier content unchanged
    assert gve.missing(after) == []
    assert after.count("memory_admin_key:") == 1  # an existing entry is not regenerated
    for name in gve.ENTRIES:
        value = re.search(rf'^{name}: "([^"]+)"', after, re.M).group(1)
        assert value not in out, f"{name}'s value was printed"
    assert gve.main(["--vault", str(vault), "--check"]) == 0
    assert gve.main(["--vault", str(vault)]) == 0
    assert subprocess.run(["ansible-vault", "view", str(vault)], check=True, capture_output=True,
                          text=True).stdout == after  # a second run changes nothing
    assert os.stat(vault).st_size > 0
