# Feature Specification: Mutmut Shared Cache

**Feature Branch**: `029-mutmut-shared-cache`
**Created**: 2026-01-16
**Status**: Draft
**Input**: User description: "Persist mutmut cache on shared NAS storage so PVE and developer laptops can use mutmut browse without rerunning mutations."

## Clarifications

### Session 2026-01-16
- Q: What shared cache layout should be used? → A: Per-branch cache file under the shared mount (e.g., `/mnt/nas/homelab_ci/mutmut-cache/<branch>`).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Shared mutation cache (Priority: P1)

As a maintainer, I want mutation test results to be stored in a shared location, so I can inspect failures and surviving mutants without rerunning the full suite.

**Why this priority**: Mutation runs are expensive; cached results are required for `mutmut results/show/apply/browse` workflows.

**Independent Test**: Run a nightly mutation test, then open the shared cache and run `mutmut results` without re-running mutations.

**Acceptance Scenarios**:

1. **Given** a completed mutation run, **When** the shared cache is opened from a workstation or PVE, **Then** `mutmut results` shows the same mutant statuses without a rerun.
2. **Given** a mutant ID, **When** `mutmut show` or `mutmut apply` is run using the shared cache, **Then** it displays/applies the correct mutation.

---

### User Story 2 - Developer laptop access (Priority: P2)

As a developer, I want my laptop to access the same mutation cache as the PVE host, so I can use `mutmut browse` locally.

**Why this priority**: The browse workflow is most useful on a developer machine with local tooling.

**Independent Test**: Mount the shared storage on a laptop, point the repo cache to it, and open `mutmut browse`.

**Acceptance Scenarios**:

1. **Given** the NAS share is mounted on a laptop, **When** the repo points `.mutmut-cache` at the shared location, **Then** `mutmut browse` opens and shows the latest results.

---

### User Story 3 - CI writes cache predictably (Priority: P3)

As a maintainer, I want CI mutation runs to write their cache to the same shared path consistently, so the cache remains current and usable.

**Why this priority**: The cache must be refreshed by scheduled runs to stay relevant.

**Independent Test**: Trigger the nightly workflow and confirm the shared cache is updated.

**Acceptance Scenarios**:

1. **Given** a nightly mutation run, **When** it finishes, **Then** the shared cache reflects the latest run and is readable from both PVE and a laptop.
2. **Given** multiple branches run mutations, **When** caches are written, **Then** each branch writes to its own cache file under the shared mount.

---

### Edge Cases

- The shared cache path is not mounted when a mutation run starts.
- The shared cache exists but is not writable by the CI user.
- The laptop mount is read-only or disconnected mid-browse.
- Cache contents are stale or partially written.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST store mutation cache outputs in a shared per-branch location accessible by the PVE host and developer laptops.
- **FR-002**: The mutation cache location MUST be documented for operators and developers.
- **FR-003**: The mutation cache MUST be readable by `mutmut results/show/apply/browse` without rerunning mutations.
- **FR-004**: The system MUST handle missing or unwritable cache paths with a clear failure message that includes the expected cache path and a permission/mount hint.
- **FR-005**: The mutation cache MUST NOT contain secrets beyond what is already present in the codebase.

### Key Entities *(include if feature involves data)*

- **Mutation Cache**: The persisted `.mutmut-cache` SQLite file used by `mutmut` for results and metadata.
- **Shared Storage**: A NAS-mounted path accessible by PVE and developer laptops.

### Assumptions & Dependencies

- The NAS share `homelab_ci` already exists.
- The PVE host has the share mounted at `/mnt/nas/homelab_ci` via NFS.
- The mutation cache layout uses per-branch cache files under the shared mount.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A nightly mutation run updates the shared cache successfully on at least 95% of runs.
- **SC-002**: Developers can open `mutmut browse` using the shared cache within 2 minutes of mounting the share.
- **SC-003**: Mutation cache access failures produce an error message that includes the expected cache path and a permission/mount hint.
