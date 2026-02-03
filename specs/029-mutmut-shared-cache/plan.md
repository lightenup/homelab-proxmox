# Implementation Plan: Mutmut Shared Cache

**Branch**: `029-mutmut-shared-cache` | **Date**: 2026-01-16 | **Spec**: [specs/029-mutmut-shared-cache/spec.md](spec.md)
**Input**: Feature specification from `/specs/029-mutmut-shared-cache/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

Persist mutmut cache outputs on the shared NAS mount (`/mnt/nas/homelab_ci`) using per-branch cache files so PVE and developer laptops can use `mutmut results/show/apply/browse` without rerunning mutations. Document the workflow, align CI to write to the shared cache (or a symlinked `.mutmut-cache`), validate via actionlint and act when editing GitHub Actions workflows.

**Developer verification**: On the laptop, mount `/Volumes/nas/homelab_ci`, symlink `.mutmut-cache` to `/Volumes/nas/homelab_ci/mutmut-cache/<branch>`, and run `mutmut browse` from the repo root to confirm results load without re-running mutations.

## Technical Context

**Language/Version**: Python 3.11 (mutmut/pytest tooling), shell scripts for automation
**Primary Dependencies**: mutmut, pytest, uv, GitHub Actions
**Storage**: NAS NFS share mounted on PVE at `/mnt/nas/homelab_ci` and on developer laptops at `/Volumes/nas/homelab_ci` (per-branch cache file)
**Testing**: mutmut (nightly), pytest baseline; actionlint for workflow linting; act for local workflow validation
**Target Platform**: PVE host (Debian), GitHub Actions runners (Ubuntu), developer laptops (macOS/Linux)
**Project Type**: Infrastructure repo with workflows + Python tooling
**Performance Goals**: Keep nightly mutation runs manageable; enable reuse via cache to avoid re-runs
**Constraints**: No secrets in cache; shared mount must be available; per-branch cache layout
**Scale/Scope**: Single repo, single shared cache mount

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- ✅ **Spec-driven workflow**: Work is defined under `specs/029-mutmut-shared-cache/` with tasks.md.
- ✅ **Secrets policy**: Shared cache contains only code-derived artifacts; no secrets added.
- ✅ **Separation of concerns**: Changes are limited to testing workflow and documentation.
- ✅ **Provider strategy**: No Terraform provider changes.
- ✅ **State management**: No Terraform state changes.
- ✅ **Storage**: Uses existing NAS NFS mount on PVE; no new storage system introduced.
- ✅ **Workflow testing**: Use actionlint and act when modifying `.github/workflows/*` per constitution.

### Constitution Check (Post-Design)

- ✅ No new violations introduced by research or design outputs.
## Project Structure

### Documentation (this feature)

```text
specs/029-mutmut-shared-cache/
├── plan.md              # This file
├── spec.md              # Feature specification
├── tasks.md             # Task list
├── quickstart.md        # Shared cache workflow
└── checklists/
    └── requirements.md  # Spec quality checklist
```

### Source Code (repository root)

```text
.github/workflows/
└── nightly-deeper-verification.yml

python/
└── mutmut.ini
```

**Structure Decision**: Keep existing repo layout; update workflow + mutmut configuration and spec docs only.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| [e.g., 4th project] | [current need] | [why 3 projects insufficient] |
| [e.g., Repository pattern] | [specific problem] | [why direct DB access insufficient] |
