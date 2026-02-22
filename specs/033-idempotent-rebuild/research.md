# Research: Idempotent Rebuild Orchestrator

**Feature**: 033-idempotent-rebuild
**Date**: 2026-02-05

## Decision 1: Use existing Taskfile + scripts/lab orchestration

**Decision**: Drive rebuild via Taskfile entrypoints and existing `scripts/lab/*` orchestration, with a thin macOS launcher script.

**Rationale**: Reuses established workflows and guardrails, avoids duplicate orchestration logic, and aligns with the constitution’s separation of concerns.

**Evidence**:
- [Taskfile.yml](Taskfile.yml)
- [scripts/lab/pve-service-deploy](scripts/lab/pve-service-deploy)

**Alternatives considered**:
- New standalone rebuild CLI (rejected: reinvents existing flows).

## Decision 2: Plan-only by default with explicit apply

**Decision**: Default to plan-only execution; require explicit apply flag and destructive confirmation string.

**Rationale**: Matches existing safety patterns and supports idempotent, lab-first iteration.

**Evidence**:
- [specs/033-idempotent-rebuild/spec.md](specs/033-idempotent-rebuild/spec.md)

**Alternatives considered**:
- Always apply (rejected: unsafe for incremental lab runs).

## Decision 3: Evidence and state stored locally on laptop

**Decision**: Store evidence under `artifacts/rebuild-runs/<timestamp>` and state at `artifacts/rebuild-runs/<timestamp>/state.json`.

**Rationale**: Avoids CI dependencies and keeps evidence localized to the operator run.

**Evidence**:
- [specs/033-idempotent-rebuild/spec.md](specs/033-idempotent-rebuild/spec.md)
- [specs/032-audit-rebuild-readiness/evidence-index.md](specs/032-audit-rebuild-readiness/evidence-index.md)

**Alternatives considered**:
- Store on PVE host only (rejected: conflicts with macOS-run requirement).

## Decision 4: Use PVE restore runbook as baseline

**Decision**: Rebuild steps must align to the Proxmox restore runbook as canonical baseline.

**Rationale**: Prevents drift from documented restore procedures and ensures consistency with existing DR practices.

**Evidence**:
- [docs/operations/backups-proxmox-config-restore.md](docs/operations/backups-proxmox-config-restore.md)
- [specs/032-audit-rebuild-readiness/rebuild-baseline.md](specs/032-audit-rebuild-readiness/rebuild-baseline.md)

**Alternatives considered**:
- New custom baseline (rejected: duplicates existing runbook).
