# Implementation Plan: Monitoring Stack Version Currency

**Branch**: `090-monitoring-version-currency` | **Date**: 2026-10-22 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/090-monitoring-version-currency/spec.md`

## Summary

Three parts:

1. **Upgrade** (P1). Raise the pins: Grafana `12.3.1 → 13.2.4`, Prometheus `v3.8.1 → v3.13.5`
   (LTS), Alertmanager `v0.30.0 → v0.34.1`, blackbox `v0.28.0 → v0.29.1`, Telegraf
   `1.37.0 → 1.40.2`, node_exporter `1.10.2 → 1.12.1`. No component config needs to change
   (research R-02, R-03). Telegraf 1.37 turned out to be out of support as well.
   - In `monitoring_stack`, run `promtool check config/rules` and `amtool check-config` with the
     target images **before** `docker compose up -d` (R-05).
   - Rollout:
     1. Before snapshot.
     2. Side-by-side rehearsal on the monitoring LXC, including a temporary Grafana 13.2 container
        on a copy of its data (R-06).
     3. `pct snapshot`.
     4. One prod deploy.
     5. After snapshot and diff.
     6. node_exporter, host by host.

   The lab path cannot be used, because lab and prod share an address space (the 072 and 067
   issues).
2. **Single source** (P2). Delete the five version lines from `roles/monitoring_stack/defaults`.
   They are dead copies, because the playbook `include_vars` the group_vars file. Move
   `node_exporter_version` to `group_vars/all/vars.yml`. Fix `runbook-upgrades.md`, which today
   says to edit the dead copy (R-04).
3. **Currency check** (P2). Add a stdlib-only Python module, `version_currency.py`, in the
   existing package. It reads `ansible/version-sources.yml` (pin → GitHub repo, endoflife.date
   product, policy), compares against releases and support windows, and posts one ntfy message to
   topic `versions` when something is behind (R-08 to R-12).
   - It runs weekly from a new scheduled workflow on the self-hosted `pi-ci` runner, and
     repeats every finding until the pin is fixed.
   - It covers the monitoring pins and every service pin that has a source. Pins it cannot check
     are listed by name.
   - A failed run (source or publish error) fails the workflow and never passes silently.

Research: [research.md](./research.md). Data: [data-model.md](./data-model.md). Interface:
[contracts/currency-check.md](./contracts/currency-check.md). Rollout and validation:
[quickstart.md](./quickstart.md).

## Technical Context

**Language/Version**: Ansible (existing roles), YAML. Python 3.11 for the new module (the CI
and runner baseline; `nightly-deeper-verification.yml` asserts ≥ 3.11). GitHub Actions YAML.

**Primary Dependencies**: Python stdlib (`urllib.request`, `json`, `argparse`, `datetime`) and
PyYAML (already in `python/requirements-test.txt` and the runner's environment). No new packages.
External data: GitHub REST releases API and the endoflife.date API. Container images:
`grafana/grafana`, `prom/prometheus`, `prom/alertmanager`, `prom/blackbox-exporter` and
`telegraf`. node_exporter is a GitHub release binary.

**Storage**: the Docker volumes `prometheus_data`, `grafana_data` (SQLite) and `alertmanager_data`
on the monitoring LXC's root disk, which is LVM-thin and supports snapshots. The check keeps no
state.

**Testing**: pytest.

- Unit tests in `python/tests/version_currency/` use faked HTTP and cover the policies, tag
  parsing, exit codes and the message.
- The guard test `python/tests/guardrails/test_version_pins.py` checks one assignment per pin,
  that every pin is in the sources map, and that the workflow is present.
- Both run in PR CI through `scripts/ci/python-tests.sh`.
- Also run `ansible-playbook --syntax-check`, `ansible-lint`, and `act -l` / `act -n` for the
  workflow.
- Live checks are in the quickstart: before/after diff, rehearsal and test alert.

**Target Platform**: the monitoring LXC (`192.168.1.214`, Debian 12, Docker Compose), all 11
service LXCs (node_exporter), and the `pi-ci` self-hosted runner (the check).

**Project Type**: infrastructure configuration (Ansible-managed homelab), plus one small Python
CLI module.

**Performance Goals**: N/A. A check run finishes well inside its 10-minute job timeout, and each
HTTP call has a 20 s timeout. The test alert arrives within 5 minutes (SC-003).

**Constraints**:

- Nothing lost silently: targets, rules and dashboards must be identical before and after
  (FR-007).
- A Grafana pin change cannot roll back after the storage migration; a snapshot restore can
  (R-02).
- The prod deploy path for monitoring needs `allow_override_failed_lab_gate=true` (072).
- The ntfy token comes from the vault, not a duplicate GitHub secret.
- The Mac cannot push over git, reach Docker Hub, or reach the tailnet (Zscaler). Push through
  the GitHub API, as described in `AGENTS.md`.

**Scale/Scope**: 6 component pins and 20 pins under check (5 monitoring components plus node_exporter, and 14 in the services block).

- Changed: about 8 files (`group_vars` ×2, role defaults ×2, `validate_alerts.yml`, `main.yml`
  task order, `runbook-upgrades.md`, ntfy defaults and ACL check).
- Added: 5 files (module, sources map, workflow, 2 test files).
- Deleted: none.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Spec-driven workflow | PASS | Work comes from `specs/090-*`. The runbook correction ships in the same change. Spec clarifications are recorded. |
| II. Secrets policy | PASS | The new ntfy token and password hash go into the existing gitignored vault. The workflow decrypts only that key with the existing `ANSIBLE_VAULT_PASSWORD` secret and masks it. The Grafana password in quickstart commands is passed through the environment. |
| III. Separation of concerns | PASS | No Terraform changes. Ansible changes stay inside the LXCs. The snapshot is an operator step on `pve`, not Terraform. |
| IV. Code economy | PASS | Removes duplicate pins (net lines go down in Ansible). Validation extends the existing `validate_alerts.yml`. The check is one module in the existing package, uses only the stdlib plus PyYAML, and makes no registry queries (R-11). The sources map is data with 20 entries today. No state store (R-09). |
| V. Dual-provisioning parity | PASS | Deploys use the existing pipeline, which also runs from a laptop via `pve-service-deploy`. The check runs the same command in CI and locally (`--dry-run`, or `NTFY_TOKEN` to publish). The ntfy token is read from the vault in both contexts. The `pct snapshot` and rehearsal are one-off operator steps, not provisioning operations, and are recorded in the quickstart. |
| Test-driven changes | PASS | Unit tests for the module's logic. A guard test for the single-source rule and source coverage. Dry-run mode. Live verification in the quickstart. |
| CI/CD: no destructive automation without barriers | PASS | The upgrade goes through the gated `Prod 1 → Prod 2` deploy. Validators now gate the restart. The check is read-only, apart from posting a message. |
| Local workflow testing | PASS (planned) | `act -l` and `act -n -W .github/workflows/version-currency.yml workflow_dispatch` in quickstart §0. |

**Post-design re-check (after Phase 1)**: all PASS. No violations, so Complexity Tracking is
empty.

## Project Structure

### Documentation (this feature)

```text
specs/090-monitoring-version-currency/
├── plan.md              # This file
├── research.md          # Phase 0: R-01 … R-13
├── data-model.md        # Phase 1: pins, sources map, findings, before/after record
├── quickstart.md        # Phase 1: validation and rollout record (§0–§9)
├── contracts/
│   └── currency-check.md  # CLI, workflow, ntfy publisher, message format
├── checklists/
│   └── requirements.md
└── tasks.md             # Phase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
ansible/
├── group_vars/
│   ├── all/vars.yml                     # + node_exporter_version
│   ├── monitoring/vars.yml              # pins raised; blackbox_exporter_version moved into the version block
│   └── services/vars.yml                # unchanged (service pins are read by the check)
├── version-sources.yml                  # NEW: pin → policy/github/endoflife map (data-model §2)
└── roles/
    ├── monitoring_stack/
    │   ├── defaults/main.yml            # − five *_version lines
    │   └── tasks/
    │       ├── main.yml                 # validation moved before compose up
    │       ├── compose_stack.yml        # split: render configs, then (after validation) `up -d`
    │       └── validate_alerts.yml      # + promtool check config, + amtool check-config, target images
    ├── node_exporter/defaults/main.yml  # − node_exporter_version
    └── ntfy/defaults/main.yml           # + version_check user (token/hash from vault)

