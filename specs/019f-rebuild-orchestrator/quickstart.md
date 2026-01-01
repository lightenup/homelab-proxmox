# Quickstart: Rebuild Orchestrator (019f)

## Overview
The Rebuild Orchestrator validates the Proxmox host and templates against a strict baseline before running the full test suite. Use this to ensure a clean and correct environment.

## Usage

### 1. Validate Environment (Dry Run)
Check if the host and templates meet the baseline requirements without making any changes.

```bash
./scripts/lab/pve-lab rebuild --dry-run
```

### 2. Remediate and Run (Apply)
**Note**: Remediation logic is currently a placeholder. This command will run checks and then the suite if checks pass.

```bash
./scripts/lab/pve-lab rebuild --apply
```

### 3. Run with Specific Profile
Specify a custom profile (default is `rebuild-hypervisor-nested-workload`).

```bash
./scripts/lab/pve-lab rebuild --profile rebuild-hypervisor-nested-workload
```

### 4. Verify Implementation (CI)
Run the offline verification suite to ensure the orchestrator logic and fixtures are correct.

```bash
./scripts/lab/ci-verify.sh
```

## Troubleshooting

- **HOST-001 Fail**: Check SSH access to the Proxmox host (`ssh root@<host>`).
- **HOST-002 Fail**: Verify `vmbr99` exists and has the correct IP (`10.99.0.1`).
- **TPL-* Fail**: Ensure templates 9001 and 9002 exist and are configured correctly.
- **Verification Fail**: Check `reports/verify.json` in the evidence pack for detailed error messages.
