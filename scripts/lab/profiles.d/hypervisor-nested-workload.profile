# Profile: Hypervisor Nested Workload
# Formerly: tier2-plus
# Purpose: Validate PVE + nested virtualization + workload deployment

PROFILE_ID="hypervisor-nested-workload"
DISPLAY_NAME="Hypervisor Nested Workload"
SAFETY_LEVEL="strict"
TIER=2
MODE="plus"
EXPECTED_DURATION_MINUTES=10

# Prerequisites
PREREQUISITES=(
    "Host: Debian 13 base"
    "Host: Nested virtualization enabled (Intel VT-x or AMD-V)"
    "Network: Internet connectivity"
    "Resources: 8GB RAM, 4 vCPU"
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
    "NEST-001"
    "NEST-002"
    "NEST-003"
    "NEST-004"
    "WORK-001"
    "WORK-002"
    "WORK-003"
    "WORK-004"
    "GUARD-001"
    "GUARD-002"
    "GUARD-003"
    "CLEANUP-001"
    "CLEANUP-002"
)

# Execution phases
PHASES=(
    "bootstrap"
    "tier2-install"
    "network-validation"
    "nested-validation"
    "workload-validation"
    "guardrails"
    "cleanup"
)
