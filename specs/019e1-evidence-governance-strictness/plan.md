# Implementation Plan: Evidence Governance Strictness & Self-Verification Gate

**Branch**: `019e1-evidence-governance-strictness` | **Date**: 2025-12-31 | **Spec**: [specs/019e1-evidence-governance-strictness/spec.md](specs/019e1-evidence-governance-strictness/spec.md)
**Input**: Feature specification from `specs/019e1-evidence-governance-strictness/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

This feature enforces strict governance on Evidence Packs by making the Check Catalog (`scripts/lab/checks.d/catalog.json`) the authoritative Single Source of Truth (SSOT) for titles, phases, and ownership. It also introduces a "Self-Verification Gate" where every `pve-lab suite` run automatically verifies its own output, ensuring immediate feedback without relying on a CI pipeline.

Key technical changes:
- Update `verify_evidence.py` to enforce strict catalog matching (titles, phases) and ownership rules (Ansible vs Harness origin).
- Update `pve-lab` suite command to trigger auto-verification.
- Update `diff_evidence.py` to fallback to catalog titles for stable reporting.
- Add new negative test fixtures to `scripts/lab/fixtures/evidence-packs/`.

## Technical Context

**Language/Version**: Python 3 (stdlib only: json, pathlib, sys, argparse)
**Primary Dependencies**: None (Standard Library)
**Storage**: Filesystem (JSON artifacts in `artifacts/` and `scripts/lab/fixtures/`)
**Testing**: `scripts/lab/ci-verify.sh` (Bash integration test running Python verifier against fixtures)
**Target Platform**: macOS/Linux (Development & CI environments)
**Project Type**: CLI Tooling / Scripting
**Performance Goals**: Verification should be near-instant (<1s) for typical packs.
**Constraints**: Must not introduce new Python dependencies (pip packages). Must work offline.
**Scale/Scope**: Validates ~50-100 checks per run.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Spec-Driven Workflow**: Compliant. Spec `019e1` created.
- **Secrets Policy**: Compliant. No secrets involved in governance logic.
- **Separation of Concerns**: Compliant. Governance logic resides in `scripts/lab/`, distinct from Terraform/Ansible.
- **Provider Strategy**: N/A.
- **Networking**: N/A.
- **Access Control**: N/A.
- **Baseline Decisions**: Compliant. Uses local filesystem for artifacts.
- **Workflow & Process**: Enhances workflow by adding local verification gate.
- **Repo Layout**: Compliant. Uses `scripts/lab/` and `specs/`.
- **Governance**: This feature *implements* governance.

## Project Structure

### Documentation (this feature)

```text
specs/019e1-evidence-governance-strictness/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
└── tasks.md             # Phase 2 output
```

### Source Code (repository root)

```text
scripts/lab/
├── verify_evidence.py       # UPDATED: Strictness logic
├── diff_evidence.py         # UPDATED: Catalog fallback
├── pve-lab                  # UPDATED: Auto-verify integration
├── checks.d/
│   └── catalog.json         # REFERENCE: SSOT
└── fixtures/evidence-packs/ # UPDATED: New invalid fixtures
    ├── invalid-title-mismatch/
    ├── invalid-phase-missing/
    ├── invalid-owner-mismatch/
    └── invalid-ansible-check-not-in-assertion-report/
```

**Structure Decision**: Extend existing `scripts/lab/` tooling. No new top-level directories required.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

N/A - No violations.
