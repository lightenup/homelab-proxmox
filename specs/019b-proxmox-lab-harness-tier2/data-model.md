# Data Model: Lab VM Tier 2

## VM Specification

| Attribute | Value | Description |
| :--- | :--- | :--- |
| **OS** | Debian 13 (Trixie) | Base OS for Proxmox VE 9. |
| **vCPU** | 2 (Min) | Required for PVE services. |
| **RAM** | 4096 MB (Min) | Required for PVE services + ClamAV/SpamAssassin overhead. |
| **Disk** | 32 GB (Min) | Root filesystem. |
| **Network** | `vmbr99` | Lab network (10.99.0.0/24). |
| **IP** | `10.99.0.10` | Static IP assigned by harness/DHCP. |

## Nested VM (Tier 2 Plus)

| Attribute | Value | Description |
| :--- | :--- | :--- |
| **OS** | CirrOS / Alpine | Minimal OS for smoke testing. |
| **vCPU** | 1 | |
| **RAM** | 512 MB | |
| **Disk** | 1 GB | |
