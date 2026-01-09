# Data Model: Promotion UX Observability

This spec does not introduce a new database. The “data model” is expressed as **files** inside durable evidence packs and **workflow inputs/outputs**.

## Entities

### Run
Represents a single controller invocation for a specific environment + service stage.

**Fields**
- `run_id` (string): Unique identifier (currently `<env>-<service>-<sha8>-YYYYMMDD-HHMMSS`).
- `profile_id` (string): Evidence profile (currently `service-deploy`).
- `contract_version` (string): Evidence contract version.
- `environment` (enum): `lab` | `prod`.
- `service` (string): Allowlisted service slug.
- `git_sha` (string): Short SHA used in provenance.
- `trigger_ref` / `trigger_ref_name` (string): GitHub ref context when available.

**Relationships**
- A Run produces exactly one Evidence Pack at `ARTIFACT_ROOT/ARTIFACT_RUNS_DIR/<run_id>`.

---

### Evidence Pack
Durable audit bundle written on PVE and later fetched to the runner.

**Key paths (existing)**
- `preflight.txt`
- `summary.json`
- `provenance.json`
- `checks.json`
- `evidence_manifest.json`
- `blast-radius.json`
- `reports/plan/plan.tfplan` (binary)
- `reports/plan/plan.json` (terraform show -json)
- `reports/plan/plan.txt`

**Validation**
- Must pass offline verification via `scripts/lab/ci-verify.sh`.

---

### Plan Summary (UI Summary)
A bounded representation of planned change impact shown in the GitHub run UI.

**Fields**
- `counts`: create/update/replace/destroy.
- `destructive` (boolean): true if any replace or destroy.
- `resources`: truncated list of affected resource addresses + action class.
- `confirmation_token_required` (string | null):
  - `apply-lab-destructive` when env=lab and destructive=true
  - `deploy-prod-destructive` when env=prod and destructive=true

**Source of truth**
- Derived from `blast-radius.json` and/or `reports/plan/plan.json`.

---

### Execution Plan Artifact (Saved Planfile)
The exact plan bytes that must be applied in PROD.

**Fields**
- `path` (string): `reports/plan/plan.tfplan` within the plan-stage evidence pack.
- `sha256` (string): Optional integrity signal for “apply uses exact bytes”.

**Invariants**
- PROD apply must reference a specific plan RUN_ID and use that planfile without re-planning.

---

### Destructive Confirmation Token
Operator-provided input required only when destructive changes are detected.

**Values (per spec)**
- LAB: `apply-lab-destructive`
- PROD: `deploy-prod-destructive`

**Validation rule**
- Tokens are only required when `destructive == true`.
- When required, the token must match exactly.
