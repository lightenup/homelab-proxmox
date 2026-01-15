# Implementation Plan: Sunset Shell Tools

**Branch**: `028-sunset-shell-tools` | **Date**: 2026-01-14 | **Spec**: [specs/028-sunset-shell-tools/spec.md](spec.md)
**Input**: Feature specification from [specs/028-sunset-shell-tools/spec.md](spec.md)

## Summary

Sunset the majority of operator-invoked shell scripts by consolidating day-to-day workflows behind a single entry point (`go-task` via `Taskfile.yml`), while migrating legacy script functionality into testable Python tooling and/or IaC where appropriate.

Key rules baked into the plan:

- Keep core harness/host-installed/spec tooling unchanged.
- Define protected paths for those areas and enforce them with automated guardrails.
- Preserve downstream compatibility: only introduce new entry points in a way that does not break existing CI/IaC/core harness. Use shims only where updating the caller is impractical/cumbersome.
- Deprecate by moving scripts into `scripts/deprecated/` and ensure there are **zero references** to deprecated scripts in code/CI/IaC/docs.
- Tests are required for every migrated capability: unit + CLI smoke tests with fakes; nightly mutation testing (`mutmut`); optional lab-backed integration tests in GitHub Actions.

## Technical Context

**Language/Version**: Python 3.x (existing repo subproject in `python/`)  
**Primary Dependencies**: Runtime: Python stdlib (preferred), existing repo utilities. Dev/test: `pytest`, `mutmut`  
**Storage**: Local filesystem repo artifacts; Terraform/Ansible state/artifacts as already implemented (no new state system introduced)  
**Testing**: `pytest` (unit + CLI smoke), `mutmut` (nightly), optional lab-backed integration tests in GitHub Actions  
**Target Platform**: macOS/Linux local dev, GitHub Actions runners, Proxmox host (PVE) where harness executes  
**Project Type**: Infrastructure repo with Terraform + Ansible + scripts + a Python tooling subproject  
**Performance Goals**: Fast PR feedback; “Top 10 workflows” runnable within a typical operator session without excessive setup  
**Constraints**: No secrets in logs; no breaking existing CI/IaC/harness entrypoints; incremental migration; deprecations via `scripts/deprecated/` must be reference-free  
**Scale/Scope**: Refactor operator tooling surface; no provider/state strategy change; avoid changing core harness scripts

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- ✅ **Spec-driven workflow**: Work is captured under `specs/028-sunset-shell-tools/` and will be executed via `tasks.md`.
- ✅ **Secrets policy**: No secrets will be introduced; all new tooling must accept secrets via existing environment or gitignored inputs.
- ✅ **Separation of concerns**: Terraform remains responsible for resource existence; Ansible remains responsible for in-guest configuration. This feature only changes orchestration/tooling.
- ✅ **Provider strategy**: No Terraform provider migration.
- ✅ **State management**: No remote state introduced.

## Project Structure

### Documentation (this feature)

```text
specs/028-sunset-shell-tools/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
└── tasks.md             # Phase 2 output (/speckit.tasks)
```

### Source Code (repository root)

```text
Taskfile.yml

python/
  src/homelab_proxmox_orchestrator/
  tests/
  pytest.ini
  mutmut.ini

scripts/
  lab/                 # protected harness scripts
  healthcheck/
  ci/
  monitoring/ dr/ tailscale/
  deprecated/

docs/
ansible/
terraform/
.github/workflows/
```

**Structure Decision**: Keep the existing repository structure. Add `Taskfile.yml` at repo root, and add new Python CLI modules within `python/src/homelab_proxmox_orchestrator/` plus tests in `python/tests/`.

## Complexity Tracking

No constitution violations identified; no complexity exceptions required.

## Phase 0: Outline & Research

Generate [specs/028-sunset-shell-tools/research.md](research.md) covering:

- Taskfile runner choice and compatibility considerations
- Shim policy guidelines and removal conditions
- Deprecation mechanics (`scripts/deprecated/`) and enforcement
- Test strategy: unit/CLI smoke vs lab-backed integration; nightly mutmut scope

## Phase 1: Design & Contracts

Generate:

- [specs/028-sunset-shell-tools/data-model.md](data-model.md) capturing key entities (Legacy Script, Task, Migration Item, Deprecation Notice) and state transitions (active → shim → deprecated → deleted).
- `specs/028-sunset-shell-tools/contracts/` capturing the public “task/cli” interface contract (task names, inputs, outputs, exit codes, and stability guarantees).
- [specs/028-sunset-shell-tools/quickstart.md](quickstart.md) describing how to run tasks and tests locally and in CI.

## Phase 1.5: Agent Context Update

Run `.specify/scripts/bash/update-agent-context.sh copilot` so agent context reflects the Taskfile + testing decisions.

## Phase 2: Planning (for `/speckit.tasks`)

Break work into incremental slices aligned to the spec’s “Top 10 day-to-day workflows” and deprecation rules:

- Introduce `Taskfile.yml` without breaking existing callers.
- Implement Python-backed tasks with unit + CLI smoke tests.
- Add guardrails to prevent references to `scripts/deprecated/`.
- Migrate/replace workflows one-by-one, updating docs and the January candidate list as removals/deprecations land.

**Re-check (post Phase 1 design artifacts)**:

- ✅ Confirm design artifacts are created under `specs/028-sunset-shell-tools/`.
- ✅ Confirm no secret material introduced.
