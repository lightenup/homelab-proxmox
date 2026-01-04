# Data Model: Gated LXC Deploy (Least Privilege)

**Spec**: specs/022-lxc-gated-deploy/spec.md  
**Date**: 2026-01-04

This feature is primarily workflow-driven (CI/CD), so the “data model” is a set of structured inputs and artifacts rather than an application database.

## Entities

### Deployment Target
Represents which environment is being targeted.

- **Fields**:
  - `environment`: `lab` | `prod`
  - `proxmox_host`: hostname (e.g., `pve`)
  - `gating`:
    - `requires_approval`: boolean
    - `requires_confirmation_input`: boolean

### LXC Deployment Request
Desired state for a single service LXC.

- **Fields**:
  - `service`: string (baseline example: `jellyfin`)
  - `hostname`: string
  - `vmid`: integer (optional; if used must be unique)
  - `ip`: string (static)
  - `gateway`: string
  - `bridge`: string
  - `resources`:
    - `cores`: integer
    - `memory_mb`: integer
    - `disk_gb`: integer
  - `storage_pool`: string
  - `template`: string
  - `mountpoints`: list (optional)
  - `gpu_passthrough_enabled`: boolean (default false)

### Plan Artifact
Produced by the plan/preflight stage.

- **Fields**:
  - `intent`: `create` | `update` | `no-op` | `blocked`
  - `diff_summary`: human-readable summary
  - `terraform_plan_exit_code`: integer (expected 0/2; 1 indicates failure)
  - `inputs`: echo of the `LXC Deployment Request` (redacted for secrets)

### Evidence Bundle
Durable, verifiable record of what happened during plan/apply.

- **Fields**:
  - `run_id`: string
  - `started_at`: timestamp
  - `ended_at`: timestamp
  - `environment`: `lab` | `prod`
  - `service`: string
  - `status`: `success` | `failure`
  - `checks`: structured results (machine-readable)
  - `artifacts`: list of files with hashes
  - `provenance`: tool versions and inputs summary

### Verification Result
Offline verification result of an evidence bundle.

- **Fields**:
  - `run_id`: string
  - `verification_status`: `PASS` | `FAIL`
  - `failures`: list of reasons (if any)

## Relationships

- `Deployment Target` 1—* `LXC Deployment Request` (a run targets one env and one or more requests; this feature starts with one request per run).
- `LXC Deployment Request` 1—1 `Plan Artifact` (plan stage produces exactly one plan artifact per request).
- `Deployment Target` 1—* `Evidence Bundle` (each run produces one bundle).
- `Evidence Bundle` 1—1 `Verification Result` (offline verification of that bundle).

## Validation Rules

- `environment` MUST be one of `lab`/`prod`.
- `prod` runs MUST require approval + confirmation input (per spec FR-004).
- `ip`, `gateway`, `bridge` MUST be present (static networking expectation).
- If `vmid` is set, it MUST NOT already be in use by another workload (edge case).
- `gpu_passthrough_enabled` defaults to false and must be explicitly enabled.
