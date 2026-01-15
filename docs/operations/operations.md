# Operations

This page describes the supported operational entrypoints in this repo.

## Operator-only vs rebuild-critical

This repo intentionally distinguishes between:

- **Rebuild-critical** tasks: part of the infrastructure rebuild path and suitable for repeatable automation.
- **Operator-only** tasks: day-to-day convenience workflows that may depend on local context or interactively supplied inputs.

The operator-facing entrypoint is the repo-root Taskfile (the `task` command). Run `task -l` to discover available workflows.

### Rebuild-critical

These tasks are used to rebuild or deploy infrastructure and services and are the safest to automate.

Examples:

- `terraform:validate`, `terraform:plan`, `terraform:apply`
- `deploy:lab`
- `inventory:update`

**Safety**:

- Destructive operations require explicit confirmation.
- Prefer running rebuild-critical flows via the bounded-input GitHub Actions workflows.

### Operator-only

These tasks are intended for day-to-day maintenance and admin work.

Examples:

- `service:add`, `service:change`, `service:remove`
- `healthcheck:run`
- `summary:render`

## Deprecation policy

Deprecation and shim rules are documented in docs/operations/tooling-sunsetting.md.
