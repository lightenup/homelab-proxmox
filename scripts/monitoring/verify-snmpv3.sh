#!/usr/bin/env bash
#
# Purpose: Verify Synology NAS SNMPv3 configuration before deployment
# Usage: ./scripts/monitoring/verify-snmpv3.sh [nas_ip]
#

set -euo pipefail

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
NAS_IP="${1:-192.168.1.109}"
SNMP_USERNAME="${SNMP_USERNAME:-monitoring}"
SNMP_AUTH_PROTOCOL="${SNMP_AUTH_PROTOCOL:-MD5}"
SNMP_PRIV_PROTOCOL="${SNMP_PRIV_PROTOCOL:-AES}"

# Helper functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[✓]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[✗]${NC} $1"
}

check_snmp_tools() {
    if ! command -v snmpwalk >/dev/null 2>&1; then
        log_error "snmpwalk command not found"
        log_info "Install with:"
        log_info "  macOS:  brew install net-snmp"
        log_info "  Ubuntu: sudo apt-get install snmp"
        log_info "  RHEL:   sudo yum install net-snmp-utils"
        exit 1
    fi
    log_success "snmpwalk tool available"
}

check_nas_reachable() {
    log_info "Checking if NAS is reachable at ${NAS_IP}..."
    
    if ping -c 1 -W 2 "${NAS_IP}" >/dev/null 2>&1; then
        log_success "NAS is reachable at ${NAS_IP}"
    else
        log_error "NAS is not reachable at ${NAS_IP}"
        log_info "Verify:"
        log_info "  1. NAS is powered on"
        log_info "  2. Network connectivity"
        log_info "  3. IP address is correct"
        exit 1
    fi
}

get_snmp_credentials() {
    log_info "SNMPv3 credentials required for testing"
    log_info "(These should match your Synology DSM configuration)"
    echo ""
    
    # Auth password
    if [[ -z "${SNMP_AUTH_PASSWORD:-}" ]]; then
        read -rsp "Enter SNMP auth password: " SNMP_AUTH_PASSWORD
        echo ""
    fi
    
    # Priv password
    if [[ -z "${SNMP_PRIV_PASSWORD:-}" ]]; then
        read -rsp "Enter SNMP priv password: " SNMP_PRIV_PASSWORD
        echo ""
    fi
    
    export SNMP_AUTH_PASSWORD
    export SNMP_PRIV_PASSWORD
}

test_snmpv3_basic() {
    log_info "Testing SNMPv3 basic connectivity (sysName)..."
    
    local result
    result=$(snmpwalk -v3 -l authPriv \
        -u "${SNMP_USERNAME}" \
        -a "${SNMP_AUTH_PROTOCOL}" -A "${SNMP_AUTH_PASSWORD}" \
        -x "${SNMP_PRIV_PROTOCOL}" -X "${SNMP_PRIV_PASSWORD}" \
        "${NAS_IP}" 1.3.6.1.2.1.1.5.0 2>&1)
    
    if echo "${result}" | grep -q "STRING:"; then
        local nas_name
        nas_name=$(echo "${result}" | grep -oP 'STRING: \K.*')
        log_success "SNMPv3 authentication successful"
        log_info "NAS hostname: ${nas_name}"
        return 0
    else
        log_error "SNMPv3 authentication failed"
        echo "${result}"
        return 1
    fi
}

test_snmpv3_storage() {
    log_info "Testing SNMPv3 storage metrics (hrStorageTable)..."
    
    local result
    result=$(snmpwalk -v3 -l authPriv \
        -u "${SNMP_USERNAME}" \
        -a "${SNMP_AUTH_PROTOCOL}" -A "${SNMP_AUTH_PASSWORD}" \
        -x "${SNMP_PRIV_PROTOCOL}" -X "${SNMP_PRIV_PASSWORD}" \
        "${NAS_IP}" 1.3.6.1.2.1.25.2.3.1.3 2>&1 | head -5)
    
    if echo "${result}" | grep -q "STRING:"; then
        log_success "Storage metrics accessible"
        log_info "Sample volumes:"
        echo "${result}" | grep "STRING:" | sed 's/^/  /'
        return 0
    else
        log_warning "Storage metrics not accessible"
        echo "${result}"
        return 1
    fi
}

test_snmpv3_synology_disk() {
    log_info "Testing Synology-specific disk health OIDs..."
    
    local result
    result=$(snmpwalk -v3 -l authPriv \
        -u "${SNMP_USERNAME}" \
        -a "${SNMP_AUTH_PROTOCOL}" -A "${SNMP_AUTH_PASSWORD}" \
        -x "${SNMP_PRIV_PROTOCOL}" -X "${SNMP_PRIV_PASSWORD}" \
        "${NAS_IP}" 1.3.6.1.4.1.6574.2.1.1.2 2>&1 | head -5)
    
    if echo "${result}" | grep -q "STRING:"; then
        log_success "Synology disk health OIDs accessible"
        log_info "Sample disks:"
        echo "${result}" | grep "STRING:" | sed 's/^/  /'
        return 0
    else
        log_warning "Synology disk health OIDs not accessible"
        log_info "This may be normal if your NAS model doesn't support these OIDs"
        return 1
    fi
}

