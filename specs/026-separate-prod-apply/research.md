# Phase 0 Research: Separate PROD Apply Workflow

This document resolves technical unknowns for Spec 026 and records the key design decisions.

## Decision: Plan reference format

- **Decision**: Use the existing evidence-pack `RUN_ID` as the "plan reference" for PROD applies.
- **Rationale**:
  - Evidence packs are already durable on PVE: `/var/lib/homelab-proxmox/artifacts/service-deploy-runs/<run_id>`.
  - `scripts/lab/pve-service-deploy apply --from-plan-run-id <RUN_ID>` already:
    - validates the plan evidence dir exists,
    - validates `provenance.json` matches expected `environment` + `service`,
    - requires `reports/plan/plan.tfplan`, and
    - records `plan_source_run_id` + `plan_sha256` in apply provenance.
  - Re-using `RUN_ID` avoids inventing a new identifier format.
- **Alternatives considered**:
  - **GitHub Actions artifact ID / URL**: rejected because the authoritative bytes live on PVE and workflows already fetch from PVE.
  - **Plan SHA only**: rejected because apply needs a stable location for the planfile bytes, not just an integrity value.

## Decision: Workflow split (LAB vs PROD)

- **Decision**: Split into two workflows:
  1. **LAB promote**: plan + apply for `lab` only.
  2. **PROD promote**: a single pipeline that runs LAB deploy + full confidence suite + PROD plan + approval + PROD apply from saved plan.
- **Rationale**:
  - Makes operator intent unambiguous (PROD is never "along for the ride").
  - Keeps production approval and production execution in a separately triggered run.
  - Preserves the current safety model and evidence verification.
- **Alternatives considered**:
  - **Single workflow with flags controlling prod**: rejected (still feels like "one run goes to prod").
  - **Single workflow with prod jobs conditional + environments**: rejected because the run UX still contains prod steps and approval gates.

## Decision: Interactive approval mechanism for PROD apply

- **Decision**: Use GitHub Environments approval gating by setting `environment: prod` on an approval job (or the apply job), relying on repository environment protection rules (required reviewers).
- **Rationale**:
  - Native GitHub feature; clear and auditable.
  - No custom token/prompting logic required.
- **Alternatives considered**:
  - **Manual confirmation string input only**: rejected; does not create an interactive pause with reviewers.

## Decision: Fast-fail validation of plan references in PROD promote

- **Decision**: The PROD promote workflow should validate prerequisites before requesting approval:
  - LAB deploy evidence exists and matches the current git SHA
  - confidence suite evidence exists and indicates PASS
  - PROD plan evidence exists and matches the current git SHA
  - saved plan bytes exist for the apply step
- **Rationale**:
  - `pve-service-deploy` already validates on the PVE side, but early validation allows better run UI output without waiting for a remote failure.
  - Reuses bounded excerpt mechanisms (`scripts/lab/render_failure_evidence.sh`) and offline verification (`scripts/lab/ci-verify.sh`).
- **Alternatives considered**:
  - **Rely only on `pve-service-deploy` failures**: rejected; slower feedback and worse UX.

## Decision: Workflow naming

- **Decision**: Use explicit workflow filenames and run names:
  - `.github/workflows/lxc-promote-lab.yml` (LAB only)
  - `.github/workflows/lxc-promote-prod.yml` (PROD pipeline: LAB+confidence+PROD)
- **Rationale**: Avoid ambiguity and avoid implying LAB runs may touch PROD.
- **Alternatives considered**:
  - Keep `.github/workflows/lxc-promote.yml` name while changing behavior: rejected as confusing.

## Decision: Select git SHA for strict provenance checks

- **Decision**: The PROD promotion pipeline accepts an explicit `ref` input (branch/tag/SHA), checks out that ref, and enforces strict SHA alignment against the checked-out commit SHA.
- **Rationale**:
  - Makes “strict same git SHA” deterministic and operator-controlled.
  - Avoids ambiguity around `github.sha` vs. the intended target commit.
- **Alternatives considered**:
  - **Use `github.sha` only**: rejected; can be surprising when dispatching from UI or when workflow file changes.

## Decision: Proceed-to-PROD override when LAB gate fails

- **Decision**:
  - If LAB deploy fails or the confidence suite fails, the pipeline still generates and publishes the PROD plan summary + plan reference.
  - PROD apply remains blocked unless:
    - the GitHub Environment approval is granted, and
    - an explicit override checkbox input is set.
  - The override checkbox applies only to the PROD approval/apply decision; it does not alter LAB execution.
- **Rationale**:
  - Keeps the operator’s review flow intact (you can still inspect a PROD plan) while making “continue despite failed LAB assertions” an explicit opt-in.
- **Alternatives considered**:
  - **Stop early and skip PROD plan**: rejected; reduces ability to inspect blast radius.

## Decision: Destructive confirmation behavior under override

- **Decision**: When the override checkbox is set (i.e., continuing despite failed LAB deploy/suite), destructive confirmation requirements are bypassed.
- **Rationale**: Operator explicitly chooses to proceed despite failed LAB assertions; keeping a second destructive token gate in this mode was rejected.
- **Alternatives considered**:
  - Require destructive confirmations even under override: rejected per operator preference.

## Decision: Confidence suite when LAB deploy fails

- **Decision**: Attempt the confidence suite even if the LAB deploy step fails (best-effort), and surface its outcome in the run summary.
- **Rationale**:
  - Provides additional diagnostic evidence in the same run.
- **Alternatives considered**:
  - Skip suite on LAB deploy failure: rejected.
