"""Forwarded arguments that begin with a dash must not be rejected.

Regression test for the failure that made every PROD lifecycle run report failure after a
successful apply:

    $ ops_cli healthcheck run --json --no-notify
    homelab-proxmox-ops: error: unrecognized arguments: --json --no-notify

`nargs=argparse.REMAINDER` only collects trailing arguments when the first one is a
positional. `lxc-lifecycle.yml` passed options first, and so does the Taskfile's own
documented example (`task healthcheck:run -- --check-drift`), so the separator-less form is
the one people actually write and it has to work.
"""

from __future__ import annotations

import argparse

import pytest

from homelab_proxmox_orchestrator.ops_cli import _parse_with_forwarded


@pytest.mark.parametrize(
    "argv",
    [
        ["healthcheck", "run", "--json", "--no-notify"],   # the form that failed in CI
        ["healthcheck", "run", "--", "--json", "--no-notify"],  # the form the handlers expect
    ],
)
def test_leading_dash_args_are_forwarded_not_rejected(argv: list[str]) -> None:
    args = _parse_with_forwarded(argv)
    assert args.command == "healthcheck"
    assert args.healthcheck_cmd == "run"
    # The handler strips a leading "--"; both forms must carry the flags through to it.
    forwarded = [a for a in args.args if a != "--"]
    assert forwarded == ["--json", "--no-notify"]


def test_documented_taskfile_example_parses() -> None:
    """`task healthcheck:run -- --check-drift`, straight from Taskfile.yml's summary."""
    args = _parse_with_forwarded(["healthcheck", "run", "--check-drift"])
    assert args.args == ["--check-drift"]


def test_order_is_preserved_for_flag_value_pairs() -> None:
    """Sliced from the original argv, not concatenated.

    Merging `unknown` onto `args.args` would reorder `--flag value` into `value --flag`,
    which silently changes the meaning of the forwarded command.
    """
    args = _parse_with_forwarded(["healthcheck", "run", "--profile", "lan", "--json"])
    assert args.args == ["--profile", "lan", "--json"]


def test_unknown_args_to_a_non_forwarding_subcommand_still_error() -> None:
    """Tolerating forwarded options must not turn every typo into a silent pass."""
    with pytest.raises(SystemExit) as exc:
        _parse_with_forwarded(["summary", "render", "--bogus-flag"])
    assert exc.value.code == 2


def test_known_options_are_still_parsed_not_forwarded() -> None:
    args = _parse_with_forwarded(["terraform", "apply", "--confirm"])
    assert args.confirm is True
    assert [a for a in args.args if a != "--"] == []