python/
├── src/homelab_proxmox_orchestrator/
│   └── version_currency.py              # NEW: fetch, evaluate, report, publish; __main__ CLI
└── tests/
    ├── version_currency/test_version_currency.py   # NEW: unit tests (faked HTTP)
    └── guardrails/test_version_pins.py             # NEW: FR-017 guard

.github/workflows/
└── version-currency.yml                 # NEW: weekly + workflow_dispatch(dry_run), self-hosted

scripts/healthcheck/ntfy-acl-check.sh    # + version_check row/column (082 SC-002 matrix)
docs/operations/monitoring/runbook-upgrades.md   # pin step → group_vars; rollback = snapshot for Grafana
docs/backlog/improvement-candidates.md   # + monitoring_stack defaults drift (non-version values)
```

**Structure Decision**: extend existing roles, tasks and the Python package in place. The only new
artifacts are the ones the check needs: module, sources map, workflow, and their two test files.
The sources map sits in `ansible/` next to the pins it describes. It is not under `group_vars/`,
where Ansible would load it as a group.

## Implementation Notes

- **Task ordering in `monitoring_stack`**: today `compose_stack.yml` renders the configs and then
  runs `docker compose up -d` inline. Split it at the `Start monitoring stack` task, so the order
  is: render → `validate_alerts.yml` → up. The 072 contract guard stays where it is, before
  rendering.
- **`validate_alerts.yml`**: keep the per-file `promtool check rules` loop. Add
  `promtool check config /etc/prometheus/prometheus.yml` and
  `amtool check-config /etc/alertmanager/alertmanager.yml`, each run with the pinned (target)
  image. The alertmanager config contains credentials, so use `no_log: true` on the amtool task
  and print only `rc` and the error text.
- **`version-sources.yml` coverage**: the guard test parses the version blocks. In
  `group_vars/monitoring/vars.yml` that is all `*_version` keys. In `group_vars/services/vars.yml`
  it is the keys from `# Service versions` to the next blank line (14 today), plus
  `node_exporter_version`. The test asserts that each key has exactly one entry and that each
  entry's variable exists in its file.
- **Grafana tag format**: the Docker tag has no `v` (`13.2.4`); the GitHub tag is `v13.2.4`.
  Parsing compares numeric cores, so the pin format stays whatever the image needs.
- **Monitoring before services in the report**: sort by the order in the sources file. Put
  monitoring entries first in the file.

## Complexity Tracking

No constitution violations.
