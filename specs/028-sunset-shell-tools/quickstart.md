# Quickstart: Sunset Shell Tools

**Feature**: [specs/028-sunset-shell-tools/spec.md](spec.md)

## Prerequisites

- `go-task` installed (`task` command available)
- Python tooling uses the existing repo conventions under `python/`

## Operator usage

- List tasks:
  - `task -l`

- Run a task:
  - `task <task-name>`

- Variables (example):
  - `task service:add -- SERVICE=myservice PORT=8080 PATH=/`

## Tests

- Run fast tests (unit + CLI smoke):
  - `cd python && .venv/bin/python -m pytest -c pytest.ini`

## Mutation testing (nightly-quality check)

- Run mutmut locally (optional):
  - `cd python && .venv/bin/mutmut run --paths-to-mutate src/homelab_proxmox_orchestrator --tests-dir tests --runner ".venv/bin/python -m pytest -q -c pytest.ini"`

## Integration tests (lab-backed)

- Integration tests may run in GitHub Actions using the lab environment.
- These tests should be gated so they do not run for every PR unless explicitly required.

## Deprecations

- Deprecated scripts live under `scripts/deprecated/`.
- Nothing (code/CI/IaC/docs) should reference anything under `scripts/deprecated/`.
