# Quickstart: Lab Harness Confidence Suite

**Feature**: `019c-lab-confidence-suite`

## Running Validation Profiles

The `pve-lab` tool now supports named validation profiles.

### Bootstrap (Tier 1)
Validates basic connectivity and Ansible convergence.

```bash
./scripts/lab/pve-lab run --profile bootstrap
```

### Hypervisor Control Plane (Tier 2 Min)
Installs and verifies Proxmox VE on Debian 13.

```bash
./scripts/lab/pve-lab run --profile hypervisor-control-plane
```

### Hypervisor Nested Workload (Tier 2 Plus)
Verifies nested virtualization and runs a mini-service.

```bash
./scripts/lab/pve-lab run --profile hypervisor-nested-workload
```

## Running the Confidence Suite

To run the full suite of tests (Safety + All Profiles):

```bash
./scripts/lab/pve-lab suite
```

## Inspecting Evidence

Evidence Packs are stored in `artifacts/019-lab/<runid>/`.

```bash
ls -F artifacts/019-lab/latest/
# Output: checks.json evidence_manifest.json logs/ config/ ...

cat artifacts/019-lab/latest/checks.json
```
