# Contract: Teardown Evidence (TEARDOWN-001/002)

## Purpose
Defines the evidence format for deterministic teardown of nested VM/LXC resources, consumed by checks TEARDOWN-001 (VM) and TEARDOWN-002 (LXC).

## Evidence Files
- VM: `reports/cleanup/teardown-vm-<vmid>.txt`
- LXC: `reports/cleanup/teardown-lxc-<ctid>.txt`

## Required Content
- Timestamped command executions in order (stop, wait, destroy; retries included)
- Exit codes for each command
- stdout/stderr for each command
- Final status (PASS/FAIL) noted in file footer

## Acceptance Rules
- PASS if destroy succeeds within bounded retries and no residual running state
- FAIL if retries exhausted or final destroy non-zero
- Evidence path must be referenced in checks.json entries for TEARDOWN-001/002 (phase=cleanup, owner=harness, severity=high)
