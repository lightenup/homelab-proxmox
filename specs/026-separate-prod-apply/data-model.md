# Data Model (Spec 026)

This feature does not introduce a new database. The "data model" is defined by the evidence-pack files and the workflow inputs that select and connect runs.

## Entity: Promotion Run

Represents one execution targeting one service and one environment.

**Identifier**: `run_id` (string)

**Core fields** (from evidence pack):
- `run_id` (string, non-empty)
- `profile_id` (string; evidence profile)
- `environment` (enum: `lab` | `prod`)
- `service` (string slug; allowlisted)
- `git_sha` (string)
- `git_branch` (string)
- `git_dirty` (boolean)
- `trigger_ref` / `trigger_ref_name` (string)
- `runner.hostname` / `runner.user` (string)

**Primary locations**:
- Evidence root: `/var/lib/homelab-proxmox/artifacts/service-deploy-runs/<run_id>`
- Key files:
  - `provenance.json`
  - `preflight.txt`
  - `reports/plan/plan.tfplan` (plan bytes)
  - `reports/plan/plan.json`, `reports/plan/plan.txt`
  - `blast-radius.json` (includes `destructive` boolean)

**Validation rules**:
- `run_id` must not contain `/` and must not contain `..` when used as an input (enforced in `scripts/lab/pve-service-deploy`).
- `service` must be in the allowlist (`scripts/lab/service-scope-allowlist.json`).

**State transitions**:
- `planned` → `applied` (for LAB)
- `planned(prod)` → `approved(prod)` → `applied(prod)` (for PROD)

**Spec 026 workflow inputs impacting provenance**:
- PROD promotion uses an explicit `ref` input (branch/tag/SHA) and checks out that ref; strict provenance checks compare evidence to the checked-out SHA.
- PROD promotion supports `allow_override_failed_lab_gate` (boolean). When `true`, PROD apply may proceed even if LAB deploy or confidence suite failed (still gated by `environment: prod`).

## Entity: Plan Reference

A stable pointer to a previously produced plan.

**Identifier**: `plan_run_id` (string) == `run_id` of a successful PROD plan run.

**Required invariants** (enforced by `scripts/lab/pve-service-deploy apply --from-plan-run-id`):
- Evidence directory exists for `plan_run_id`.
- `provenance.json` exists in the plan evidence pack.
- `provenance.json.environment` equals the apply environment.
- `provenance.json.service` equals the apply service.
- `reports/plan/plan.tfplan` exists in the plan evidence pack.

## Entity: Approval Decision

Represents a GitHub Environment approval event.

**Fields**:
- `environment` (must be `prod`)
- `required reviewers` (configured in GitHub; out-of-repo)
- `decision` (approved/denied/timeout)

**Note**: This is enforced by GitHub Actions’ `environment: prod` gate rather than stored in repo state.

## Entity: Confidence Suite Run

Represents an execution of the lab harness full validation suite.

**Identifier**: `suite_run_id` (string)

**Primary locations**:
- Evidence root: `/var/lib/homelab-proxmox/artifacts/<lab-harness-runs>/<suite_run_id>` (as produced by `scripts/lab/pve-lab`)

**Required invariants for PROD promotion**:
- The suite run indicates PASS.
- The suite run’s provenance indicates the same git SHA as the service LAB deploy and the PROD plan/apply pipeline.

**Note (override mode)**:
- The suite may fail; in that case, PROD plan is still generated/published and PROD apply requires `allow_override_failed_lab_gate=true`.
- The suite is attempted best-effort even if LAB deploy fails.
