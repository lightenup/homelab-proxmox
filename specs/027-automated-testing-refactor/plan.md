# Implementation Plan: Automated Testing Refactor

**Branch**: `027-automated-testing-refactor` | **Date**: 2026-01-13 | **Spec**: [specs/027-automated-testing-refactor/spec.md](spec.md)
**Input**: Feature specification from [specs/027-automated-testing-refactor/spec.md](spec.md)

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

Introduce a Python-based automation runner (initially as a thin wrapper around existing bash entrypoints) to reduce shell orchestration over time while keeping existing GitHub Actions workflow UX and evidence packs stable. Add a layered automated testing strategy (fast PR checks + nightly deeper verification) covering:

- Deterministic, bounded run summaries (golden tests)
- Orchestrator/runner decision logic (unit tests + mutation testing)
- Selected Ansible roles (Molecule)
- Terraform modules (format/validate everywhere; `terraform test` where feasible)

Migration is incremental (slice-by-slice), preserving current behavior and operational safety.

## Technical Context

<!--
  ACTION REQUIRED: Replace the content in this section with the technical details
  for the project. The structure here is presented in advisory capacity to guide
  the iteration process.
-->

**Language/Version**: Python 3 (target: 3.11+) for new runner code; existing bash for orchestration remains during migration
**Primary Dependencies**: Runtime: Python stdlib only (initially). Dev/test: `pytest`, `mutmut`, optional `ruff`
**Storage**: Local filesystem artifacts and evidence packs (existing pattern)
**Testing**: `pytest` (unit + golden), `mutmut` (nightly mutation), `molecule` (Ansible roles), `terraform fmt/validate/test` (Terraform)
**Target Platform**: GitHub Actions runners (Linux), Proxmox host (PVE) remote executor, local developer machines (macOS/Linux)
**Project Type**: Infrastructure repo with a small Python subproject + existing bash scripts
**Execution Location (initial)**: Runner executes on the Proxmox host (PVE) alongside existing `scripts/lab/*` entrypoints; GitHub Actions continues to SSH into PVE (workflow UX unchanged).
**Performance Goals**: PR validation completes <10 minutes for typical changes; summaries render in seconds and remain bounded
**Constraints**: No secrets in logs/summaries; bounded output; no new workflow UX; preserve evidence pack semantics; incremental migration only
**Scale/Scope**: One repo with Terraform + Ansible + workflow automation; initially focus on runner + testing harness, then expand coverage

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- ✅ **Spec-driven workflow**: This plan produces artifacts under `specs/027-automated-testing-refactor/` and does not implement code changes outside an approved `tasks.md`.
- ✅ **Secrets policy**: Planning/artifacts do not include real secrets and require using placeholders and environment/gitignored inputs.
- ✅ **Separation of concerns**: Terraform remains responsible for machine existence/sizing; Ansible remains responsible for in-guest config; runner coordinates without mixing responsibilities.
- ✅ **Provider strategy**: No provider migration proposed.
- ✅ **State management**: No remote state introduced.
- ✅ **Workflow testing expectation**: When workflows are changed in implementation, validate with `act` when feasible (document if not).

**Re-check (post Phase 1 design artifacts)**:
- ✅ Design artifacts created under `specs/027-automated-testing-refactor/` only.
- ✅ No secret material introduced in spec/plan/research/contracts/quickstart.

## Project Structure

### Documentation (this feature)

```text
specs/027-automated-testing-refactor/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)
<!--
  ACTION REQUIRED: Replace the placeholder tree below with the concrete layout
  for this feature. Delete unused options and expand the chosen structure with
  real paths (e.g., apps/admin, packages/something). The delivered plan must
  not include Option labels.
-->

```text
.github/workflows/
ansible/
terraform/
scripts/
  healthcheck/
  lab/

# Added by this feature (planned)
src/
  homelab_proxmox_orchestrator/
    __init__.py
    cli.py
    orchestrator.py
    exec.py
    models.py

tests/
  orchestrator/
    fixtures/
    test_*.py

ansible/roles/
  <service role>/
    molecule/
      default/
        molecule.yml
        converge.yml
        verify.yml
```

**Structure Decision**: Add a small `src/` + `tests/` Python subproject for the automation runner and its tests, while keeping existing infrastructure layout intact.

## Complexity Tracking

No constitution violations identified; no complexity exceptions required.

## Phase 0: Outline & Research

This plan intentionally keeps runtime dependencies minimal (stdlib-first) and focuses on adding testability without changing operator UX.

Research outputs are captured in [specs/027-automated-testing-refactor/research.md](research.md).

Key decisions to finalize in research:

- Where the runner code lives and how it is invoked (module execution via `PYTHONPATH=python/src` vs packaging/install)
- Mutation testing scope and reporting
- Molecule scenario approach for Docker-based roles
- Terraform test strategy given current Terraform version constraints

## Phase 1: Design & Contracts

Design artifacts are captured in:

- [specs/027-automated-testing-refactor/data-model.md](data-model.md)
- [specs/027-automated-testing-refactor/contracts/](contracts/)
- [specs/027-automated-testing-refactor/quickstart.md](quickstart.md)

## Phase 2: Planning (for `/speckit.tasks`)

Translate the migration slices into a `tasks.md` that is:

- Incremental (4–7 independently shippable slices)
- Test-driven (each slice adds or updates automated tests)
- Safe (no secrets; no mixing Terraform/Ansible responsibilities)

The tasks should explicitly separate PR checks from nightly checks and document when `act` and real GitHub Actions runs are required for validation.
