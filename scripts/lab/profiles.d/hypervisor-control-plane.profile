# Profile: Hypervisor Control Plane
# Formerly: tier2-min
# Purpose: Validate PVE installation and API verification

PROFILE_ID="hypervisor-control-plane"
DISPLAY_NAME="Hypervisor Control Plane"
SAFETY_LEVEL="standard"
TIER=2
MODE="min"
EXPECTED_DURATION_MINUTES=5

# Prerequisites
PREREQUISITES=(
    "Host: Debian 13 base"
    "Network: Internet connectivity"
    "Resources: 4GB RAM, 2 vCPU"
)

# Expected checks (in execution order)
EXPECTED_CHECKS=(
    "ENV-001"
    "ENV-002"
    "PVE-001"
    "PVE-002"
    "PVE-003"
    "PVE-004"
    "PVE-005"
    "NET-001"
    "NET-002"
    "NET-003"
    "NET-004"
)

# Execution phases
PHASES=(
    "bootstrap"
    "tier2-install"
    "network-validation"
)