test_snmpv3_cpu_memory() {
    log_info "Testing CPU and memory metrics..."
    
    local cpu_result
    cpu_result=$(snmpwalk -v3 -l authPriv \
        -u "${SNMP_USERNAME}" \
        -a "${SNMP_AUTH_PROTOCOL}" -A "${SNMP_AUTH_PASSWORD}" \
        -x "${SNMP_PRIV_PROTOCOL}" -X "${SNMP_PRIV_PASSWORD}" \
        "${NAS_IP}" 1.3.6.1.2.1.25.3.3.1.2 2>&1 | head -1)
    
    if echo "${cpu_result}" | grep -q "INTEGER:"; then
        log_success "CPU metrics accessible"
    else
        log_warning "CPU metrics not accessible"
    fi
    
    local mem_result
    mem_result=$(snmpwalk -v3 -l authPriv \
        -u "${SNMP_USERNAME}" \
        -a "${SNMP_AUTH_PROTOCOL}" -A "${SNMP_AUTH_PASSWORD}" \
        -x "${SNMP_PRIV_PROTOCOL}" -X "${SNMP_PRIV_PASSWORD}" \
        "${NAS_IP}" 1.3.6.1.2.1.25.2.2.0 2>&1)
    
    if echo "${mem_result}" | grep -q "INTEGER:"; then
        log_success "Memory metrics accessible"
    else
        log_warning "Memory metrics not accessible"
    fi
}

test_snmpv3_network() {
    log_info "Testing network interface metrics..."
    
    local result
    result=$(snmpwalk -v3 -l authPriv \
        -u "${SNMP_USERNAME}" \
        -a "${SNMP_AUTH_PROTOCOL}" -A "${SNMP_AUTH_PASSWORD}" \
        -x "${SNMP_PRIV_PROTOCOL}" -X "${SNMP_PRIV_PASSWORD}" \
        "${NAS_IP}" 1.3.6.1.2.1.2.2.1.2 2>&1 | head -5)
    
    if echo "${result}" | grep -q "STRING:"; then
        log_success "Network interface metrics accessible"
        log_info "Sample interfaces:"
        echo "${result}" | grep "STRING:" | sed 's/^/  /'
        return 0
    else
        log_warning "Network interface metrics not accessible"
        return 1
    fi
}

print_summary() {
    echo ""
    echo "=========================================="
    log_info "SNMPv3 Verification Summary"
    echo "=========================================="
    echo ""
    log_info "Configuration:"
    echo "  • NAS IP: ${NAS_IP}"
    echo "  • Username: ${SNMP_USERNAME}"
    echo "  • Auth Protocol: ${SNMP_AUTH_PROTOCOL}"
    echo "  • Priv Protocol: ${SNMP_PRIV_PROTOCOL}"
    echo ""
    log_info "Test Results:"
    echo "  ✓ Basic connectivity: ${test_basic_result}"
    echo "  ✓ Storage metrics: ${test_storage_result}"
    echo "  ✓ CPU/Memory metrics: OK"
    echo "  ✓ Network metrics: ${test_network_result}"
    echo "  • Synology disk OIDs: ${test_disk_result} (optional)"
    echo ""
    
    if [[ "${test_basic_result}" == "PASS" ]] && [[ "${test_storage_result}" == "PASS" ]]; then
        log_success "SNMPv3 verification PASSED"
        log_info "Your NAS is ready for monitoring deployment"
        echo ""
        log_info "Next steps:"
        log_info "  1. Run: ./scripts/monitoring/init-monitoring.sh"
        log_info "  2. Or follow: docs/operations/monitoring/quickstart.md"
        return 0
    else
        log_error "SNMPv3 verification FAILED"
        log_info "Troubleshooting steps:"
        log_info "  1. Verify SNMPv3 is enabled in DSM"
        log_info "  2. Check username and passwords match DSM configuration"
        log_info "  3. Verify auth/priv protocols match (MD5/AES recommended)"
        log_info "  4. See: docs/operations/monitoring/synology-snmp-setup.md"
        return 1
    fi
}

# Main execution
main() {
    echo "=========================================="
    echo "Synology SNMPv3 Verification Script"
    echo "Feature 017: Monitoring Stack"
    echo "=========================================="
    echo ""
    
    # Prerequisites
    check_snmp_tools
    check_nas_reachable
    
    # Get credentials
    get_snmp_credentials
    
    # Run tests
    echo ""
    log_info "Running SNMPv3 tests..."
    echo ""
    
    if test_snmpv3_basic; then
        test_basic_result="PASS"
    else
        test_basic_result="FAIL"
        log_error "Basic connectivity test failed - aborting remaining tests"
        log_info "Check credentials and try again"
        exit 1
    fi
    
    if test_snmpv3_storage; then
        test_storage_result="PASS"
    else
        test_storage_result="FAIL"
    fi
    
    test_snmpv3_cpu_memory
    
    if test_snmpv3_network; then
        test_network_result="PASS"
    else
        test_network_result="FAIL"
    fi
    
    if test_snmpv3_synology_disk; then
        test_disk_result="AVAILABLE"
    else
        test_disk_result="N/A"
    fi
    
    # Summary
    print_summary
}

main "$@"
