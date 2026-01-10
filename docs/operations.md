# Operations Manual

## Service Promotion Workflows

Preferred day-to-day deployment path is via the bounded GitHub Actions promotion workflows:

- **LAB-only**: `.github/workflows/lxc-promote-lab.yml` (plan+apply to LAB; never touches PROD)
- **PROD pipeline**: `.github/workflows/lxc-promote-prod.yml` (explicit `ref` checkout → LAB apply → best-effort confidence suite → PROD plan → `prod` environment approval → PROD apply from saved plan)

Operational notes:

- The PROD pipeline always attempts to generate a PROD plan (even if LAB deploy or the confidence suite fails).
- PROD apply is blocked until the GitHub Environment approval is granted (`environment: prod`).
- PROD apply uses the saved plan RUN_ID from the plan stage (`--from-plan-run-id <prod_plan_run_id>`).

## Proxmox CI Posture

- CI user only: all SSH/rsync from workflows must target `ci@pve` with non-interactive sudo; root SSH is disallowed.
- Ansible defaults: use `remote_user=ci` with `become_flags=-n`; avoid `remote_user: root` except bootstrap.
- Terraform: use a non-root Proxmox API token (e.g., `ci-terraform@pve!token`) provided via `TF_VAR_proxmox_api_token_id`/`TF_VAR_proxmox_api_token_secret`.
- Runbook and sudoers details live in [docs/operations/proxmox-ci.md](docs/operations/proxmox-ci.md); quickstart in [specs/021-proxmox-ci-hardening/quickstart.md](specs/021-proxmox-ci-hardening/quickstart.md).

## Remote Access (Tailscale)

### Validation (Smoke Test)

To verify that remote access is working correctly:

1.  **Disconnect from WiFi**: Ensure your client device (phone/laptop) is on an external network (e.g., LTE/5G or a coffee shop WiFi).
2.  **Enable Tailscale**: Connect to your tailnet.
3.  **Test Proxmox UI**:
    *   Navigate to `https://192.168.1.112:8006`
    *   **Expected**: Login page loads.
4.  **Test SSH**:
    *   Run `ssh root@192.168.1.112`
    *   **Expected**: Shell prompt appears.
5.  **Test Services**:
    *   Navigate to `http://192.168.1.213:2283` (Immich)
    *   **Expected**: Immich loads.
6.  **Test ACLs (Negative Test)**:
    *   If you have a non-admin device, try to SSH to `192.168.1.112`.
    *   **Expected**: Connection timed out or refused (blocked by ACL).

### Troubleshooting

*   **Host not appearing**: Check `systemctl status tailscaled` on the Proxmox host.
*   **Routes not working**: Ensure you approved the `192.168.1.0/24` route in the Tailscale Admin Console.
*   **Key Expired**: If the auth key expires, generate a new one and update `ansible/group_vars/proxmox_hosts.yml`.

## Proxmox Configuration Backup

- **Main Operations Guide**: [Proxmox Configuration Backup Operations](operations/backups-proxmox-config.md)
- **Restore Guide**: [Proxmox Configuration Restore](operations/backups-proxmox-config-restore.md)

### Email Decommissioning & Kuma Migration

We have migrated from email notifications to Uptime Kuma Push monitoring.

-   **Runbook**: [Proxmox Backup Email Decommissioning](operations/backups-proxmox-config-email-decommission.md)
-   **Current Mode**: `kuma_only` (Email disabled, Kuma active)
-   **Configuration**: `ansible/group_vars/proxmox_hosts/vars.yml`

## Evidence Governance

The lab suite produces evidence packs for every run. These packs are validated against a strict schema and catalog.

### Verification

To verify an evidence pack against the catalog and schema:

```bash
scripts/lab/pve-lab verify-evidence artifacts/019-lab/lab-YYYYMMDD-HHMMSS
```

This checks:
- **Structure**: JSON schema compliance.
- **Catalog**: All checks must be defined in `scripts/lab/checks.d/catalog.json`.
- **Integrity**: All referenced evidence files must exist.

