"""Guard test: the harness gate ran against today's memory configuration (spec 097 T037, FR-021).

FR-021: no PROD promotion that changes memory without the spike harness passing against the
production-rendered configuration (research R-017). This test computes a fingerprint over the
pins and files that decide memory behaviour and fails unless a committed
docs/backlog/097-spike/results/*-prod-render/ run passed with the same value.

docs/backlog/097-spike/render-prod.sh writes that file with compute_fingerprint() below, so the
test and the harness cannot disagree on what is hashed.

Fingerprinted: the Hindsight, Postgres, plugin and agent pins (the plugin's behaviour depends on
the agent, G2), the wheel pins and the plugin tarball hash, the templates (server env, client list,
plugin config), the variables they render from (the memory role's defaults: MCP tools, bank ids,
clients and scopes, images; the hermes role's memory settings), the policy module, the shim and
the Open WebUI filter (once it exists). Added after the PR #318 review: hashing a template alone
missed a change to the values it renders.

A matching fingerprint alone is not evidence: the run must also have passed. gate.py writes
gate.json with the SC-001 to SC-005 verdict and the fingerprint; only a passing gate.json counts.

Not fingerprinted: the Claude Code hook. It lives in dotfiles, and the harness replays its turn format without running
it, so hashing it would force re-runs that test nothing (I2). The turn-format contract and
quickstart § 6 cover it.

Deliberately stdlib + PyYAML only, so render-prod.sh can import it without pytest.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
RESULTS = ROOT / "docs" / "backlog" / "097-spike" / "results"

PINS = ("hindsight_version", "memory_postgres_version", "hermes_hindsight_plugin_version", "hermes_agent_version")
FILES = (
    "ansible/roles/memory/templates/server.env.j2",
    "ansible/roles/memory/templates/clients.json.j2",
    "ansible/roles/memory/defaults/main.yml",
    "ansible/roles/hermes/templates/hindsight-config.json.j2",
    "ansible/roles/hermes/templates/SOUL.md.j2",
    # The harness agent's config: memory switches, hook spill limit, tool-loop stop, memory MCP
    # server. Alignment tests in test_hermes_memory_config.py tie it to agent-config.yaml.j2, so a
    # change on either side invalidates the evidence (PR #340 review).
    "docs/backlog/097-spike/runs/prod-render/config.yaml",
    "python/src/homelab_proxmox_orchestrator/memory_access.py",
    "ansible/roles/memory/files/hindsight_ext/shim.py",
)
OPTIONAL_FILES = ("ansible/roles/hermes/files/open_webui/memory_filter.py",)
HERMES_MEMORY_PREFIXES = ("hermes_memory_", "hermes_hindsight_", "hermes_agent_site_packages")


def fingerprint_inputs(root: Path = ROOT) -> list[str]:
    """One line per input, in a fixed order: `pin <name>=<value>` or `file <path> <sha256>`."""
    services = yaml.safe_load((root / "ansible/group_vars/services/vars.yml").read_text())
    hermes = yaml.safe_load((root / "ansible/roles/hermes/defaults/main.yml").read_text())
    lines = [f"pin {name}={services[name]}" for name in PINS]
    lines.append(f"pin hermes_hindsight_plugin_sha256={hermes['hermes_hindsight_plugin_sha256']}")
    for wheel in hermes["hermes_hindsight_plugin_wheels"]:
        lines.append(f"pin wheel {wheel['name']}{wheel['version']} {wheel['sha256']}")
    # The hermes role's memory settings (the plugin config renders from them), not the whole
    # defaults file, which holds unrelated workspace settings.
    for name in sorted(hermes):
        if name.startswith(HERMES_MEMORY_PREFIXES) and name != "hermes_hindsight_plugin_wheels":
            lines.append(f"var {name}={json.dumps(hermes[name], sort_keys=True)}")
    for rel in FILES + tuple(f for f in OPTIONAL_FILES if (root / f).exists()):
        lines.append(f"file {rel} {hashlib.sha256((root / rel).read_bytes()).hexdigest()}")
    return lines


def compute_fingerprint(root: Path = ROOT) -> str:
    return hashlib.sha256("\n".join(fingerprint_inputs(root)).encode()).hexdigest()


def fingerprint_file(root: Path = ROOT) -> str:
    """The content render-prod.sh writes: the fingerprint, then the inputs for a reviewer."""
    return "\n".join([compute_fingerprint(root), *fingerprint_inputs(root)]) + "\n"


GATE_CRITERIA = ("images", "SC-001", "SC-002", "SC-003", "SC-004", "SC-005", "T071")


def _recorded() -> dict[str, str]:
    """Fingerprints of archived runs whose gate.json says every criterion passed."""
    passed = {}
    for path in sorted(RESULTS.glob("*-prod-render/gate.json")):
        gate = json.loads(path.read_text())
        listed = (path.parent / "fingerprint.txt").read_text().splitlines()[0].strip()
        if (gate.get("pass") is True and gate.get("fingerprint") == listed
                and all(gate.get(c, {}).get("pass") is True for c in GATE_CRITERIA)):
            passed[gate["fingerprint"]] = path.parent.name
    return passed


def test_inputs_cover_every_pin_and_file():
    lines = fingerprint_inputs()
    assert sum(line.startswith("pin wheel ") for line in lines) == 3
    for rel in FILES:
        assert any(line.startswith(f"file {rel} ") for line in lines), rel
    for name in ("hermes_memory_api_url", "hermes_memory_bank_id", "hermes_agent_site_packages"):
        assert any(line.startswith(f"var {name}=") for line in lines), name


def test_a_render_input_change_moves_the_fingerprint(tmp_path):
    """The review case: changing a rendered value (here the MCP tool list) without touching any
    template must change the fingerprint."""
    for rel in ("ansible/group_vars/services/vars.yml", "ansible/roles/hermes/defaults/main.yml", *FILES):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_bytes((ROOT / rel).read_bytes())
    before = compute_fingerprint(tmp_path)
    defaults = tmp_path / "ansible/roles/memory/defaults/main.yml"
    defaults.write_text(defaults.read_text().replace("  - list_tags\n", "  - list_tags\n  - delete_document\n"))
    assert compute_fingerprint(tmp_path) != before


def _archive(root: Path, name: str, gate: dict) -> None:
    run = root / name
    run.mkdir()
    (run / "fingerprint.txt").write_text(gate["fingerprint"] + "\n")
    (run / "gate.json").write_text(json.dumps(gate))


def test_only_a_passing_gate_is_evidence(tmp_path, monkeypatch):
    """The review case: a run whose fingerprint matches but whose criteria failed must not count."""
    monkeypatch.setattr(__import__(__name__), "RESULTS", tmp_path)
    fp = compute_fingerprint()
    passing = {"fingerprint": fp, "pass": True, **{c: {"pass": True} for c in GATE_CRITERIA}}
    _archive(tmp_path, "2099-01-01-prod-render", {**passing, "pass": False, "SC-001": {"pass": False}})
    _archive(tmp_path, "2099-01-02-prod-render", {**passing, "SC-003": {"pass": False}})
    assert _recorded() == {}
    _archive(tmp_path, "2099-01-03-prod-render", passing)
    assert _recorded() == {fp: "2099-01-03-prod-render"}


def test_harness_gate_ran_against_this_configuration():
    current = compute_fingerprint()
    recorded = _recorded()
    assert current in recorded, (
        "Memory configuration changed since the last harness gate run (FR-021). Run "
        "docs/backlog/097-spike/render-prod.sh and run.sh prod-render (quickstart § 1), and commit "
        "results/<YYYY-MM-DD>-prod-render/ with its passing gate.json and fingerprint.txt. "
        f"Current: {current}; "
        f"recorded: {sorted(recorded.values()) or 'none'}"
    )


# --- SC-001's retrieval leg for preference probes (spec SC-001, amended 2026-11-01) ---


def _gate_module():
    import importlib
    import sys
    spike = str(ROOT / "docs" / "backlog" / "097-spike")
    if spike not in sys.path:
        sys.path.insert(0, spike)
    return importlib.import_module("gate")


def test_preference_probe_counts_on_a_top_three_recall_and_keeps_the_answer_on_record():
    gate = _gate_module()
    pref = {"id": "p16", "kind": "volume-preference", "recall_expect": "spørre først"}
    plain = {"id": "p9", "kind": "volume-no"}
    probes = [(pref, False, "a", False), (plain, True, "b", False)]
    effective, answers = gate.recalled(probes, ['{"probe": "p16", "rank": 2, "top3": true}'])
    assert [ok for _, ok, _, _ in effective] == [True, True]
    assert answers == {"p16": False}


def test_preference_probe_fails_without_a_top_three_recall_and_is_never_left_unjudged():
    gate = _gate_module()
    pref = {"id": "p16", "kind": "volume-preference", "recall_expect": "x"}
    for lines in ([], ['{"probe": "p16", "rank": 4, "top3": false}'], ['{"probe": "p16", "error": "URLError"}'], ["not json"]):
        [(_, ok, _, review)] = gate.recalled([(pref, True, "a", True)], lines)[0]
        assert (ok, review) == (False, False), lines


def test_only_probes_with_a_recall_pattern_use_the_retrieval_leg():
    gate = _gate_module()
    plain = {"id": "p1", "kind": "update"}
    effective, answers = gate.recalled([(plain, False, "a", True)], ['{"probe": "p1", "top3": true}'])
    assert effective == [(plain, False, "a", True)] and answers == {}


def test_the_dataset_marks_exactly_the_preference_probe():
    import json
    dataset = json.loads((ROOT / "docs" / "backlog" / "097-spike" / "dataset.json").read_text())
    marked = {p["id"]: p["recall_expect"] for p in dataset["probes"] if p.get("recall_expect")}
    assert list(marked) == ["p16"]
    session = next(s for s in dataset["sessions"] if s["id"] == "s9")
    import re
    assert re.search(marked["p16"], session["turns"][0], re.I), "the pattern must match the seeded preference"


# --- the preference leg measures the injected recall block (PR #340 review) ---


def _spike_module(name):
    import importlib
    import sys
    spike = str(ROOT / "docs" / "backlog" / "097-spike")
    if spike not in sys.path:
        sys.path.insert(0, spike)
    return importlib.import_module(name)


BLOCK = ("\n[System note: recalled]\n\n# Hindsight Memory (persistent cross-session context)\n"
         "Use this to answer.\n\n- first fact\n- User: ikke foreslå endringer uten å spørre først\n- third\n")


def test_rank_reads_the_items_of_the_injected_block():
    m = _spike_module("recall_from_injected")
    assert m.items(BLOCK)[:2] == ["first fact", "User: ikke foreslå endringer uten å spørre først"]
    assert m.rank(BLOCK, "uten å spørre|spørre først") == 2
    assert m.rank(BLOCK, "nowhere") is None
    assert m.items("no recalled items here") == []


def test_only_this_runs_first_injected_block_per_probe_counts(tmp_path, capsys):
    m = _spike_module("recall_from_injected")
    dataset = tmp_path / "dataset.json"
    dataset.write_text(json.dumps({"probes": [
        {"id": "p16", "q": "Router?", "recall_expect": "spørre først"}, {"id": "p1", "q": "Where?"}]}))
    log = tmp_path / "injected.jsonl"
    rows = [
        {"run": "other/probes", "q": "Router?", "context": BLOCK},              # another candidate
        {"run": "prod-render/probes", "q": "Router?", "context": "\n\n- miss\n- miss\n- miss\n- spørre først"},
        {"run": "prod-render/probes", "q": "Router?", "context": BLOCK},        # a later request
    ]
    log.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    m.main("prod-render", str(dataset), str(log))
    [line] = capsys.readouterr().out.splitlines()
    assert json.loads(line) == {"probe": "p16", "rank": 4, "top3": False, "truncated": False, "source": "injected"}


def test_a_probe_without_an_injected_block_is_an_error_line(tmp_path, capsys):
    m = _spike_module("recall_from_injected")
    dataset = tmp_path / "dataset.json"
    dataset.write_text(json.dumps({"probes": [{"id": "p16", "q": "Router?", "recall_expect": "x"}]}))
    m.main("prod-render", str(dataset), str(tmp_path / "absent.jsonl"))
    assert json.loads(capsys.readouterr().out) == {"probe": "p16", "error": "no injected recall"}


def test_the_proxy_records_injected_recall_only_while_probing(tmp_path, monkeypatch):
    monkeypatch.setenv("LITELLM_SPIKE_KEY", "test")
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "logproxy", ROOT / "docs" / "backlog" / "097-spike" / "llmproxy" / "logproxy.py")
    proxy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(proxy)
    monkeypatch.setattr(proxy, "INJECTED", str(tmp_path / "injected.jsonl"))
    payload = {"messages": [{"role": "system", "content": "s"},
                            {"role": "user", "content": "Router?\n\n<memory-context>" + BLOCK + "</memory-context>"}]}
    for phase in ("sessions", "probes"):
        monkeypatch.setattr(proxy, "run_tag", lambda phase=phase: f"prod-render/{phase}")
        proxy.record_injected(payload)
    proxy.record_injected({"messages": [{"role": "user", "content": "no block"}]})
    [row] = [json.loads(line) for line in (tmp_path / "injected.jsonl").read_text().splitlines()]
    assert row == {"run": "prod-render/probes", "q": "Router?", "context": BLOCK}
