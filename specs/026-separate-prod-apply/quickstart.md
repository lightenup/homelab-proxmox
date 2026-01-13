# Quickstart (Spec 026)

This quickstart describes the intended operator workflow after the split.

## 1) Promote to LAB (no PROD steps)

- Trigger workflow: **LXC Promote (LAB)**
- Input:
  - `service`: one of the allowlisted services
  - `confirm_destructive_lab`: required only when LAB plan is destructive (`apply-lab-destructive`)

Expected outcomes:
- The run plans + applies to `lab`.
- No production approval gate is requested.
- Evidence packs are produced on PVE and a bounded summary is shown in the job summary.

## 2) Promote to PROD (single pipeline with interactive approval)

- Trigger workflow: **LXC Promote (PROD)**
- Inputs:
  - `ref`: git ref (branch/tag/SHA) to promote; the workflow checks out this ref and enforces strict SHA alignment
  - `service`
  - `allow_override_failed_lab_gate`: optional checkbox; only relevant if LAB deploy or confidence suite fails
  - `confirm_destructive_lab`: required only when LAB plan is destructive (`apply-lab-destructive`)

Expected outcomes:
- The workflow deploys to LAB first.
- The workflow runs the **full confidence suite** (strictly for the same git SHA). If LAB deploy fails, the confidence suite is still attempted best-effort.
- The workflow generates a PROD plan and publishes:
  - LAB evidence pointer(s)
  - confidence suite evidence pointer(s)
  - PROD plan summary + plan reference (`RUN_ID`)
- The workflow pauses at the GitHub Environment approval gate (`environment: prod`).
- Only after approval, the apply runs on PVE using a saved plan reference.
- If LAB deploy or confidence suite failed, the run summary will indicate the failure and PROD apply will only proceed if `allow_override_failed_lab_gate=true`.
- When `allow_override_failed_lab_gate=true`, destructive confirmation requirements are bypassed.
  - `scripts/lab/pve-service-deploy apply --environment prod --service <service> --from-plan-run-id <prod_plan_run_id>`

## Prerequisite: Configure GitHub Environment

- In GitHub repo settings, create/configure Environment `prod` with **required reviewers**.
- This environment name must match the workflow job’s `environment: prod`.

## Workflow parse validation (local)

Use `act` to validate that the workflows parse and the job graph resolves.

List jobs:

```bash
act -l -W .github/workflows/lxc-promote-lab.yml
act -l -W .github/workflows/lxc-promote-prod.yml
```

Dry-run (no execution) with a workflow_dispatch payload:

```bash
cat > /tmp/act-workflow-dispatch.json <<'JSON'
{
  "inputs": {
    "service": "monitoring",
    "ref": "main",
    "allow_override_failed_lab_gate": "false",
    "confirm_destructive_lab": ""
  }
}
JSON

act -n -W .github/workflows/lxc-promote-prod.yml workflow_dispatch \
  -e /tmp/act-workflow-dispatch.json \
  -P self-hosted=catthehacker/ubuntu:act-latest
```
