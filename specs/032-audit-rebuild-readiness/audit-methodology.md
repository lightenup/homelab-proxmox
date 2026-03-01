# Audit Methodology & Classification Rubric

**Feature**: 032-audit-rebuild-readiness
**Date**: 2026-02-05

## Purpose

Define a consistent method for inventorying, classifying, and documenting repository components and runtime assets.

## Evidence Sources (required)

- Repository evidence (files, role/playbook wiring, Taskfile entrypoints).
- Runtime inventory (PVE mounts, LXC list, LXC mountpoints, in-guest mount checks).
- Runbooks/operations docs for rebuild procedures.

## Classification Status

| Status | Definition | Minimum Evidence |
| --- | --- | --- |
| in-use | Actively used in current workflows or runtime | Repo reference + runtime confirmation (or CI/task entrypoint) |
| unused | No current references and not used at runtime | Repo scan + runtime confirmation |
| requires-review | Conflicting evidence or unclear ownership | Repo scan + flagged gap |
| dr-maintenance-only | Used only in DR or maintenance windows | Runbook + periodic use evidence |

## Severity Levels (Findings)

| Severity | Description | Example |
| --- | --- | --- |
| low | Cosmetic or documentation-only | Missing doc link |
| medium | Gap with workaround | Role exists but not wired |
| high | Operational risk | Rebuild step missing |
| critical | Blocks rebuild/DR | No restore path for required data |

## Remediation Priority

Prioritize by rebuild/DR criticality, then operational impact, then effort.

| Priority | Meaning |
| --- | --- |
| p1 | Blocks rebuild/DR or data safety |
| p2 | Degrades operations but has workaround |
| p3 | Optimization or cleanup |

## Runtime Inventory Requirements

- PVE host mounts and LXC mountpoints must be captured.
- LXC in-guest mount visibility must be confirmed for shared storage.
- Evidence must include date/time, command output, and host context.

## Output Artifacts

- Inventory (specs/032-audit-rebuild-readiness/inventory.md)
- Findings log (specs/032-audit-rebuild-readiness/findings.md)
- Recommendations (specs/032-audit-rebuild-readiness/recommendations.md)
- Runtime inventory evidence (specs/032-audit-rebuild-readiness/runtime-inventory.md)
- Audit report (specs/032-audit-rebuild-readiness/audit-report.md)
