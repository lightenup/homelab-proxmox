#!/bin/bash
# Monitoring Stack Smoke Test
# Purpose: Validate Prometheus, Grafana, and Alertmanager endpoints return 200 OK

set -euo pipefail

# Configuration
MONITORING_IP="${MONITORING_IP:-192.168.1.214}"
PROMETHEUS_PORT="${PROMETHEUS_PORT:-9090}"
GRAFANA_PORT="${GRAFANA_PORT:-3000}"
SNMP_EXPORTER_PORT="${SNMP_EXPORTER_PORT:-9116}"
ALERTMANAGER_PORT="${ALERTMANAGER_PORT:-9093}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test counter
PASSED=0
FAILED=0

# Logging function
log_pass() {
    echo -e "${GREEN}✓${NC} $1"
    ((PASSED++))
}

log_fail() {
    echo -e "${RED}✗${NC} $1"
    ((FAILED++))
}

log_info() {
    echo -e "${YELLOW}ℹ${NC} $1"
}

# HTTP test function
test_endpoint() {
    local name="$1"
    local url="$2"
    local expected_code="${3:-200}"

    log_info "Testing ${name}: ${url}"

    if response=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "${url}" 2>/dev/null); then
        if [ "${response}" -eq "${expected_code}" ]; then
            log_pass "${name} returned ${response}"
        else
            log_fail "${name} returned ${response} (expected ${expected_code})"
        fi
    else
        log_fail "${name} unreachable or timed out"
    fi
}

# JSON endpoint test function
test_json_endpoint() {
    local name="$1"
    local url="$2"
    local jq_filter="$3"

    log_info "Testing ${name}: ${url}"

    if response=$(curl -s --max-time 5 "${url}" 2>/dev/null); then
        if echo "${response}" | jq -e "${jq_filter}" > /dev/null 2>&1; then
            log_pass "${name} JSON valid and ${jq_filter} exists"
        else
            log_fail "${name} JSON invalid or ${jq_filter} missing"
        fi
    else
        log_fail "${name} unreachable or timed out"
    fi
}

echo "========================================="
echo "Monitoring Stack Smoke Test"
echo "========================================="
echo "Target: ${MONITORING_IP}"
echo "Timestamp: $(date)"
echo ""

# Test Prometheus
echo "--- Prometheus Tests ---"
test_endpoint "Prometheus Health" "http://${MONITORING_IP}:${PROMETHEUS_PORT}/-/healthy"
test_endpoint "Prometheus Ready" "http://${MONITORING_IP}:${PROMETHEUS_PORT}/-/ready"
test_json_endpoint "Prometheus Targets" "http://${MONITORING_IP}:${PROMETHEUS_PORT}/api/v1/targets" '.data.activeTargets'
test_json_endpoint "Prometheus Rules" "http://${MONITORING_IP}:${PROMETHEUS_PORT}/api/v1/rules" '.data.groups'
echo ""

# Test Grafana
echo "--- Grafana Tests ---"
test_endpoint "Grafana Health" "http://${MONITORING_IP}:${GRAFANA_PORT}/api/health"
test_json_endpoint "Grafana Datasources" "http://${MONITORING_IP}:${GRAFANA_PORT}/api/datasources" '.[] | select(.type == "prometheus")'
echo ""

# Test SNMP Exporter
echo "--- SNMP Exporter Tests ---"
test_endpoint "SNMP Exporter Health" "http://${MONITORING_IP}:${SNMP_EXPORTER_PORT}/health"
echo ""

# Test Alertmanager
echo "--- Alertmanager Tests ---"
test_endpoint "Alertmanager Health" "http://${MONITORING_IP}:${ALERTMANAGER_PORT}/-/healthy"
test_endpoint "Alertmanager Ready" "http://${MONITORING_IP}:${ALERTMANAGER_PORT}/-/ready"
test_json_endpoint "Alertmanager Status" "http://${MONITORING_IP}:${ALERTMANAGER_PORT}/api/v2/status" '.config'
echo ""

# Test SNMP Target
echo "--- Synology NAS Target Test ---"
log_info "Checking if Prometheus is scraping Synology NAS"
if targets_json=$(curl -s --max-time 5 "http://${MONITORING_IP}:${PROMETHEUS_PORT}/api/v1/targets" 2>/dev/null); then
    if echo "${targets_json}" | jq -e '.data.activeTargets[] | select(.labels.job == "synology-snmp" and .health == "up")' > /dev/null 2>&1; then
        log_pass "Synology NAS target UP in Prometheus"
    else
        log_fail "Synology NAS target DOWN or not found in Prometheus"
    fi
else
    log_fail "Could not query Prometheus targets"
fi
echo ""

# Summary
echo "========================================="
echo "Test Summary"
echo "========================================="
echo -e "${GREEN}Passed: ${PASSED}${NC}"
echo -e "${RED}Failed: ${FAILED}${NC}"
echo ""

if [ ${FAILED} -eq 0 ]; then
    echo -e "${GREEN}✓ All tests passed${NC}"
    exit 0
else
    echo -e "${RED}✗ Some tests failed${NC}"
    exit 1
fi
