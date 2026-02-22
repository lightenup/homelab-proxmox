# Research: Proxmox Token Privilege Separation

**Feature Branch**: `036-token-privilege-separation`
**Date**: 2026-02-22

## R-001: How does the orchestrator read host-path mount definitions?

**Decision**: Parse tfvars directly via inline python3 heredoc (not `terraform output`).

**Rationale**:
- FR-008 explicitly requires reading from `service_mountpoints` tfvars, the single source of truth.
- The existing `_extract_service_mountpoints()` function in `scripts/lifecycle/remove_checks.py` already regex-parses this exact nested HCL structure — reuse the logic.
- The orchestrator (`pve-service-deploy`) already uses inline python3 heredocs for complex parsing (e.g., lines 1428–1458 for ansible inventory extraction from terraform state).
- Tfvars files contain only literal values (no HCL expressions or variable interpolation), making regex parsing safe and reliable.
- Parsing tfvars directly is available at any phase (plan or apply) and requires zero Terraform infrastructure changes (no new outputs needed in per-service roots).

**Alternatives considered**:
1. **`terraform output -json`**: Higher fidelity (Terraform's own parser), but requires adding/maintaining `host_path_mountpoints` output in all 6+ per-service `outputs.tf` files, is unavailable during plan-only runs, and contradicts FR-008's source-of-truth intent.
2. **`terraform console` with expression**: Would parse HCL correctly but adds complexity and requires an initialized Terraform workspace. Not warranted for literal tfvars.
3. **Pure bash/awk parsing**: The nested HCL structure (`map(map(object))`) is too complex for safe awk/sed parsing. Python3 regex is the right tool at this depth.

## R-002: How to filter host-path mounts from Terraform's `mountpoint {}` block?

**Decision**: No Terraform-level filtering needed. Keep existing architecture.

**Rationale**:
- The `enforce_bind_mount_policy()` function in `pve-service-deploy` already validates the plan JSON and **rejects** any plan containing host-path volumes in `mountpoint` blocks.
- The `lifecycle { ignore_changes = [mountpoint] }` directive in the LXC module means Terraform never modifies existing mounts.
- For **new** containers: the plan-stage bind-mount guard will block host-path volumes from reaching `terraform apply`. This is the existing designed behavior (FR-003).
- The per-service `main.tf` files pass `mountpoints = values(lookup(var.service_mountpoints, "service", {}))` to the module. For services with ONLY host-path mounts (e.g., Nextcloud), this will result in mountpoint blocks in the plan that the guard catches. This is **acceptable** — the guard blocks the plan, the operator removes host-path entries from tfvars mountpoints that go to Terraform, and the orchestrator handles them separately.
- **Correction**: On closer inspection, the plan-stage guard only triggers on plan CHANGES (new/modified resources). For existing containers with `lifecycle { ignore_changes }`, the guard never fires. For new containers, the guard would fire. The cleanest approach is to filter at the Terraform local level in per-service `main.tf` so host-path entries never enter the `mountpoint {}` block.

**Revised decision**: Filter at the Terraform local level in per-service `main.tf` files. Use `startswith(v.volume, "/")` to separate storage-backed mounts (pass to module) from host-path mounts (handled by orchestrator). This is defensive and prevents the plan-stage guard from ever blocking a legitimate deploy.

## R-003: pct set bind mount format and reboot behavior

**Decision**: Follow existing patterns exactly. Reboot after applying new mounts.

**Findings**:
- **Format**: `pct set <CTID> -mp<N> "<host_path>,mp=<container_path>[,ro=1]"`
- **Read-write**: `pct set 104 -mp0 "/mnt/nas/homelab_immich,mp=/mnt/immich"`
- **Read-only**: `pct set 104 -mp0 "/mnt/nas/video,mp=/media/video,ro=1"`
- **Config output**: `mp0: /mnt/nas/homelab_immich,mp=/mnt/immich` (no quotes in config)
- **Reboot required**: Yes. The existing script always reboots after applying mounts via `pct reboot`, then waits for SSH. Bind mounts applied via `pct set` require a container restart to take effect.
- **Idempotency**: The existing pattern compares `pct config` output with the desired value string. If they match, skip. Otherwise, apply and reboot.
- **Batch reboots**: If multiple mounts need to be applied, apply ALL mounts first, then reboot ONCE (not per-mount). This minimizes downtime.

## R-004: Mount index selection strategy

**Decision**: Parse `pct config` for existing `mp<N>` lines, find max N, use N+1. If no mounts exist, start at 0.

**Rationale**:
- The existing script hardcodes `mp0` and `mp1` per service. The generic version must be dynamic.
- `pct config <CTID>` outputs lines like `mp0: ...`, `mp1: ...`. Parse with: `grep -oP '^mp\K[0-9]+' | sort -n | tail -1`.
- On Linux (PVE host), `grep -P` is available. On macOS (laptop), fall back to `awk '/^mp[0-9]+:/ { match($0, /^mp([0-9]+)/, a); print a[1] }'` or similar.
- When checking for existing mounts (idempotency), match on the `volume,mp=path` portion of the config line, not the index. This handles the case where a mount was previously applied at a different index.

## R-005: Allowlist enforcement approach

**Decision**: Extend existing `enforce_bind_mount_policy()` pattern. Apply same `/mnt/nas/` prefix check with trailing-slash directory boundary enforcement.

**Rationale**:
- The existing function already does this for the Terraform plan stage. The orchestrator-stage check follows the same logic.
- Prefix matching with trailing slash: `[[ "${volume}" == "/mnt/nas/"* ]]`. This ensures `/mnt/nasty-trick` does NOT match (FR-007).
- The allowlist is kept as a bash array `local -a allowed_prefixes=("/mnt/nas/")` in the script, matching the existing `enforce_bind_mount_policy()` implementation.

## R-006: Step summary format

**Decision**: Markdown table format following existing `render_github_summary.sh` pattern.

**Rationale**:
- The existing `render_github_summary.sh` + Python renderer produces markdown for `$GITHUB_STEP_SUMMARY`.
- The bind mount summary is a simpler, inline addition to the orchestrator output.
- Format:

```markdown
## Bind Mount Summary (Service: nextcloud)

| Host Path | Container Path | Permission | Result |
|-----------|---------------|------------|--------|
| /mnt/nas/homelab_nextcloud | /mnt/nextcloud | rw | applied |

**Container reboot**: stopped → mounts applied → started
**Overall**: success (1 applied, 0 skipped, 0 failed)
```

- In CI: written to `$GITHUB_STEP_SUMMARY` (append).
- On laptop: printed to terminal (same content).

## R-007: Tier label output format

**Decision**: Simple bracketed labels emitted to stdout at phase boundaries.

**Format**:
```
[Tier 1] Creating container via Terraform...
[Tier 2] Applying bind mounts via pct set...
[Tier 2] Applying feature flags via pct set...
```

This is a simple `echo` before each phase block. No structural changes needed.

## R-008: Constitution documentation approach

**Decision**: Add a new "### Token Privilege Tiers" subsection under "## Access Control" in the constitution.

**Rationale**:
- The constitution already has an "Access Control" section covering SSH keys and root usage.
- The three-tier model naturally fits there.
- Keep it concise: a table + 3 invariant rules.

## R-009: Tfvars type extension for `readonly`

**Decision**: Add `readonly = optional(bool)` to the `service_mountpoints` object type in ALL locations.

**Locations** (7 files):
1. `terraform/variables.tf` (root module)
2. `terraform/modules/lxc_service/variables.tf` (LXC module)
3. `terraform/services/jellyfin/variables.tf`
4. `terraform/services/immich/variables.tf`
5. `terraform/services/nextcloud/variables.tf`
6. `terraform/services/homeassistant/variables.tf`
7. `terraform/services/monitoring/variables.tf`
8. `terraform/services/reverse_proxy/variables.tf`

The module variable also needs `readonly` even though storage-backed mounts don't use it, for type consistency across the pipeline.
