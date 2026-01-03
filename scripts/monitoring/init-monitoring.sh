#!/usr/bin/env bash
#
# Purpose: Automate vault creation, encryption, and Terraform/Ansible deployment
# Usage: ./scripts/monitoring/init-monitoring.sh
#

set -euo pipefail

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
VAULT_FILE="${REPO_ROOT}/ansible/group_vars/monitoring/vault.yml"
TERRAFORM_DIR="${REPO_ROOT}/terraform"
ANSIBLE_DIR="${REPO_ROOT}/ansible"

# Helper functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

prompt_secret() {
    local prompt_text="$1"
    local var_name="$2"
    local default_value="${3:-}"
    
    if [[ -n "${default_value}" ]]; then
        read -rsp "${prompt_text} [default: ${default_value}]: " value
        echo
        value="${value:-${default_value}}"
    else
        read -rsp "${prompt_text}: " value
        echo
    fi
    
    eval "${var_name}='${value}'"
}

prompt_value() {
    local prompt_text="$1"
    local var_name="$2"
    local default_value="${3:-}"
    
    if [[ -n "${default_value}" ]]; then
        read -rp "${prompt_text} [${default_value}]: " value
        value="${value:-${default_value}}"
    else
        read -rp "${prompt_text}: " value
    fi
    
    eval "${var_name}='${value}'"
}

