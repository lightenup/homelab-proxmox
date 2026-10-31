#!/usr/bin/env python3
"""Generate the memory service's vault entries (spec 097, task T002).

Usage, from anywhere in the repo:

    scripts/memory/generate-vault-entries.py --check        # names present/missing, changes nothing
    scripts/memory/generate-vault-entries.py                # add the missing entries to the vault
    scripts/memory/generate-vault-entries.py --keychain     # ... and store the Claude Code key in
                                                            #     the macOS keychain (homelab-memory)
    scripts/memory/generate-vault-entries.py --copy-ui-key  # ... and put the web UI login key on
                                                            #     the clipboard for the password manager

What it does:

- Decrypts ansible/group_vars/services/vault.yml with `ansible-vault view`, run from ansible/ so
  ansible.cfg's vault_password_file applies. The plaintext stays in memory and in a 0700 temp
  directory that is removed on exit.
- Adds only the entries that are missing. An existing entry is never changed: rotating a key is
  a deliberate act (data-model.md § Client), not a side effect of re-running this.
- Generates each value in the format the deploy's preflight checks (roles/memory/tasks/
  preflight.yml, roles/llm_router conventions): `hmem_` plus 32 random bytes as URL-safe base64
  for the six memory keys, 24 random bytes URL-safe for the database password, and
  `sk-` plus 24 random bytes as hex for the gateway key.
- Re-encrypts with `ansible-vault encrypt`, then decrypts the result to verify that every
  earlier line is unchanged and every entry is present, before replacing the vault file.
- Never prints a value. Output names entries only.

The vault file is tracked in git: commit it through a PR, as every vault change.

--keychain passes the key to `security add-generic-password` as an argument, so it is visible in
the process list for the moment that command runs; the alternative is the manual step in T002.
"""

from __future__ import annotations

import argparse
import datetime
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VAULT = ROOT / "ansible" / "group_vars" / "services" / "vault.yml"
KEYCHAIN_SERVICE = "homelab-memory"
KEYCHAIN_ACCOUNT = "claude-code"

MEMORY_KEYS = (
    "memory_client_hermes_key",
    "memory_client_open_webui_key",
    "memory_client_claude_code_key",
    "memory_client_control_plane_key",
    "memory_ui_access_key",
    "memory_admin_key",
)
ENTRIES = (*MEMORY_KEYS, "memory_db_password", "llm_router_client_memory_key")

# The formats the deploy refuses to go without (preflight.yml in the memory and hermes roles).
FORMATS = {
    **{name: re.compile(r"^hmem_[A-Za-z0-9_-]{43,}$") for name in MEMORY_KEYS},
    "memory_db_password": re.compile(r"^[A-Za-z0-9_-]{24,}$"),
    "llm_router_client_memory_key": re.compile(r"^sk-[0-9a-f]{48}$"),
}
TOP_LEVEL_KEY = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:", re.M)


def present(plaintext: str) -> set[str]:
    """Top-level keys of the decrypted vault YAML."""
    return set(TOP_LEVEL_KEY.findall(plaintext))


def missing(plaintext: str) -> list[str]:
    have = present(plaintext)
    return [name for name in ENTRIES if name not in have]


def generate(name: str) -> str:
    if name in MEMORY_KEYS:
        return "hmem_" + secrets.token_urlsafe(32)
    if name == "memory_db_password":
        return secrets.token_urlsafe(24)
    if name == "llm_router_client_memory_key":
        return "sk-" + secrets.token_hex(24)
    raise KeyError(name)


def valid(name: str, value: str) -> bool:
    return bool(FORMATS[name].match(value))


def merged(plaintext: str, values: dict[str, str], today: str) -> str:
    """The vault plaintext with the new entries appended; earlier content is untouched."""
    if not values:
        return plaintext
    block = [f"# Spec 097 shared memory, generated {today} by scripts/memory/generate-vault-entries.py"]
    block += [f'{name}: "{values[name]}"' for name in ENTRIES if name in values]
    base = plaintext if plaintext.endswith("\n") or not plaintext else plaintext + "\n"
    return base + "\n" + "\n".join(block) + "\n"


def _vault(*args: str, stdin: str | None = None) -> str:
    """Run ansible-vault from ansible/, so ansible.cfg's password file applies."""
    proc = subprocess.run(
        ["ansible-vault", *args], cwd=ROOT / "ansible", input=stdin, capture_output=True, text=True
    )
    if proc.returncode != 0:
        # stderr from ansible-vault names files and errors, never vault content.
        sys.exit(f"ansible-vault {args[0]} failed: {proc.stderr.strip()}")
    return proc.stdout


def _value_of(plaintext: str, name: str) -> str:
    match = re.search(rf'^{name}\s*:\s*"?([^"\n]+)"?\s*$', plaintext, re.M)
    if not match:
        sys.exit(f"{name} not found in the vault")
    return match.group(1).strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", action="store_true", help="report present/missing names only")
    parser.add_argument("--keychain", action="store_true", help="store the Claude Code key in the macOS keychain")
    parser.add_argument("--copy-ui-key", action="store_true", help="copy the web UI login key to the clipboard")
    parser.add_argument("--vault", type=Path, default=VAULT, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    vault = args.vault.resolve()
    if shutil.which("ansible-vault") is None:
        sys.exit("ansible-vault not found on PATH")

    plaintext = _vault("view", str(vault))
    todo = missing(plaintext)
    for name in ENTRIES:
        print(f"{'missing' if name in todo else 'present'}  {name}")
    if args.check:
        return 1 if todo else 0

    if todo:
        values = {name: generate(name) for name in todo}
        assert all(valid(n, v) for n, v in values.items())
        new_plaintext = merged(plaintext, values, datetime.date.today().isoformat())
        workdir = Path(tempfile.mkdtemp(prefix="vault-entries-"))
        os.chmod(workdir, 0o700)
        try:
            plain = workdir / "vault.yml"
            plain.write_text(new_plaintext)
            os.chmod(plain, 0o600)
            encrypted = workdir / "vault.yml.enc"
            _vault("encrypt", "--output", str(encrypted), str(plain))
            check = _vault("view", str(encrypted))
            if not check.startswith(plaintext) or missing(check):
                sys.exit("verification failed: the re-encrypted vault does not hold the old content plus every entry")
            for name in ENTRIES:
                if not valid(name, _value_of(check, name)):
                    print(f"warning: existing {name} does not match the format the deploy expects", file=sys.stderr)
            shutil.copyfile(encrypted, vault)
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
        plaintext = new_plaintext
        shown = vault.relative_to(ROOT) if vault.is_relative_to(ROOT) else vault
        print(f"added {len(todo)} entries to {shown}; commit it through a PR")
    else:
        print("nothing to add")

    if args.keychain:
        subprocess.run(
            ["security", "add-generic-password", "-U", "-s", KEYCHAIN_SERVICE, "-a", KEYCHAIN_ACCOUNT,
             "-w", _value_of(plaintext, "memory_client_claude_code_key")],
            check=True, capture_output=True,
        )
        print(f"stored memory_client_claude_code_key in the keychain ({KEYCHAIN_SERVICE}/{KEYCHAIN_ACCOUNT})")
    if args.copy_ui_key:
        subprocess.run(["pbcopy"], input=_value_of(plaintext, "memory_ui_access_key"), text=True, check=True)
        print("copied memory_ui_access_key to the clipboard: paste it into the password manager, then clear the clipboard")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
