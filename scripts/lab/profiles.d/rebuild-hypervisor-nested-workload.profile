# Profile: Rebuild Hypervisor Nested Workload
# Purpose: Validate host baseline, templates, and run full nested workload suite

PROFILE_ID="rebuild-hypervisor-nested-workload"
DISPLAY_NAME="Rebuild Hypervisor Nested Workload"
SAFETY_LEVEL="strict"
EXPECTED_DURATION_MINUTES=15

# Underlying suite profile to run after baseline
SUITE_PROFILE="hypervisor-nested-workload"

# Prerequisites
PREREQUISITES=(
    "Host: Proxmox VE installed"
    "Host: SSH access configured"
    "Host: Bridge vmbr99 configured"
    "Host: Storage local-lvm available"
)

# Expected checks (Baseline + Suite)
EXPECTED_CHECKS=(
    "HOST-001"
    "HOST-002"
    "HOST-003"
    "HOST-004"
    "TPL-001"
    "TPL-002"
    "TPL-003"
    "TPL-004"
    "TPL-005"
    "TPL-006"
)