check_prerequisites() {
    log_info "Checking prerequisites..."
    
    local missing_tools=()
    
    # Check for required tools
    command -v terraform >/dev/null 2>&1 || missing_tools+=("terraform")
    command -v ansible >/dev/null 2>&1 || missing_tools+=("ansible")
    command -v ansible-vault >/dev/null 2>&1 || missing_tools+=("ansible-vault")
    command -v ssh >/dev/null 2>&1 || missing_tools+=("ssh")
    
    if [[ ${#missing_tools[@]} -gt 0 ]]; then
        log_error "Missing required tools: ${missing_tools[*]}"
        log_error "Install missing tools and try again"
        exit 1
    fi
    
    # Check Proxmox SSH connectivity
    log_info "Checking Proxmox SSH connectivity (192.168.1.112)..."
    if ! ssh -o ConnectTimeout=5 -o BatchMode=yes root@192.168.1.112 'exit' 2>/dev/null; then
        log_warning "Cannot SSH to Proxmox host (192.168.1.112)"
        log_warning "Ensure SSH key is configured or continue with manual verification"
        read -rp "Continue anyway? (y/N): " continue_choice
        [[ "${continue_choice}" != "y" ]] && exit 1
    else
        log_success "Proxmox SSH connectivity verified"
    fi
    
    log_success "Prerequisites check passed"
}

check_snmpv3_configuration() {
    log_info "Checking Synology SNMPv3 configuration (192.168.1.109)..."
    
    if ! command -v snmpwalk >/dev/null 2>&1; then
        log_warning "snmpwalk tool not installed"
        log_info "Install with: brew install net-snmp (macOS) or apt-get install snmp (Linux)"
        return 1
    fi
    
    # We can't test without credentials, so just prompt user
    log_warning "SNMPv3 must be manually configured on Synology NAS"
    log_info "Required configuration:"
    log_info "  1. DSM → Control Panel → Terminal & SNMP → SNMP"
    log_info "  2. Enable SNMP service"
    log_info "  3. Create SNMPv3 user:"
    log_info "     - Username: monitoring"
    log_info "     - Auth Protocol: MD5"
    log_info "     - Auth Password: (min 8 characters)"
    log_info "     - Priv Protocol: AES"
    log_info "     - Priv Password: (min 8 characters)"
    log_info ""
    
    read -rp "Have you configured SNMPv3 on Synology? (y/N): " snmp_configured
    if [[ "${snmp_configured}" != "y" ]]; then
        log_error "Please configure SNMPv3 on Synology before continuing"
        log_info "See: docs/operations/monitoring/synology-snmp-setup.md"
        exit 1
    fi
    
    log_success "SNMPv3 configuration confirmed by operator"
}

collect_secrets() {
    log_info "Collecting secrets for Ansible vault..."
    log_info "(Passwords will not be echoed to screen)"
    echo ""
    
    # Grafana admin password
    prompt_secret "Enter Grafana admin password" GRAFANA_PASSWORD
    
    # SMTP configuration
    echo ""
    log_info "SMTP Configuration (for alert emails)..."
    prompt_value "SMTP server hostname" SMTP_SERVER "smtp.gmail.com"
    prompt_value "SMTP port" SMTP_PORT "587"
    prompt_value "SMTP from address" SMTP_FROM
    prompt_value "SMTP username" SMTP_USERNAME "${SMTP_FROM}"
    prompt_secret "SMTP password (use App Password for Gmail)" SMTP_PASSWORD
    prompt_value "Alert recipient email" ALERT_EMAIL
    
    # SNMPv3 credentials
    echo ""
    log_info "SNMPv3 Configuration (must match Synology settings)..."
    prompt_value "SNMP username" SNMP_USERNAME "monitoring"
    prompt_value "SNMP auth protocol" SNMP_AUTH_PROTOCOL "MD5"
    prompt_secret "SNMP auth password (min 8 chars)" SNMP_AUTH_PASSWORD
    prompt_value "SNMP priv protocol" SNMP_PRIV_PROTOCOL "AES"
    prompt_secret "SNMP priv password (min 8 chars)" SNMP_PRIV_PASSWORD
    
    echo ""
    log_success "All secrets collected"
}

create_vault_file() {
    log_info "Creating Ansible vault file..."
    
    # Ensure directory exists
    mkdir -p "$(dirname "${VAULT_FILE}")"
    
    # Create vault content
    cat > "${VAULT_FILE}" << EOF
---
# Ansible Vault for Monitoring Stack
# Generated: $(date '+%Y-%m-%d %H:%M:%S')
# WARNING: This file contains sensitive credentials - encrypt before committing!

# Grafana Configuration
grafana_admin_password: "${GRAFANA_PASSWORD}"

# SMTP Configuration (for alert emails)
smtp_server: "${SMTP_SERVER}"
smtp_port: ${SMTP_PORT}
smtp_from_address: "${SMTP_FROM}"
smtp_username: "${SMTP_USERNAME}"
smtp_password: "${SMTP_PASSWORD}"

# Alert Recipients
alert_email_recipient: "${ALERT_EMAIL}"

# SNMPv3 Configuration (must match Synology DSM settings)
snmp_username: "${SNMP_USERNAME}"
snmp_auth_protocol: "${SNMP_AUTH_PROTOCOL}"  # MD5 or SHA
snmp_auth_password: "${SNMP_AUTH_PASSWORD}"  # Min 8 characters for MD5
snmp_priv_protocol: "${SNMP_PRIV_PROTOCOL}"  # AES or DES
snmp_priv_password: "${SNMP_PRIV_PASSWORD}"  # Min 8 characters
EOF
    
    chmod 600 "${VAULT_FILE}"
    log_success "Vault file created at: ${VAULT_FILE}"
}

encrypt_vault_file() {
    log_info "Encrypting Ansible vault..."
    
    if ! ansible-vault encrypt "${VAULT_FILE}"; then
        log_error "Failed to encrypt vault file"
        exit 1
    fi
    
    log_success "Vault file encrypted successfully"
    log_warning "IMPORTANT: Remember your vault password - you'll need it for Ansible deployments"
}

verify_snmpv3_connectivity() {
    log_info "Verifying SNMPv3 connectivity to Synology..."
    
    if ! command -v snmpwalk >/dev/null 2>&1; then
        log_warning "snmpwalk not available, skipping connectivity test"
        return 0
    fi
    
    log_info "Testing SNMP connection..."
    if snmpwalk -v3 -l authPriv -u "${SNMP_USERNAME}" \
        -a "${SNMP_AUTH_PROTOCOL}" -A "${SNMP_AUTH_PASSWORD}" \
        -x "${SNMP_PRIV_PROTOCOL}" -X "${SNMP_PRIV_PASSWORD}" \
        192.168.1.109 1.3.6.1.2.1.1.5 2>&1 | grep -q "STRING:"; then
        log_success "SNMPv3 connectivity verified!"
    else
        log_error "SNMPv3 connectivity test failed"
        log_error "Verify credentials match Synology DSM configuration"
        exit 1
    fi
}

provision_terraform() {
    log_info "Provisioning monitoring LXC with Terraform..."
    
    cd "${TERRAFORM_DIR}"
    
    # Initialize Terraform if needed
    if [[ ! -d ".terraform" ]]; then
        log_info "Initializing Terraform..."
        terraform init
    fi
    
    # Show plan
    log_info "Terraform plan:"
    terraform plan -var-file=prod.tfvars
    
    echo ""
    read -rp "Apply Terraform changes? (y/N): " apply_terraform
    if [[ "${apply_terraform}" == "y" ]]; then
        terraform apply -var-file=prod.tfvars -auto-approve
        log_success "Terraform provisioning complete"
    else
        log_warning "Skipping Terraform apply"
        return 1
    fi
}

update_ansible_inventory() {
    log_info "Updating Ansible inventory..."
    
    cd "${REPO_ROOT}"
    
    # Use existing update script if available
    if [[ -x "scripts/update_ansible_inventory.sh" ]]; then
        log_info "Running inventory update script..."
        ./scripts/update_ansible_inventory.sh
    else
        # Manual inventory update
        local inventory_file="${ANSIBLE_DIR}/inventories/generated/hosts.yml"
        
        if ! grep -q "\[monitoring\]" "${inventory_file}" 2>/dev/null; then
            log_info "Adding monitoring group to inventory..."
            cat >> "${inventory_file}" << 'EOF'

[monitoring]
monitoring ansible_host=192.168.1.214 ansible_user=root

[monitoring:vars]
ansible_python_interpreter=/usr/bin/python3
EOF
            log_success "Monitoring added to inventory"
        else
            log_info "Monitoring already in inventory"
        fi
    fi
    
    # Test connectivity
    log_info "Testing Ansible connectivity..."
    cd "${ANSIBLE_DIR}"
    if ansible monitoring -m ping; then
        log_success "Ansible connectivity verified"
    else
        log_warning "Cannot reach monitoring LXC yet (may need a few seconds to boot)"
    fi
}

deploy_ansible() {
    log_info "Deploying monitoring stack with Ansible..."
    
    cd "${ANSIBLE_DIR}"
    
    log_info "Running playbook: playbooks/monitoring.yml"
    log_warning "You will be prompted for the vault password"
    
    if ansible-playbook playbooks/monitoring.yml --ask-vault-pass; then
        log_success "Ansible deployment complete"
    else
        log_error "Ansible deployment failed"
        exit 1
    fi
}

run_smoke_test() {
    log_info "Running smoke tests..."
    
    cd "${REPO_ROOT}"
    
    if [[ -x "scripts/monitoring/smoke-test.sh" ]]; then
        ./scripts/monitoring/smoke-test.sh
    else
        log_warning "Smoke test script not found"
        log_info "Manually verify services at:"
        log_info "  - Grafana: http://192.168.1.214:3000"
        log_info "  - Prometheus: http://192.168.1.214:9090"
        log_info "  - Alertmanager: http://192.168.1.214:9093"
    fi
}

print_summary() {
    echo ""
    echo "=========================================="
    log_success "Monitoring Stack Deployment Complete!"
    echo "=========================================="
    echo ""
    log_info "Service URLs:"
    echo "  • Grafana:       http://192.168.1.214:3000"
    echo "  • Prometheus:    http://192.168.1.214:9090"
    echo "  • Alertmanager:  http://192.168.1.214:9093"
    echo ""
    log_info "Grafana Login:"
    echo "  • Username: admin"
    echo "  • Password: (from vault.yml: grafana_admin_password)"
    echo ""
    log_info "Next Steps:"
    echo "  1. Open Grafana and view 'Synology NAS Health' dashboard"
    echo "  2. Verify Prometheus targets are UP: http://192.168.1.214:9090/targets"
    echo "  3. Test alert delivery: docs/operations/monitoring/runbook-alert-testing.md"
    echo "  4. Configure NFS backup mount (optional)"
    echo ""
    log_info "Documentation:"
    echo "  • Quickstart: docs/operations/monitoring/quickstart.md"
    echo "  • Operations: docs/operations/monitoring/"
    echo ""
}

# Main execution flow
main() {
    echo "=========================================="
    echo "Monitoring Stack Initialization (Feature 017)"
    echo "=========================================="
    echo ""
    
    # Phase 1: Prerequisites
    check_prerequisites
    check_snmpv3_configuration
    
    # Phase 2: Secrets collection
    collect_secrets
    verify_snmpv3_connectivity
    create_vault_file
    encrypt_vault_file
    
    # Phase 3: Infrastructure provisioning
    if provision_terraform; then
        sleep 5  # Wait for LXC to boot
        update_ansible_inventory
    else
        log_warning "Terraform skipped - ensure LXC exists manually"
    fi
    
    # Phase 4: Application deployment
    deploy_ansible
    
    # Phase 5: Verification
    sleep 10  # Wait for containers to start
    run_smoke_test
    
    # Phase 6: Summary
    print_summary
}

# Run main function
main "$@"
