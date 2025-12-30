# CLI Contract: pve-lab

## Commands

### `run`
Executes the lab lifecycle.

**Arguments**:
*   `--tier <level>`: Integer. Default `1`.
    *   `1`: Bootstrap only.
    *   `2`: Bootstrap + PVE Install (Tier 2).
*   `--tier2-mode <mode>`: String. Default `min`.
    *   `min`: Install PVE, verify services/API.
    *   `plus`: `min` + Nested VM smoke test.
*   `--keep`: Flag.
    *   If present, do not destroy VM on exit (success or failure).
    *   If absent, destroy VM on exit (unless debug mode implies otherwise).

## Environment Variables
*   `LAB_TEMPLATE_VMID_TIER2`: VM ID for the Debian 13 template. Default: `9002` (example).
