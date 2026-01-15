# Research: Sunset Shell Tools

**Feature**: [specs/028-sunset-shell-tools/spec.md](spec.md)
**Date**: 2026-01-14

## Decision 1: Task runner (`go-task`)

**Decision**: Use `go-task` with a repo-root `Taskfile.yml` as the operator entry point.

**Rationale**:

- “Taskfile” conventionally refers to `go-task` in many infra repos.
- It provides a clear, discoverable command surface for operators.
- It can wrap existing scripts during migration without forcing an immediate full rewrite.

**Alternatives considered**:

- `make`: common, but tends to become a shell wrapper layer and is less structured.
- `just`: great UX, but “Taskfile” wording implies `go-task` and would require a naming pivot.

## Decision 2: Compatibility & shim strategy

**Decision**: Keep shims only when updating the downstream caller is impractical/cumbersome (typically CI/IaC/core harness references a stable script path). Otherwise, update callers to use `task ...`.

**Rationale**:

- Allows aggressive simplification without breaking critical automation.
- Avoids long-lived legacy entrypoints.

**Alternatives considered**:

- Keep shims for everything: safer short-term, but encourages indefinite legacy usage.
- No shims: too risky given existing callers across Ansible playbooks and harness scripts.

## Decision 3: Deprecation mechanism

**Decision**: Deprecate by moving scripts under `scripts/deprecated/`. Deprecated scripts must have zero references in code/CI/IaC/docs.

**Rationale**:

- Physical move makes deprecations obvious and prevents accidental reuse.
- Eliminates ambiguity about what is supported.

**Alternatives considered**:

- Inline deprecation warnings: easy to miss and easy for callers to keep using.
- Leaving deprecated scripts in place: conflicts with “sunset” goal.

## Decision 4: Test strategy per migration step

**Decision**:

- Every migrated capability adds unit tests plus CLI smoke tests using fakes.
- Nightly mutation testing via `mutmut` validates test strength.
- Integration tests may run in GitHub Actions against the lab environment when higher confidence is needed.

**Rationale**:

- Unit + smoke tests give fast, hermetic feedback.
- Mutation testing increases confidence that tests actually protect behavior.
- Lab-backed integration is reserved for parts that are too coupled to validate hermetically.

**Alternatives considered**:

- Integration-only: too slow and flaky for iterative migration.
- Unit-only: insufficient confidence for CLI orchestration flows.

## Decision 5: “January candidate list” location

**Decision**: Treat [specs/candidate/january.md](../candidate/january.md) as the “January candidate list” referenced by this feature.

**Rationale**:

- It is the repository’s existing January 2026 candidate automation list.

**Alternatives considered**:

- Creating a new doc in `docs/`: would split the canonical list and add drift risk.
