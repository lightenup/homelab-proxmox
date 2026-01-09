# Implementation Plan: Promotion UX Observability

**Branch**: `025-promotion-ux-observability` | **Date**: 2026-01-09 | **Spec**: [specs/025-promotion-ux-observability/spec.md](spec.md)
**Input**: Feature specification from `specs/025-promotion-ux-observability/spec.md`

## Summary

Refine the existing LAB→PROD promotion workflow to be safer and more usable:

- Production approval happens only after a production plan summary is visible.
- LAB/PROD plans render concise summaries and annotations in the run UI (counts, truncated resource list, destructive status, evidence locations).
- Destructive applies are blocked unless explicit confirmation tokens are supplied.
- Production apply consumes the exact saved planfile produced by production plan (no re-plan drift).

This feature builds on the existing evidence pack system produced by `scripts/lab/pve-service-deploy` and validated via `scripts/lab/ci-verify.sh`.

## Technical Context

**Language/Version**: Bash + GitHub Actions YAML; Python 3.x used for offline parsing/summaries  \
**Primary Dependencies**: Terraform CLI, jq, ssh/scp/rsync, tar, GitHub Actions artifacts  \
**Storage**: Filesystem evidence packs on PVE (`/var/lib/homelab-proxmox/artifacts/service-deploy-runs/`)  \
**Testing**: `act -l` parse check; `scripts/lab/ci-verify.sh` (offline evidence verifier)  \
**Target Platform**: Self-hosted GitHub Actions runner(s) + Proxmox (PVE) host execution  \
**Project Type**: Infra repo (Terraform + Ansible + bash tooling + workflows)  \
**Performance Goals**: Fast operator signal; bounded summaries (avoid huge UI output)  \
**Constraints**: No secrets in logs/artifacts; no Terraform targeting; state stays local on PVE; PROD apply approval-gated  \
**Scale/Scope**: One service per run; small-to-moderate Terraform plans

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Spec-driven workflow**: This plan only creates spec artifacts. Follow-up implementation must be represented in `specs/025-promotion-ux-observability/tasks.md` before code changes land.
- **Secrets policy**: No secrets committed or printed. Workflow output must not echo token secrets; keep stdin/temp-file patterns.
- **Separation of concerns**: Terraform stays responsible for infra; Ansible stays responsible for in-guest config. This feature changes orchestration/reporting only.
- **State management**: Terraform state remains local on PVE; backups remain handled by existing scripts.

**Gate result (pre-design)**: PASS.

## Project Structure

### Documentation (this feature)

```text
specs/025-promotion-ux-observability/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── workflow-promote.schema.json
│   └── plan-ui-summary.schema.json
└── checklists/
   └── requirements.md
```

### Source Code (repository root)

```text
.github/workflows/
├── lxc-promote.yml
├── lxc-deploy-lab.yml
└── proxmox-apply.yml

scripts/lab/
├── pve-service-deploy
├── ci-verify.sh
├── verify_evidence.py
└── lib/
   └── (artifacts/evidence/jsonl helpers)
```

**Structure Decision**: Treat this as a workflow + bash tooling change. Keep implementation in `.github/workflows/` and `scripts/lab/`.

## Phase 0 — Research (complete)

Research outputs:

- [specs/025-promotion-ux-observability/research.md](research.md)

Key decisions:

- Use existing `blast-radius.json` / `plan.json` as the authoritative source for destructive detection and bounded plan summaries.
- Use GitHub job summaries (`$GITHUB_STEP_SUMMARY`) + focused annotations (`::error`/`::warning`/`::notice`) for observability.
- Enforce “apply uses exact planned bytes” by passing a plan RUN_ID/planfile reference from plan→apply and verifying metadata (service/env/hash).

## Phase 1 — Design & Contracts (complete)

Outputs:

- Data model: [specs/025-promotion-ux-observability/data-model.md](data-model.md)
- Contracts: [specs/025-promotion-ux-observability/contracts/](contracts/)
- Quickstart: [specs/025-promotion-ux-observability/quickstart.md](quickstart.md)

Design sketch (for implementation once tasks.md is approved):

1) **Workflow sequencing**
  - Plan (LAB) → Apply (LAB) → Plan (PROD) → Approval (PROD) → Apply (PROD)
  - Ensure the PROD approval job is not reachable until the PROD plan job has succeeded and rendered a plan summary.

2) **Plan summaries + failure surfacing**
  - After each evidence fetch + offline verify, generate bounded Markdown summaries derived from `blast-radius.json` and selected evidence files.
  - On failures, emit a small number of actionable annotations and a short “next steps” section.

3) **Destructive confirmations**
  - Use explicit string tokens (not booleans):
    - LAB: `apply-lab-destructive`
    - PROD: `deploy-prod-destructive`
  - Only required when `blast-radius.json.destructive == true`.

4) **Saved planfile integrity (PROD)**
  - Extend `scripts/lab/pve-service-deploy` to support applying an existing planfile produced earlier (referenced by plan RUN_ID or explicit path).
  - Validate planfile existence and metadata match (service/env/hash) and fail fast with clear guidance if missing.

## Phase 1 — Agent Context Update (pending)

After filling this plan, run:

```bash
.specify/scripts/bash/update-agent-context.sh copilot
```

## Constitution Check (post-design)

- Spec-driven: design artifacts produced under this spec directory.
- Secrets: quickstart/contracts use placeholders only.
- Separation of concerns: unchanged.

**Gate result (post-design)**: PASS.

## Phase 2 — Task Planning (next step)

Create and approve `specs/025-promotion-ux-observability/tasks.md` via `/speckit.tasks`, then implement:

- Workflow refactor (`.github/workflows/lxc-promote.yml`) for ordering + summaries + confirmations.
- `pve-service-deploy` enhancement for apply-from-plan (no re-plan drift).
- Update evidence verification/contracts as needed.

Stop point: this `/speckit.plan` run ends here (before creating tasks.md).

## Complexity Tracking

No constitution violations required for this feature.
