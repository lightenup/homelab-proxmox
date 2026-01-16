# Tasks: Mutmut Shared Cache

**Input**: Feature specification from `specs/029-mutmut-shared-cache/spec.md`

## Phase 1: Documentation and paths

- [X] T001 Document the shared cache location and browse workflow for PVE + laptop in specs/029-mutmut-shared-cache/quickstart.md
- [X] T002 Define the shared cache path naming convention (NAS share + directory layout) in specs/029-mutmut-shared-cache/spec.md
- [X] T003 Record developer laptop NFS mount path (`/Volumes/nas/homelab_ci`) and access confirmation

## Phase 2: CI and tooling alignment

- [X] T004 Update nightly mutation workflow to write cache to the per-branch shared location (or a symlinked .mutmut-cache) and fail clearly if the mount is missing
- [X] T005 Ensure mutation cache artifacts are still uploaded for CI debugging
- [X] T006 Validate workflow changes with actionlint and act (or document why not feasible)
	- actionlint succeeded; act dry-run succeeded with Docker running.

## Phase 3: Validation

- [ ] T007 Run a nightly mutation workflow and verify the per-branch shared cache is updated
- [ ] T008 On a developer laptop, mount the share, symlink `.mutmut-cache` to `/Volumes/nas/homelab_ci/mutmut-cache/<branch>`, and validate `mutmut browse` loads results without re-running mutations
