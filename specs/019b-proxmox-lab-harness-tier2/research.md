# Research: Lab Harness Tier 2

**Feature**: `019b-proxmox-lab-harness-tier2`
**Date**: 2025-12-30

## 1. Proxmox VE 9 (Trixie) Availability
*   **Question**: Does the Proxmox VE repository for Debian 13 (Trixie) exist?
*   **Finding**: Yes, `http://download.proxmox.com/debian/pve/dists/trixie/` is accessible and contains packages.
*   **Decision**: We can proceed with targeting Debian 13 and the `trixie` distribution in the `sources.list`.

## 2. Debian 13 Cloud Image
*   **Question**: Is there a ready-to-use Debian 13 Cloud Init image?
*   **Finding**: Debian "Trixie" is the current testing distribution. Generic cloud images are typically available for testing.
*   **Decision**: The user/admin must ensure a template with ID `LAB_TEMPLATE_VMID_TIER2` exists and is based on Debian 13. The harness will verify the OS release.

## 3. Nested Virtualization
*   **Question**: How to verify nested virtualization support?
*   **Finding**:
    *   Host: Check `/sys/module/kvm_intel/parameters/nested` (should be `Y` or `1`).
    *   Guest: Check for `/dev/kvm` device.
*   **Decision**: Implement checks in the harness. Tier 2 "Min" does not require it, but "Plus" does.

## 4. Keyring Management
*   **Question**: How to handle Proxmox repository keys securely?
*   **Finding**: Modern Debian uses `/usr/share/keyrings/` or `/etc/apt/keyrings/` instead of `trusted.gpg`.
*   **Decision**: We will download the key to `/usr/share/keyrings/proxmox-release-trixie.gpg` and reference it in the `sources.list` entry with `signed-by=`.
