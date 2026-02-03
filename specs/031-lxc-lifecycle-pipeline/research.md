# Phase 0 Research: LXC Lifecycle Workflow Consolidation

## Decision 1: Data location removal requires explicit confirmation

- **Decision**: Delete service data locations (NAS mounts, bind mounts, directories) only after explicit confirmation, optionally after backup.
- **Rationale**: Prevents accidental data loss while still meeting full cleanup requirements.
- **Alternatives considered**:
  - Always delete automatically (rejected: too destructive).
  - Never delete automatically (rejected: leaves drift/cleanup incomplete).
  - Archive for retention window (rejected: more complex than required).

## Decision 2: Destructive confirmation without GitHub Environments

- **Decision**: Use a protected branch label or tag to approve destructive actions.
- **Rationale**: Works on standard GitHub plans without environment approvals.
- **Alternatives considered**:
  - GitHub Environment approvals (rejected: paid feature).
  - Manual input flag in workflow (rejected: not enforceable against tampering).

## Decision 3: Approval scope for destructive confirmation

- **Decision**: Maintainers can set the destructive label/tag and must be definable without paid GitHub features.
- **Rationale**: Maintainers can be managed with repository roles or CODEOWNERS without requiring paid GitHub plans.
- **Alternatives considered**:
  - Admin-only approvals (rejected: too restrictive).
  - Any collaborator approvals (rejected: too permissive).

## Decision 4: Failure handling for removal verification

- **Decision**: Treat removal as failed until all verification steps pass; require retry.
- **Rationale**: Prevents drift and ensures removal is only complete when inventory/healthchecks are clean.
- **Alternatives considered**:
  - Partial success with follow-up task (rejected: increases drift risk).
  - Success on Terraform apply only (rejected: leaves orphaned references).

## Decision 5: Unified pipeline behavior

- **Decision**: A single workflow runs plan and apply for add/change/delete, and apply must consume the same plan with evidence capture.
- **Rationale**: Consistent execution path and repeatable evidence for auditing.
- **Alternatives considered**:
  - Separate workflows per action (rejected: inconsistent guards and evidence).
