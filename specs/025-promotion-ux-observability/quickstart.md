# Quickstart: Promotion UX Observability

This quickstart describes how the **promotion workflow** is intended to work once the implementation is complete.

## Run the promotion workflow

- Workflow: `.github/workflows/lxc-promote.yml`
- Trigger: `workflow_dispatch`
- Scope: exactly **one service** per run

### Inputs
- `service`: the allowlisted service slug
- `confirm_destructive_lab`: only required if the LAB plan is destructive; must equal `apply-lab-destructive`
- `confirm_destructive_prod`: only required if the PROD plan is destructive; must equal `deploy-prod-destructive`

### Expected sequence
1. Plan (LAB) → summary published in run UI
2. Apply (LAB)
3. Plan (PROD) → summary published in run UI
4. Approval (PROD) after the PROD plan summary exists
5. Apply (PROD) using the exact planfile produced by Plan(PROD)

## What to look for in the run UI

- Job summaries should include:
  - counts: create/update/replace/destroy
  - destructive true/false
  - required confirmation token (if destructive)
  - a truncated list of resource addresses
  - evidence location references (RUN_ID and where the evidence is stored)

Implementation note: the bounded summary is generated from the evidence pack using:

- `scripts/lab/plan_ui_summary.py`
- `scripts/lab/render_github_summary.sh`

- Failures should include:
  - a small number of `::error` annotations with the likely root cause
  - a short “next steps” section (e.g., re-run with token, check evidence pack, fix tfvars)

Implementation note: annotations are emitted via:

- `scripts/lab/render_github_annotations.sh`

## Local validation

### Workflow parsing
If you have Docker + `act` installed:

- List workflows (parsing check):
  - `act -l`

- Dry-run the workflow dispatch (no execution):
  - `act -n -W .github/workflows/lxc-promote.yml workflow_dispatch`

Note: this repo uses `runs-on: [self-hosted]`, so fully executing with `act` may require additional configuration.

## Secrets
Do not commit secrets. When documenting examples, use placeholders like:

- `ANSIBLE_VAULT_PASSWORD=<redacted>`
- `PROXMOX_API_TOKEN_SECRET=<redacted>`
