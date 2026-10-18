# Implementation Plan: Confidence Suite Trim

**Branch**: `086-confidence-suite-trim` | **Date**: 2026-10-18 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/086-confidence-suite-trim/spec.md`

## Summary

This feature cuts the promote-time confidence suite from about 18 minutes to about 8, and skips it when none of the files it reads have changed. It makes two changes:

1. **Run one profile.** `cmd_confidence_suite` in `scripts/lab/pve-lab` runs only the `hypervisor-nested-workload` profile. That profile already covers `bootstrap` and `hypervisor-control-plane`.
2. **Gate on the suite's real dependencies.** The inline regex in the `confidence_gate` job is replaced with a path-list file, `scripts/ci/confidence-suite-paths.txt`, read with `grep -Ef`. A pytest drift guard parses the harness and lab playbooks and fails PR CI if any dependency isn't covered by the list.

The gate logic from 063 is unchanged: force-run, the last-verified base, fail-safe defaults, and skip-as-pass.

## Technical Context

**Language/Version**: Bash (harness, workflow `run:` step), GitHub Actions YAML, Python 3.11 (pytest). No new language.

**Primary Dependencies**: Existing `pve-lab` harness, `actions/checkout@v4`, `git`, `grep -E`, and pytest with PyYAML (already in `python/requirements-test.lock.txt`).

**Storage**: N/A. The path list is a checked-in text file.

**Testing**: pytest under `python/tests/workflows/`, run by `scripts/ci/python-tests.sh` in PR CI. One lab run, forced with `run_confidence_suite=true`, checks the suite's timing and evidence.

**Target Platform**: The GitHub-hosted runner (gate job) and the self-hosted `pve` host (suite).

**Project Type**: CI/infrastructure configuration.

**Performance Goals**: A suite run takes 10 minutes or less (SC-001). The gate's cost is unchanged.

**Constraints**:
- Prefer a false run over a false skip.
- Don't change what the suite checks, beyond removing duplicated profiles.
- Don't touch the destructive-plan gate, LAB apply, or `lxc-apply-prod.yml`.

**Scale/Scope**: About 4 files changed or added, plus spec docs.

## Constitution Check

| Principle | Status |
|---|---|
| I. Spec-Driven | ✅ Work is driven by `specs/086-…/tasks.md`. The 063 spec gets superseded notes in the same change. |
| II. Secrets | ✅ No secrets are touched. The gate job uses only `github.token`, as before. |
| III. Separation of Concerns | ✅ No Terraform or Ansible responsibility changes. |
| IV. Code Economy | ✅ One new data file. It's justified because it has two consumers today: the gate step and the drift test. One new test file, which follows the existing `test_workflow_inputs.py` pattern. No new abstractions. |
| V. Dual-Provisioning Parity | ✅ `pve-lab confidence` behaves the same from a laptop and from CI. The path list can be checked locally with `git diff --name-only A B \| grep -Ef scripts/ci/confidence-suite-paths.txt`. |
| Test-Driven Changes | ✅ The pytest drift and replay tests are written before the workflow edit, and the lab run is forced once. |
| Local Workflow Testing | ⚠️ `act` isn't installed on this dev box. YAML parse is covered by pytest and pre-commit. Record this in the PR. |

Post-design re-check: no violations, so Complexity Tracking is empty.

## Project Structure

### Documentation (this feature)

```text
specs/086-confidence-suite-trim/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/confidence-suite-paths.md
├── checklists/requirements.md
└── tasks.md            # /speckit-tasks
```

### Source Code (repository root)

```text
scripts/lab/pve-lab                                   # cmd_confidence_suite + usage line
scripts/ci/confidence-suite-paths.txt                 # NEW — gate path list (one ERE per line)
.github/workflows/lxc-promote-prod.yml                # confidence_gate: grep -Ef the list; fail-safe if missing
python/tests/workflows/test_confidence_gate_paths.py  # NEW — replay + closure + wiring tests
specs/063-ci-confidence-path-gate/spec.md             # "superseded by 086" notes on FR-002, FR-008
```

**Structure Decision**: Use the existing layout. CI helpers live in `scripts/ci/`, and workflow contract tests live in `python/tests/workflows/`.

## Complexity Tracking

None.
