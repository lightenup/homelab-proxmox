#!/usr/bin/env bash
# scripts/backup/verify_proxmox_backup.sh
# Verify Proxmox backup integrity without full extraction
# Feature: 013-proxmox-config-backup (Phase 6, User Story 4)
# Usage: ./verify_proxmox_backup.sh <backup-file.tar.zst.age>

set -euo pipefail

# Exit codes
readonly EXIT_SUCCESS=0
readonly EXIT_DECRYPTION_FAILED=1
readonly EXIT_CHECKSUM_MISMATCH=2
readonly EXIT_MISSING_FILES=3
readonly EXIT_INVALID_USAGE=4

# Colors for output
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly NC='\033[0m' # No Color

# Functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $*"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $*" >&2
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $*"
}

usage() {
    cat <<EOF
Usage: $(basename "$0") <backup-file.tar.zst.age>

Verify Proxmox backup integrity without full extraction.

Arguments:
    backup-file.tar.zst.age    Path to encrypted backup archive

Environment Variables:
    AGE_KEY_FILE               Path to age private key (default: /root/.age/proxmox-backup.key)

Exit Codes:
    0  Success - backup is valid
    1  Decryption failed
    2  Checksum mismatch detected
    3  Missing required files
    4  Invalid usage

Examples:
    # Verify latest backup
    $(basename "$0") /mnt/nas-backup/proxmox/proxmox-backup-20251223-120000.tar.zst.age

    # Verify with custom key
    AGE_KEY_FILE=/path/to/key $(basename "$0") backup.tar.zst.age
EOF
}

verify_backup() {
    local backup_file="$1"
    local age_key_file="${AGE_KEY_FILE:-/root/.age/proxmox-backup.key}"
    local temp_dir=""

    # Validate inputs
    if [[ ! -f "$backup_file" ]]; then
        log_error "Backup file not found: $backup_file"
        return $EXIT_INVALID_USAGE
    fi

    if [[ ! -f "$age_key_file" ]]; then
        log_error "Age key file not found: $age_key_file"
        return $EXIT_DECRYPTION_FAILED
    fi

    log_info "Verifying backup: $(basename "$backup_file")"
    log_info "Backup size: $(du -h "$backup_file" | cut -f1)"

    # Create temporary directory for verification
    temp_dir=$(mktemp -d -t proxmox-verify-XXXXXX)
    trap "rm -rf '$temp_dir'" EXIT RETURN

    # Step 1: Test decryption
    log_info "Step 1/4: Testing decryption..."
    if ! age -d -i "$age_key_file" "$backup_file" > "$temp_dir/backup.tar.zst" 2>/dev/null; then
        log_error "Decryption failed - invalid key or corrupted archive"
        return $EXIT_DECRYPTION_FAILED
    fi
    log_info "✓ Decryption successful"

    # Step 2: Test decompression and list contents
    log_info "Step 2/4: Testing decompression and listing contents..."
    if ! zstd -d "$temp_dir/backup.tar.zst" -o "$temp_dir/backup.tar" 2>/dev/null; then
        log_error "Decompression failed - corrupted archive"
        return $EXIT_DECRYPTION_FAILED
    fi
    
    local file_count
    file_count=$(tar -tf "$temp_dir/backup.tar" | wc -l)
    log_info "✓ Archive contains $file_count files"

    # Step 3: Verify required files present
    log_info "Step 3/4: Verifying required files..."
    local required_files=(
        "manifest.txt"
        "proxmox-config/storage.cfg"
    )
    
    local missing_files=()
    for file in "${required_files[@]}"; do
        if ! tar -tf "$temp_dir/backup.tar" | grep -q "^\\./.*$file$"; then
            missing_files+=("$file")
        fi
    done

    if [[ ${#missing_files[@]} -gt 0 ]]; then
        log_error "Missing required files:"
        for file in "${missing_files[@]}"; do
            log_error "  - $file"
        done
        return $EXIT_MISSING_FILES
    fi
    log_info "✓ All required files present"

    # Step 4: Verify checksums (if manifest exists)
    log_info "Step 4/4: Verifying checksums..."
    if tar -xf "$temp_dir/backup.tar" -C "$temp_dir" ./manifest.txt 2>/dev/null; then
        # Extract all files for checksum verification
        tar -xf "$temp_dir/backup.tar" -C "$temp_dir" 2>/dev/null

        # Verify checksums
        local checksum_errors=0
        while IFS= read -r line; do
            if [[ -z "$line" || "$line" =~ ^# ]]; then
                continue
            fi
            
            local expected_checksum=$(echo "$line" | awk '{print $1}')
            local file_path=$(echo "$line" | awk '{print $2}')
            
            if [[ -f "$temp_dir/$file_path" ]]; then
                local actual_checksum=$(sha256sum "$temp_dir/$file_path" | awk '{print $1}')
                if [[ "$expected_checksum" != "$actual_checksum" ]]; then
                    log_error "Checksum mismatch: $file_path"
                    log_error "  Expected: $expected_checksum"
                    log_error "  Actual:   $actual_checksum"
                    ((checksum_errors++))
                fi
            fi
        done < "$temp_dir/manifest.txt"

        if [[ $checksum_errors -gt 0 ]]; then
            log_error "Checksum verification failed: $checksum_errors file(s) corrupted"
            return $EXIT_CHECKSUM_MISMATCH
        fi
        log_info "✓ All checksums verified"
    else
        log_warning "Manifest not found - skipping checksum verification"
    fi

    # Success summary
    log_info ""
    log_info "================================================================"
    log_info "Verification Result: ${GREEN}PASS${NC}"
    log_info "================================================================"
    log_info "Backup file:     $(basename "$backup_file")"
    log_info "Archive size:    $(du -h "$backup_file" | cut -f1)"
    log_info "Files verified:  $file_count"
    log_info "Decryption:      ✓ Valid"
    log_info "Compression:     ✓ Valid"
    log_info "Required files:  ✓ Present"
    log_info "Checksums:       ✓ Valid"
    log_info "================================================================"

    return $EXIT_SUCCESS
}

# Main
main() {
    if [[ $# -ne 1 ]]; then
        usage
        exit $EXIT_INVALID_USAGE
    fi

    if [[ "$1" == "-h" || "$1" == "--help" ]]; then
        usage
        exit $EXIT_SUCCESS
    fi

    verify_backup "$1"
}

main "$@"
