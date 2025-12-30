# Research: Service Lifecycle & Healthcheck Enhancements

**Feature**: `018d-service-lifecycle`
**Date**: 2025-12-30

## 1. Schema Validation & Migration

**Current State**:
- `healthcheck.py` reads flat keys: `healthcheck_path`, `healthcheck_port`, `healthcheck_scheme`.
- No validation of extra keys.

**Decision**:
- Implement a `validate_schema(host_vars)` function.
- Define `ALLOWED_KEYS` constant.
- Define `REQUIRED_KEYS` constant.
- Update `perform_check` to use the new `healthcheck_url` object structure:
  ```json
  "healthcheck_url": {
    "scheme": "http",
    "port": 8080,
    "path": "/api/health"
  }
  ```
- **Migration Strategy**: Update all existing `host_vars` files to the new schema as part of this feature.

## 2. Drift Detection (`--check-drift`)

**Requirement**: Separate command, strict validation, zombie detection.

**Approach**:
- Add `--check-drift` flag.
- **Schema Check**: Iterate all hosts in `services` group. Report WARN/FAIL for missing required keys or unknown extra keys.
- **Zombie Check**:
  - "Zombie" = In Inventory but Infrastructure missing.
  - Check 1: Does `ansible_host` exist?
  - Check 2: Is host reachable? (Simple TCP connect to SSH port 22 or ICMP ping).
  - If unreachable -> Report `GAP` (Zombie).

## 3. Non-HTTP Services (`profile: none`)

**Requirement**: Support background workers via command verification.

**Approach**:
- If `healthcheck_profile == "none"`:
  - Require `healthcheck_verification_command`.
  - Execute via Ansible Ad-Hoc command:
    ```python
    subprocess.run(["ansible", hostname, "-m", "shell", "-a", cmd])
    ```
  - Return `PASS` if exit code 0, `FAIL` otherwise.

## 4. GAP vs FAIL

**Requirement**: Distinguish "Service Down" vs "Host Unreachable".

**Approach**:
- In `perform_check` (standard run):
  - `URLError` with "Connection Refused" -> `FAIL` (Service down).
  - `URLError` with "No route to host" or "Host down" -> `GAP` (Infrastructure issue).
  - This might be hard to distinguish reliably in Python's `urllib`.
  - **Alternative**: Rely on `--check-drift` for the "Host Unreachable" signal. Keep standard healthcheck as `FAIL` for any connection issue, but maybe add a "Hint" in the details if it looks like a network issue.
  - **Refined Decision**: The spec says "Healthcheck runner MUST distinguish...".
  - We can try a socket connect to the IP first. If that fails (timeout/unreachable), it's a GAP. If it connects but HTTP fails, it's a FAIL.

## 5. Implementation Plan Updates

- **Phase 1**: Define `data-model.md` with the strict schema.
- **Phase 2**:
  - Refactor `healthcheck.py` to support new schema and `healthcheck_url` object.
  - Implement `validate_schema` and `--check-drift`.
  - Implement `profile: none` logic.
  - Update existing inventory files.
  - Create helper scripts.