### Comparison (Diff)

To compare two evidence packs (e.g., to check for regressions or drift):

```bash
scripts/lab/pve-lab diff-evidence artifacts/019-lab/run-A artifacts/019-lab/run-B
```

### Catalog Maintenance

The Check Catalog is the Single Source of Truth (SSOT) for all checks.
Location: `scripts/lab/checks.d/catalog.json`

To add a new check:
1.  Add the check definition to `catalog.json`.
2.  Ensure the `check_id` is unique.
3.  Run `scripts/lab/ci-verify.sh` to validate the catalog.

## Rebuild Orchestrator (019f)

The `pve-lab rebuild` command validates the host baseline and templates before running the full nested workload suite. This is the recommended way to validate the lab after a host reinstall or major configuration change.

### Usage

```bash
# Validate only (Dry Run) - Safe by default
./scripts/lab/pve-lab rebuild

# Validate and Remediate Templates (Apply)
./scripts/lab/pve-lab rebuild --apply

# Keep Lab VMs after run (for debugging)
./scripts/lab/pve-lab rebuild --keep

# Run with specific profile
./scripts/lab/pve-lab rebuild --profile rebuild-hypervisor-nested-workload
```

### Workflow

1.  **Baseline Host Checks**: Verifies SSH, Bridge, Storage, and Nested Virtualization.
2.  **Baseline Template Checks**: Verifies Templates (9001, 9002) exist and are correctly configured.
3.  **Remediation** (if `--apply`): Attempts to fix missing or invalid templates.
4.  **Suite Execution**: Runs the `hypervisor-nested-workload` suite.
5.  **Verification**: Auto-verifies the generated evidence pack.

### Validation Phase (020 hardening)

- A post-run **validation** phase fetches the optional validation report (VAL-001) and records it under `reports/validation.json`.
- VAL-001 is catalog-governed (phase `validation`, allow_missing_evidence=true). If the report is unavailable, it is recorded as SKIP with reason and no WARN noise.

### Teardown & Verification (020 hardening)

- Teardown evidence is recorded as `reports/cleanup/teardown-vm-<vmid>.txt` and `reports/cleanup/teardown-lxc-<ctid>.txt`. Checks TEARDOWN-001/002 expect titles `Nested VM destroyed cleanly (no destroy errors)` / `Nested LXC destroyed cleanly (no destroy errors)` and FAIL if retries exhaust.
- Cleanup verification runs after guardrails: CLEANUP-001/002 confirm no lab VMs remain and no locks are present; failures flip the run to FAILED.
- Verification emits `reports/verify.json` plus `summary.verification` (status, report_path, verifier_version, reason on SKIP/FAIL). `--no-verify` sets SKIP with reason; otherwise PASS/FAIL gates exit code.
- Optional validation fetch (VAL-001) remains SKIP if absent; PASS when fetched; never warns. All titles must match catalog to avoid CAT-005 failures.

### Outputs

- Evidence pack: `artifacts/019-lab/<runid>/` containing `summary.json`, `provenance.json`, `checks.json`.
- Baseline evidence: `reports/host/` and `reports/templates/` inside the pack.
- Logs: `logs/events.jsonl` plus `logs/remediation-templates.log` when `--apply` is used.
- Verification report: `reports/verify.json` (skipped only with `--no-verify`).

### Operator Runbook

1. Run `./scripts/lab/pve-lab rebuild --dry-run` after any host rebuild or network change.
2. If template failures occur and it is safe, rerun with `--apply` to remediate templates.
3. Inspect `reports/verify.json` and baseline evidence paths; keep the pack if passing, or rerun after fixes.
4. For offline regression checks, run `./scripts/lab/ci-verify.sh` to validate fixtures.

### Interpreting Failures

*   **Baseline Host Failures**: These are usually blockers. Fix the host configuration (network, storage) manually.
*   **Baseline Template Failures**: Run with `--apply` to attempt auto-remediation.
*   **Suite Failures**: Check the suite logs and evidence for details.
