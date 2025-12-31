# Implementation Plan: Assertion Alignment

**Branch**: `019d-assertion-alignment` | **Date**: 2025-12-31 | **Spec**: [specs/019d-assertion-alignment/spec.md](specs/019d-assertion-alignment/spec.md)
**Input**: Feature specification from `specs/019d-assertion-alignment/spec.md`

## Summary

Refactor Tier 1 and Tier 2 validations in Ansible playbooks to use `ansible.builtin.assert` with a standardized style. Generate machine-readable JSON assertion reports (`reports/assertions.<phase>.json`) that are integrated into the Evidence Pack. This ensures validations are self-describing, readable, and machine-verifiable.

## Technical Context

**Language/Version**: Ansible (YAML), Python (stdlib only)
**Primary Dependencies**: `ansible.builtin.assert`, `ansible.builtin.set_fact`, `ansible.builtin.copy`
**Storage**: JSON files in `{{ evidence_dir }}/reports/`
**Testing**: `pve-lab` harness, manual playbook runs
**Target Platform**: Proxmox LXC/VMs, Ansible Controller
**Project Type**: Infrastructure as Code (Ansible)
**Performance Goals**: Minimal overhead on playbook execution
**Constraints**: No new non-stdlib dependencies on controller
**Scale/Scope**: Refactor existing bootstrap and tier2 playbooks

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Spec-Driven Workflow**: Compliant. Driven by `specs/019d-assertion-alignment/spec.md`.
- **Secrets Policy**: Compliant. No secrets in assertions.
- **Separation of Concerns**: Compliant. Ansible owns internal validation.
- **Provider Strategy**: N/A.
- **Networking**: N/A.
- **Access Control**: N/A.
- **Baseline Decisions**: Compliant. State is local.
- **Workflow & Process**: Compliant.
- **Repo Layout**: Compliant.

## Project Structure

### Documentation (this feature)

```text
specs/019d-assertion-alignment/
├── plan.md              # This file
├── research.md          # Phase 0 output (skipped, spec is detailed)
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
└── tasks.md             # Phase 2 output
```

### Source Code (repository root)

```text
ansible/
├── playbooks/
│   ├── lab_bootstrap.yml
│   ├── lab_tier2_pve.yml
│   └── roles/
│       └── assertion_utils/  # New role for reporting logic? Or inline.
scripts/
└── lab/
    └── test-harness.sh
```

**Structure Decision**: Refactor existing playbooks. Introduce a reusable pattern (possibly a role or include) for writing the assertion report.

## Complexity Tracking

N/A
