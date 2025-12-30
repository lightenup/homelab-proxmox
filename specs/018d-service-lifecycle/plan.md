# Implementation Plan: Golden Paths: Service Lifecycle

**Branch**: `018d-service-lifecycle` | **Date**: 2025-12-30 | **Spec**: [specs/018d-service-lifecycle/spec.md](specs/018d-service-lifecycle/spec.md)
**Input**: Feature specification from `specs/018d-service-lifecycle/spec.md`

## Summary

Implement "Golden Paths" for adding, changing, and removing services to minimize duplication and enforce a Single Source of Truth (SSOT) in the Ansible inventory. This involves creating a runbook, a service template, and enhancing the healthcheck runner to support strict schema validation, drift detection (zombie services), and non-HTTP services.

## Technical Context

**Language/Version**: Python 3.11 (Healthcheck runner), Ansible (Inventory/Automation), Terraform (Infrastructure).
**Primary Dependencies**: `ansible-core`, `terraform`, `python-requests` (Healthchecks).
**Storage**: Git (Inventory files).
**Testing**: Manual verification, Healthcheck runner self-tests.
**Target Platform**: Linux (Debian LXCs), macOS (Operator machine).
**Project Type**: Infrastructure as Code / Automation.
**Performance Goals**: Healthchecks < 10s total. Drift check < 30s.
**Constraints**: Must work with existing mDNS `.local` setup. No new database or service registry.
**Scale/Scope**: ~10-20 services.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Spec-Driven Workflow**: Compliant. Working from `specs/018d-service-lifecycle`.
- **Secrets Policy**: Compliant. No secrets involved in metadata schema.
- **Separation of Concerns**: Compliant. Terraform owns infra existence; Ansible owns service config/metadata.
- **Provider Strategy**: N/A.
- **Networking**: Compliant. Uses existing network model.
- **Access Control**: N/A.
- **Baseline Decisions**: Compliant.
- **Workflow & Process**: Compliant. Updates `scripts/` and `docs/`.

## Project Structure

### Documentation (this feature)

```text
specs/018d-service-lifecycle/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
└── tasks.md             # Phase 2 output
```

### Source Code (repository root)

```text
docs/
├── operations/
│   └── golden-paths-service-lifecycle.md  # New runbook
└── templates/
    └── service-host_vars.example.yml      # New template

scripts/
├── healthcheck/
│   └── healthcheck.py                     # Updated runner
└── lifecycle/                             # New helper scripts
    ├── add_service.sh
    ├── remove_service.sh
    └── verify_service.sh
```

**Structure Decision**: Extend existing `scripts/healthcheck/` and add `scripts/lifecycle/` for new helpers. Documentation added to `docs/`.

## Complexity Tracking

N/A - No constitution violations.
