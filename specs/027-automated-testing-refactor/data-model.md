# Data Model: Automated Testing Refactor

**Feature**: [specs/027-automated-testing-refactor/spec.md](spec.md)
**Date**: 2026-01-13

This describes the conceptual entities and relationships involved in the automation runner and testing strategy.

## Entities

### AutomationRun
Represents a single attempt to run an action for a service and environment.

**Fields**
- `run_id` (string): Unique identifier for the run (stable within a workflow execution)
- `service` (string): Service identifier (e.g., `ntfy`, `immich`)
- `environment` (enum): `lab` | `prod`
- `action` (enum): `plan` | `apply` | `verify`
- `source_ref` (string, optional): Git ref or SHA the run is associated with
- `started_at` (timestamp)
- `finished_at` (timestamp, optional)
- `status` (enum): `queued` | `running` | `succeeded` | `failed` | `canceled`
- `exit_code` (int, optional)
- `summary` (RunSummary)
- `evidence` (list[EvidencePointer])

**State transitions**
- `queued -> running -> succeeded|failed|canceled`

### EvidencePack
Durable record produced by executing plan/apply/verification steps.

**Fields**
- `environment` (enum): `lab` | `prod`
- `service` (string)
- `path` (string): Location pointer (local path or fetched artifact identifier)
- `created_at` (timestamp)
- `phases` (list[EvidencePhase])

### EvidencePhase
A named portion of a run that produces logs and structured outputs.

**Fields**
- `name` (string): e.g., `terraform-plan`, `terraform-apply`, `ansible-apply`, `healthcheck`
- `status` (enum): `succeeded` | `failed` | `skipped`
- `log_paths` (list[string])
- `artifact_paths` (list[string])

### EvidencePointer
A short operator-facing pointer to where evidence can be found.

**Fields**
- `label` (string)
- `location` (string)

### RunSummary
Bounded, human-readable summary derived from evidence packs.

**Fields**
- `title` (string)
- `highlights` (list[string])
- `warnings` (list[string])
- `errors` (list[string])
- `next_steps` (list[string])
- `bounded` (bool)

### ValidationSuite
Automated checks intended to run on each pull request.

**Fields**
- `checks` (list[ValidationCheck])
- `overall_status` (enum): `passed` | `failed`

### DeeperVerificationSuite
Scheduled checks intended to detect subtler regressions.

**Fields**
- `checks` (list[ValidationCheck])
- `overall_status` (enum): `passed` | `failed`
- `artifacts` (list[EvidencePointer])

### ValidationCheck
A single check within a suite.

**Fields**
- `name` (string)
- `status` (enum): `passed` | `failed` | `skipped`
- `details` (string, bounded)

## Relationships

- An `AutomationRun` produces one or more `EvidencePack`s.
- A `RunSummary` is derived from `EvidencePack` content (and must remain bounded).
- `ValidationSuite` and `DeeperVerificationSuite` are collections of `ValidationCheck` and may produce artifacts/evidence pointers.
