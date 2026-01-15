# Tooling Sunsetting Policy

This repo is progressively sunsetting ad-hoc shell scripts in favor of a single entry point: `Taskfile.yml` (go-task).

## Goals

- Prefer a discoverable, consistent operator interface (`task ...`).
- Keep changes incremental and test-backed.
- Avoid breaking existing CI/IaC/harness entry points.

## Deprecation policy

- **Deprecation mechanism**: legacy scripts are moved under the repo’s deprecated-scripts directory (under `scripts/`).
- **No deprecated references**: repository code, CI, IaC, and operator docs must not reference deprecated scripts by path.
  - Feature/spec documentation may discuss the deprecation mechanism.

## Shim policy (compatibility)

Shims are allowed only when updating the caller is impractical/cumbersome (typically CI/IaC/core harness callers that must stay path-stable).

- A shim should:
  - Keep the original path stable.
  - Print a clear message describing the replacement (`task ...` and/or Python entrypoint).
  - Forward to the replacement only when safe.
  - Document a **removal condition** (e.g., “remove once workflow X calls `task inventory:update`”).

## Approved for removal

A legacy script is **approved for removal** only when the deletion is explicitly recorded for review (replacement noted), and:

- The replacement behavior exists and is tested.
- All documentation references are updated.
- CI/IaC/harness callers are updated or have a compatibility shim.

If a script is not explicitly approved for removal, treat it as **deprecated-only**.

## Protected paths

The following paths are protected and should not be modified by feature work like shell-tool sunsetting:

- `.specify/` (spec tooling)
- `scripts/lab/` (core harness scripts)
- `mkdir/` (host-installed automation content)

CI blocks PRs that change protected paths unless the PR is explicitly labeled `allow-protected-path-changes`.
