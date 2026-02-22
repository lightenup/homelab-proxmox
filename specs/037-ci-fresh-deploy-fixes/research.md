# Research: CI Fresh-Deploy Pipeline Fixes

**Date**: 2026-02-22 | **Branch**: `037-ci-fresh-deploy-fixes`

## R-001: SSH Key Injection via `pct exec`

**Decision**: Use `sudo pct exec <ctid> -- bash -c '...'` to inject the deploy key post-create.

**Rationale**:
- `pct exec` delegates to `lxc-attach`, entering the container's namespaces directly.
- Multi-step commands require `bash -c "..."` because `pct exec` does not invoke a shell by default.
- The idempotent pattern is: `grep -qF "<key>" /root/.ssh/authorized_keys || echo "<key>" >> /root/.ssh/authorized_keys`
  - `-qF` treats the key as a fixed string (SSH keys contain regex metacharacters like `+`, `/`, `=`).
  - `touch authorized_keys` before `grep` handles the case where the file doesn't exist yet.
- `pct exec` **requires a running container** (source: Proxmox `pct.pm` — `die "container '$vmid' not running!"` guard).
- Append (`>>`) is atomic for writes under `PIPE_BUF` (4096 bytes); SSH keys are ~100-400 bytes. Concurrent appends are safe.

**Alternatives considered**:
- **TF_VAR override**: Rejected — `.tfvars` `-var-file` takes precedence over `TF_VAR_*` env vars.
- **pct push**: Also requires running container, more complex, no idempotency.
- **Modifying tfvars**: Out of scope per spec — operator key stays in tfvars.

**Source**: Proxmox source (`PVE::CLI::pct.pm`), project codebase (DNS check at line 1725 already uses this pattern).

## R-002: Network Reachability Check

**Decision**: Use `ping -c 1 -W 5 <ip>` as a binary pass/fail gate, with `pct exec` diagnostic capture on failure.

**Rationale**:
- ICMP ping verifies L3 reachability (IP, routing, interface up) — exactly what we need.
- `ping` is universally available on Proxmox. `nc`/`nmap` may not be (evidence.sh already checks `command -v nc`).
- The SSH wait loop already handles sshd startup (L4); this check only needs to catch L3 issues.
- 5-second timeout is generous for LAN (spec D-009: not configurable, binary check).
- On failure, capture three diagnostics via `pct exec` and host-side `pct config`:
  1. `ip addr show eth0` — diagnoses stale CTID, interface DOWN, wrong IP
  2. `ip route` — diagnoses routing gaps, missing gateway
  3. `pct config <ctid> | grep net` — cross-checks host-side config against actual state

**Alternatives considered**:
- **TCP port probe (nc)**: Overkill — conflates L3 and L4 checks; SSH wait loop covers L4.
- **Multiple pings with longer timeout**: Unnecessary — single ping with 5s timeout is sufficient for LAN.

**Source**: Existing project patterns (verify-snmpv3.sh, evidence.sh), spec decisions D-003, D-004, D-009.

## R-003: SSH Wait Timeout Reduction

**Decision**: Reduce default from 300s to 120s; keep `SSH_WAIT_SECONDS` env var override.

**Rationale**:
- With the network reachability pre-check catching connectivity issues, the SSH wait only covers sshd startup.
- Debian LXC sshd starts in <10s typically; 120s is very generous.
- The `SSH_WAIT_SECONDS` env var already exists (line 1627) — just change the default.
- Spec D-005 explicitly chose 120 seconds.

**Alternatives considered**:
- **60 seconds**: Too aggressive — some services have heavier startup (package install during bootstrap).
- **Keep 300s**: Wasteful now that network issues are caught early.

## R-004: Evidence Artifact Pattern

**Decision**: Follow existing Tier 2 evidence pattern (lxc-features.txt, lxc-mountpoints.txt).

**Rationale**:
- Deploy key injection evidence: `reports/apply/lxc-deploy-key.txt` (key injected/skipped, CTID, fingerprint).
- Network check evidence: `reports/apply/network-check.txt` (ping status, diagnostics on failure).
- Consistent with existing patterns:
  - `reports/apply/lxc-features.txt` — feature flags evidence
  - `reports/apply/lxc-mountpoints.txt` — bind mount evidence
  - `reports/apply/dns-check.txt` — DNS check evidence

**Source**: pve-service-deploy lines 1767-1810 (features), 2207-2320 (mountpoints).

## R-005: Container Running State Guard

**Decision**: Check container status via `sudo pct status <ctid>` before `pct exec` operations.

**Rationale**:
- `pct exec` fails with exit 255 if container is not running.
- Proxmox LXC module sets `start = true`, so containers auto-start after creation.
- However, race conditions or Terraform errors could leave a container in stopped state.
- The guard provides a clear error message rather than a cryptic `pct exec` failure.

**Source**: Proxmox source (`check_running()` guard), spec FR-015, assumption A-005.

## Open Questions

None — all unknowns resolved.
