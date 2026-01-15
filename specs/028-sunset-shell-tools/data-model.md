# Data Model: Sunset Shell Tools

**Feature**: [specs/028-sunset-shell-tools/spec.md](spec.md)

## Entities

### Legacy Script

Represents an existing script currently used by operators, CI, IaC, or the harness.

**Key fields**:

- `path`: repository-relative path
- `purpose`: one-line intent
- `caller_set`: known callers (docs/CI/IaC/harness)
- `replacement`: the task/command that replaces it
- `status`: lifecycle state (see below)

### Task

A named operation exposed through `go-task`.

**Key fields**:

- `name`: stable identifier (e.g., `service:remove`)
- `inputs`: required parameters / env vars
- `outputs`: key observable outputs (messages, artifact paths)
- `safety`: whether the task is destructive and requires confirmation

### Migration Item

Tracks one unit of migration work from legacy script to replacement.

**Key fields**:

- `legacy`: legacy script path(s)
- `new_task`: replacement task name
- `tests`: references to tests that validate parity
- `docs_updates`: list of docs that must be updated
- `shim_needed`: boolean + rationale
- `removal_condition`: when a shim can be removed

### Deprecation Notice

A user-visible signal that a legacy capability is no longer supported as a first-class entrypoint.

**Key fields**:

- `deprecated_path`: path under `scripts/deprecated/`
- `replacement`: task name
- `date`: deprecation date

## State Machine

### Legacy Script Lifecycle

- `active`: script is supported and may be referenced.
- `shim`: legacy entry point remains, but it forwards to the new task/implementation; it has a documented removal condition.
- `deprecated`: script is moved under `scripts/deprecated/` and must not be referenced by code/CI/IaC/docs.
- `deleted`: script removed from repository.

**Allowed transitions**:

- `active` → `shim`
- `active` → `deprecated`
- `shim` → `deprecated`
- `deprecated` → `deleted`

**Guards**:

- Any transition to `deprecated` requires: all references removed and docs updated.
- Any transition to `deleted` requires: replacement validated + docs updated.
