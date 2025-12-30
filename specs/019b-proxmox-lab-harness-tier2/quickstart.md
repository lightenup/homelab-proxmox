# Quickstart: Lab Tier 2

## Prerequisites
1.  **Debian 13 Template**: Ensure a template exists (ID `9002` or set `LAB_TEMPLATE_VMID_TIER2`).
2.  **SSH Access**: Ensure you have SSH access to the Proxmox host (`192.168.1.112`).

## Running Tier 2 (Min)
This installs Proxmox VE 9 on the lab VM and verifies the API.

```bash
./scripts/lab/pve-lab run --tier 2
```

## Debugging
To keep the VM running after the test (for inspection):

```bash
./scripts/lab/pve-lab run --tier 2 --keep
```

Then SSH into the lab VM:
```bash
ssh root@10.99.0.10
```

## Running Tier 2 (Plus)
**Requires Nested Virtualization on Host**.
This creates a nested VM inside the lab VM.

```bash
./scripts/lab/pve-lab run --tier 2 --tier2-mode plus
```
