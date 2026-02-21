#!/bin/bash
# scripts/lab/lib/rebuild.sh

# Provisioning defaults (overridable via env)
PROVISION_SSH_TIMEOUT_SEC="${PROVISION_SSH_TIMEOUT_SEC:-600}"   # >=5 minutes per requirements
PROVISION_SSH_INTERVAL_SEC="${PROVISION_SSH_INTERVAL_SEC:-5}"
PROVISION_SSH_USER="${PROVISION_SSH_USER:-ansible}"
PROVISION_SSH_KEY="${PROVISION_SSH_KEY:-}"
PROVISION_SSH_PUBKEY="${PROVISION_SSH_PUBKEY:-}"
PROVISION_SSH_KEY_TEMP="${PROVISION_SSH_KEY_TEMP:-false}"

ensure_provisioning_ssh_material() {
    # Reuse user-supplied key material when provided
    if [[ -n "$PROVISION_SSH_KEY" && -f "$PROVISION_SSH_KEY" ]]; then
        if [[ -z "$PROVISION_SSH_PUBKEY" ]]; then
            PROVISION_SSH_PUBKEY="${PROVISION_SSH_KEY}.pub"
        fi
        return 0
    fi

    # Generate ephemeral keypair for provisioning waits when none provided
    local key_dir
    key_dir="${TMPDIR:-/tmp}/pve-lab-${RUN_ID:-$$}"
    mkdir -p "$key_dir"

    PROVISION_SSH_KEY="${key_dir}/provision_ed25519"
    PROVISION_SSH_PUBKEY="${PROVISION_SSH_KEY}.pub"

    if [[ ! -f "$PROVISION_SSH_KEY" ]]; then
        log_info "Generating ephemeral provisioning SSH keypair"
        ssh-keygen -t ed25519 -N '' -C "pve-lab-provision-${RUN_ID:-$(date +%s)}" -f "$PROVISION_SSH_KEY" >/dev/null
        chmod 600 "$PROVISION_SSH_KEY"
        PROVISION_SSH_KEY_TEMP="true"
    fi
}

cleanup_provisioning_ssh_material() {
    if [[ "${PROVISION_SSH_KEY_TEMP:-false}" != "true" ]]; then
        return 0
    fi

    rm -f "$PROVISION_SSH_KEY" "$PROVISION_SSH_PUBKEY" 2>/dev/null || true
    rmdir "$(dirname "$PROVISION_SSH_KEY")" 2>/dev/null || true
    PROVISION_SSH_KEY_TEMP="false"
}


build_provision_ssh_opts() {
    local opts="$SSH_OPTS"
    if [[ -n "$PROVISION_SSH_KEY" ]]; then
        opts="$opts -i $PROVISION_SSH_KEY"
    fi
    # Ensure we never hang on password prompts during CI waits
    opts="$opts -o BatchMode=yes -o ConnectTimeout=5 -o ConnectionAttempts=1"
    echo "$opts"
}

wait_for_provisioning_ssh() {
    local target_ip="$1"
    local ssh_user="$PROVISION_SSH_USER"
    local timeout_sec="$PROVISION_SSH_TIMEOUT_SEC"
    local interval_sec="$PROVISION_SSH_INTERVAL_SEC"
    local ssh_opts
    ssh_opts=$(build_provision_ssh_opts)

    local start_ts end_ts elapsed
    start_ts=$(date +%s)
    end_ts=$((start_ts + timeout_sec))

    local log_file="${EVIDENCE_ROOT:-${ARTIFACT_DIR:-/tmp}}/logs/provisioning-ssh-wait.log"
    mkdir -p "$(dirname "$log_file")"

    log_info "Waiting for SSH (${ssh_user}@${target_ip}) for up to ${timeout_sec}s..."
    while [[ $(date +%s) -lt $end_ts ]]; do
        if is_local_proxmox; then
            # When running on the Proxmox host itself, don't ProxyJump back to the same host.
            if ssh $ssh_opts "${ssh_user}@${target_ip}" "echo ready" >/dev/null 2>&1; then
                elapsed=$(( $(date +%s) - start_ts ))
                log_info "SSH ready after ${elapsed}s"
                echo "SSH ready after ${elapsed}s" > "$log_file"
                return 0
            fi
        else
            if ssh $ssh_opts -J "$SSH_USER@$PROXMOX_HOST" "${ssh_user}@${target_ip}" "echo ready" >/dev/null 2>&1; then
                elapsed=$(( $(date +%s) - start_ts ))
                log_info "SSH ready after ${elapsed}s"
                echo "SSH ready after ${elapsed}s" > "$log_file"
                return 0
            fi
        fi
        sleep "$interval_sec"
    done

    elapsed=$(( $(date +%s) - start_ts ))
    log_error "Timeout waiting for SSH on ${target_ip} after ${elapsed}s"
    echo "Timeout after ${elapsed}s" > "$log_file"
    return 1
}

is_local_proxmox() {
    local host_lower="${PROXMOX_HOST,,}"
    local hostname_short
    hostname_short=$(hostname -s)
    local hostname_fqdn
    hostname_fqdn=$(hostname -f 2>/dev/null || hostname)
    local hostname_label
    hostname_label=${hostname_fqdn%%.*}
    [[ "$host_lower" == "localhost" || "$host_lower" == "127.0.0.1" || "$host_lower" == "${hostname_short,,}" || "$host_lower" == "${hostname_fqdn,,}" || "$host_lower" == "${hostname_label,,}" ]]
}

build_ssh_target() {
    if [[ -n "${SSH_TARGET:-}" ]]; then
        echo "$SSH_TARGET"
        return 0
    fi
    if [[ -n "${SSH_USER:-}" ]]; then
        echo "${SSH_USER}@${PROXMOX_HOST}"
        return 0
    fi
    echo "${PROXMOX_HOST}"
}

host_exec() {
    local cmd="$1"
    if is_local_proxmox; then
        PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:$PATH" bash -lc "$cmd"
    else
        local target
        target="$(build_ssh_target)"
        ssh $SSH_OPTS "$target" "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin $cmd"
    fi
}

cmd_rebuild() {
    local profile="rebuild-hypervisor-nested-workload"
    local apply=false
    local dry_run=true
    local keep=false
    local no_verify=false
    local apply_sudoers=false
    local start_time_epoch
    local start_time_iso

    start_time_epoch="$(date +%s)"
    start_time_iso="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

    if ! run_dependency_preflight; then
        log_error "Dependency preflight failed; install missing tools (jq, ssh, rsync) before rebuild."
        exit 1
    fi

    if ! ensure_artifact_root; then
        log_error "Artifact root missing or not writable; create ${ARTIFACT_ROOT} and ensure ci owns it."
        exit 1
    fi

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --profile) profile="$2"; shift 2 ;;
            --apply) apply=true; dry_run=false; shift ;;
            --dry-run) dry_run=true; apply=false; shift ;;
            --keep) keep=true; shift ;;
            --verify) no_verify=false; shift ;;
            --no-verify) no_verify=true; shift ;;
            --apply-sudoers) apply_sudoers=true; shift ;;
            *) log_error "Unknown option: $1"; exit 1 ;;
        esac
    done

    log_info "Starting Rebuild Orchestrator"
    log_info "  Profile: $profile"
    log_info "  Mode: $([[ "$apply" == "true" ]] && echo "APPLY (Remediation Enabled)" || echo "DRY-RUN (Validate Only)")"

    # Load Profile
    local profile_path="${SCRIPT_DIR}/profiles.d/${profile}.profile"
    if [[ ! -f "$profile_path" ]]; then
        log_error "Profile not found: $profile_path"
        exit 1
    fi
    source "$profile_path"

    # Initialize Evidence Pack
    local run_id
    local base_dir
    base_dir="$(artifact_runs_path)"
    mkdir -p "$base_dir"

    run_id="$(create_evidence_pack "$base_dir")"
    export RUN_ID="$run_id"
    export ARTIFACT_DIR="${base_dir}/${run_id}"
    export EVIDENCE_ROOT="$ARTIFACT_DIR"

    # Reuse harness evidence layout and provenance
    evidence_init "$run_id" "$profile"
    local ssh_target="${SSH_USER}@${PROXMOX_HOST}"
    generate_provenance \
        "$ARTIFACT_DIR/provenance.json" \
        "$profile" \
        "$ssh_target" \
        "mode=$([[ "$apply" == "true" ]] && echo "apply" || echo "dry-run")" \
        "keep=$keep"

    # Initialize JSONL
    init_jsonl_events "$ARTIFACT_DIR/logs/events.jsonl"
    emit_event "rebuild_started" "$RUN_ID" "profile=$profile" "mode=$([[ "$apply" == "true" ]] && echo "APPLY" || echo "DRY-RUN")"

    # Lock
    exec 200>"$LOCK_FILE"
    if ! flock -n 200; then
        log_error "Another instance is running (Lock: $LOCK_FILE). Aborting."
        exit 1
    fi

    # 2. Baseline Host Checks
    log_info "Phase: Baseline Host Checks"
    export CURRENT_PHASE="baseline-host"
    export CURRENT_SOURCE="harness"

    mkdir -p "${ARTIFACT_DIR}/reports/host"

    if ! run_baseline_host_checks; then
        log_error "Critical Baseline Host Checks Failed. Aborting."
        finalize_rebuild "FAIL" "$no_verify" "$start_time_epoch" "$start_time_iso"
        exit 1
    fi

    # 3. Baseline Template Checks
    log_info "Phase: Baseline Template Checks"
    export CURRENT_PHASE="baseline-templates"

    mkdir -p "${ARTIFACT_DIR}/reports/templates"

    local templates_valid=true
    if ! run_baseline_template_checks; then
        templates_valid=false
    fi

    # 4. Remediation
    if [[ "$templates_valid" == "false" ]]; then
        if [[ "$apply" == "true" ]]; then
            log_info "Attempting remediation of templates..."
            if remediate_templates; then
                log_info "Remediation complete. Re-running template checks..."
                prune_checks_by_phase "baseline-templates"
                if run_baseline_template_checks; then
                    templates_valid=true
                else
                    log_error "Template checks failed even after remediation."
                    finalize_rebuild "FAIL" "$no_verify" "$start_time_epoch" "$start_time_iso"
                    exit 1
                fi
            else
                log_error "Remediation failed."
                finalize_rebuild "FAIL" "$no_verify" "$start_time_epoch" "$start_time_iso"
                exit 1
            fi
        else
            log_error "Template checks failed. Run with --apply to remediate."
            finalize_rebuild "FAIL" "$no_verify" "$start_time_epoch" "$start_time_iso"
            exit 1
        fi
    fi

    # 5. Suite Execution
    log_info "Phase: Suite Execution ($SUITE_PROFILE)"

    # Call cmd_run with SKIP_LOCK=true and existing env vars
    export SKIP_LOCK=true

    if cmd_run --profile "$SUITE_PROFILE" $([[ "$keep" == "true" ]] && echo "--keep") $([[ "$no_verify" == "true" ]] && echo "--no-verify" || echo "--verify") $([[ "$apply_sudoers" == "true" ]] && echo "--apply-sudoers"); then
        :
    else
        finalize_rebuild "FAIL" "$no_verify" "$start_time_epoch" "$start_time_iso"
        exit 1
    fi

    if ! finalize_rebuild "SUCCESS" "$no_verify" "$start_time_epoch" "$start_time_iso"; then
        exit 1
    fi
}

finalize_rebuild() {
    local status="$1"
    local no_verify="$2"
    local start_time_epoch="$3"
    local start_time_iso="$4"

    local artifact_dir="$ARTIFACT_DIR"
    local run_id="$RUN_ID"
    local end_time_epoch
    local end_time_iso
    local duration_seconds
    local verification_status="SKIPPED"
    local verification_report_path=""

    end_time_epoch="$(date +%s)"
    end_time_iso="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
    if [[ -n "$start_time_epoch" ]]; then
        duration_seconds=$((end_time_epoch - start_time_epoch))
    else
        duration_seconds=0
        start_time_epoch="$end_time_epoch"
        start_time_iso="$end_time_iso"
    fi

        # Always serialize checks so verifier can run even on early failures
        mkdir -p "$artifact_dir/reports"
        mkdir -p "$artifact_dir/logs"
        serialize_checks "$artifact_dir/checks.json"

        # Pre-create summary so verifier sees required files even on failure
        local pre_verification_status="$verification_status"
        local pre_verification_report_path="$verification_report_path"
        if [[ "$no_verify" == "false" ]]; then
                pre_verification_status="PENDING"
                pre_verification_report_path="reports/verify.json"
        fi

        cat > "$artifact_dir/summary.json" <<JSON
{
    "contract_version": "1.0.0",
    "run_id": "$run_id",
    "profile_id": "${PROFILE_ID:-${profile:-unknown}}",
    "suite_profile": "${SUITE_PROFILE:-unknown}",
    "status": "$status",
    "start_time": "$start_time_epoch",
    "start_time_iso": "$start_time_iso",
    "end_time": "$end_time_epoch",
    "end_time_iso": "$end_time_iso",
    "duration_seconds": $duration_seconds,
    "checks_file": "checks.json",
    "provenance_file": "provenance.json",
    "evidence_manifest_file": "evidence_manifest.json",
    "verification": {
        "status": "$pre_verification_status",
        "report_path": "$pre_verification_report_path"
    }
}
JSON

    if [[ "$no_verify" == "false" ]]; then
        log_info "Running Evidence Verification (Rebuild)..."
        if python3 "$SCRIPT_DIR/verify_evidence.py" "$artifact_dir" | tee "$artifact_dir/reports/verify.log"; then
            verification_status="PASS"
        else
            verification_status="FAIL"
            if [[ "$status" == "SUCCESS" ]]; then
                status="FAILED_VERIFICATION"
            fi
        fi
        verification_report_path="reports/verify.json"
    fi

    cat > "$artifact_dir/summary.json" <<JSON
{
  "contract_version": "1.0.0",
  "run_id": "$run_id",
  "profile_id": "${PROFILE_ID:-${profile:-unknown}}",
  "suite_profile": "${SUITE_PROFILE:-unknown}",
  "status": "$status",
  "start_time": "$start_time_epoch",
  "start_time_iso": "$start_time_iso",
  "end_time": "$end_time_epoch",
  "end_time_iso": "$end_time_iso",
  "duration_seconds": $duration_seconds,
  "checks_file": "checks.json",
  "provenance_file": "provenance.json",
  "evidence_manifest_file": "evidence_manifest.json",
  "verification": {
    "status": "$verification_status",
    "report_path": "$verification_report_path"
  }
}
JSON

    evidence_finalize "$status"

    [[ "$status" == "SUCCESS" ]] && return 0 || return 1
}

    append_teardown_log() {
        local evidence_file="$1"
        local label="$2"
        local cmd="$3"
        local rc="$4"
        local output="$5"
        local ts
        ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

        {
            echo "[$ts] ${label}"
            echo "CMD: ${cmd}"
            echo "RC: ${rc}"
            echo "OUTPUT:"
            [[ -n "$output" ]] && echo "$output" || echo "<empty>"
            echo ""
        } >> "$evidence_file"
    }

    run_teardown_cmd() {
        local evidence_file="$1"
        local label="$2"
        local remote_cmd="$3"

        local output
        output=$(host_exec "$remote_cmd" 2>&1)
        local rc=$?
        append_teardown_log "$evidence_file" "$label" "$remote_cmd" "$rc" "$output"
        return $rc
    }

    teardown_vm_with_retries() {
        local vmid="$1"
        local evidence_file="${EVIDENCE_ROOT}/reports/cleanup/teardown-vm-${vmid}.txt"
        mkdir -p "$(dirname "$evidence_file")"

        local exists=true
        if ! host_exec "sudo -n /usr/sbin/qm status $vmid" >/dev/null 2>&1; then
            exists=false
            append_teardown_log "$evidence_file" "vm-$vmid" "sudo -n /usr/sbin/qm status $vmid" "1" "VM $vmid not found"
        fi

        local attempts=0
        local success=false
        local last_rc=0

        while [[ $attempts -lt 3 && "$exists" == "true" ]]; do
            attempts=$((attempts + 1))

            run_teardown_cmd "$evidence_file" "vm-$vmid stop attempt $attempts" "sudo -n /usr/sbin/qm stop $vmid --skiplock"

            # Wait for not-running state (best-effort)
            for _ in {1..5}; do
                if host_exec "sudo -n /usr/sbin/qm status $vmid" 2>/dev/null | grep -q "status: running"; then
                    sleep 2
                else
                    break
                fi
            done

            run_teardown_cmd "$evidence_file" "vm-$vmid destroy attempt $attempts" "sudo -n /usr/sbin/qm destroy $vmid --purge"
            last_rc=$?

            if [[ $last_rc -eq 0 ]]; then
                success=true
                break
            fi

            # rc=25 indicates still running; retry after stop
            if [[ $last_rc -ne 25 ]]; then
                break
            fi
        done

        local result="PASS"
        local reason="Destroyed VM $vmid"
        if [[ "$exists" != "true" ]]; then
            reason="VM $vmid not present"
        elif [[ "$success" != "true" ]]; then
            result="FAIL"
            reason="VM $vmid destroy failed after ${attempts} attempt(s), rc=${last_rc}"
        fi

        append_teardown_log "$evidence_file" "vm-$vmid final" "result" "-" "$reason"

        export CURRENT_SOURCE="harness"
        export CURRENT_PHASE="cleanup"
        record_check "TEARDOWN-001" "Nested VM destroyed cleanly (no destroy errors)" "high" "PASS" "$result" "$reason" "reports/cleanup/teardown-vm-${vmid}.txt"

        [[ "$result" == "PASS" ]] && return 0 || return 1
    }

    teardown_lxc_with_retries() {
        local ctid="$1"
        local evidence_file="${EVIDENCE_ROOT}/reports/cleanup/teardown-lxc-${ctid}.txt"
        mkdir -p "$(dirname "$evidence_file")"

        local exists=true
        if ! host_exec "pct status $ctid" >/dev/null 2>&1; then
            exists=false
            append_teardown_log "$evidence_file" "lxc-$ctid" "pct status $ctid" "1" "CT $ctid not found"
        fi

        local attempts=0
        local success=false
        local last_rc=0

        while [[ $attempts -lt 3 && "$exists" == "true" ]]; do
            attempts=$((attempts + 1))

            run_teardown_cmd "$evidence_file" "lxc-$ctid stop attempt $attempts" "pct stop $ctid --force"

            for _ in {1..5}; do
                if host_exec "pct status $ctid" 2>/dev/null | grep -q "status: running"; then
                    sleep 2
                else
                    break
                fi
            done

            run_teardown_cmd "$evidence_file" "lxc-$ctid destroy attempt $attempts" "pct destroy $ctid --purge --force"
            last_rc=$?

            if [[ $last_rc -eq 0 ]]; then
                success=true
                break
            fi

            if [[ $last_rc -ne 25 ]]; then
                break
            fi
        done

        local result="PASS"
        local reason="Destroyed LXC $ctid"
        if [[ "$exists" != "true" ]]; then
            reason="LXC $ctid not present"
        elif [[ "$success" != "true" ]]; then
            result="FAIL"
            reason="LXC $ctid destroy failed after ${attempts} attempt(s), rc=${last_rc}"
        fi

        append_teardown_log "$evidence_file" "lxc-$ctid final" "result" "-" "$reason"

        export CURRENT_SOURCE="harness"
        export CURRENT_PHASE="cleanup"
        record_check "TEARDOWN-002" "Nested LXC destroyed cleanly (no destroy errors)" "high" "PASS" "$result" "$reason" "reports/cleanup/teardown-lxc-${ctid}.txt"

        [[ "$result" == "PASS" ]] && return 0 || return 1
    }

run_baseline_host_checks() {
    local ssh_target
    ssh_target="$(build_ssh_target)"
    local failed=0

    # HOST-001: SSH
    local ssh_output
    local ssh_evidence="${ARTIFACT_DIR}/reports/host/HOST-001-ssh.txt"
    if ssh_output=$(host_exec "echo pong" 2>&1); then
        echo "$ssh_output" > "$ssh_evidence"
        log_info "HOST-001: SSH OK target=${ssh_target} host=${PROXMOX_HOST} user=${SSH_USER}"
        record_check "HOST-001" "Proxmox host reachable via SSH" "blocker" "PASS" "PASS" "SSH connection successful" "reports/host/HOST-001-ssh.txt"
    else
        echo "$ssh_output" > "$ssh_evidence"
        log_error "HOST-001: SSH failed target=${ssh_target} host=${PROXMOX_HOST} user=${SSH_USER} opts='${SSH_OPTS}' output=${ssh_output}"
        record_check "HOST-001" "Proxmox host reachable via SSH" "blocker" "PASS" "FAIL" "SSH connection failed" "reports/host/HOST-001-ssh.txt"
        return 1
    fi

    # HOST-002: Bridge
    local bridge_check
    bridge_check=$(host_exec "ip addr show $LAB_BRIDGE" 2>&1)
    echo "$bridge_check" > "${ARTIFACT_DIR}/reports/host/HOST-002-bridge.txt"

    if echo "$bridge_check" | grep -q "$LAB_GATEWAY"; then
        record_check "HOST-002" "Required bridge exists and has expected gateway IP" "blocker" "PASS" "PASS" "Bridge $LAB_BRIDGE has IP $LAB_GATEWAY" "reports/host/HOST-002-bridge.txt"
    else
        record_check "HOST-002" "Required bridge exists and has expected gateway IP" "blocker" "PASS" "FAIL" "Bridge $LAB_BRIDGE missing or wrong IP" "reports/host/HOST-002-bridge.txt"
        failed=1
    fi

    # HOST-003: Storage
    local storage_check
    # Avoid sudo PATH overrides that violate secure_path; use absolute binary path
    storage_check=$(host_exec "sudo -n /usr/sbin/pvesm status" 2>&1)
    local storage_rc=$?
    echo "$storage_check" > "${ARTIFACT_DIR}/reports/host/HOST-003-storage.txt"

    if [[ $storage_rc -ne 0 ]]; then
        record_check "HOST-003" "Required storage backend exists" "blocker" "PASS" "FAIL" "pvesm status rc=$storage_rc" "reports/host/HOST-003-storage.txt"
        failed=1
    elif echo "$storage_check" | grep -q "local-lvm"; then
        record_check "HOST-003" "Required storage backend exists" "blocker" "PASS" "PASS" "Storage local-lvm found" "reports/host/HOST-003-storage.txt"
    else
        record_check "HOST-003" "Required storage backend exists" "blocker" "PASS" "FAIL" "Storage local-lvm missing" "reports/host/HOST-003-storage.txt"
        failed=1
    fi

    # HOST-004: Nested
    local nested_check
    nested_check=$(host_exec "cat /sys/module/kvm_intel/parameters/nested 2>/dev/null || cat /sys/module/kvm_amd/parameters/nested 2>/dev/null")
    echo "$nested_check" > "${ARTIFACT_DIR}/reports/host/HOST-004-nested.txt"

    if [[ "$nested_check" == "Y" || "$nested_check" == "1" ]]; then
        record_check "HOST-004" "Host nested virtualization enabled" "high" "PASS" "PASS" "Nested virtualization enabled ($nested_check)" "reports/host/HOST-004-nested.txt"
    else
        record_check "HOST-004" "Host nested virtualization enabled" "high" "PASS" "FAIL" "Nested virtualization disabled ($nested_check)" "reports/host/HOST-004-nested.txt"
    fi

    return $failed
}

run_baseline_template_checks() {
    local failed=0
    # Use sudo without PATH override to satisfy sudoers secure_path rules
    local qm_cmd="sudo -n /usr/sbin/qm"

    # TPL-001: Base Template
    local tpl1_status
    tpl1_status=$(host_exec "$qm_cmd status $LAB_TEMPLATE_VMID" 2>&1)
    echo "$tpl1_status" > "${ARTIFACT_DIR}/reports/templates/TPL-001-qm-status-${LAB_TEMPLATE_VMID}.txt"

    if echo "$tpl1_status" | grep -q "status:"; then
        record_check "TPL-001" "Base template exists (VMID $LAB_TEMPLATE_VMID)" "blocker" "PASS" "PASS" "Template found" "reports/templates/TPL-001-qm-status-${LAB_TEMPLATE_VMID}.txt"
    else
        record_check "TPL-001" "Base template exists (VMID $LAB_TEMPLATE_VMID)" "blocker" "PASS" "FAIL" "Template missing" "reports/templates/TPL-001-qm-status-${LAB_TEMPLATE_VMID}.txt"
        failed=1
    fi

    # TPL-002: Tier2 Template
    local tpl2_status
    tpl2_status=$(host_exec "$qm_cmd status $LAB_TEMPLATE_VMID_TIER2" 2>&1)
    echo "$tpl2_status" > "${ARTIFACT_DIR}/reports/templates/TPL-002-qm-status-${LAB_TEMPLATE_VMID_TIER2}.txt"

    if echo "$tpl2_status" | grep -q "status:"; then
        record_check "TPL-002" "Tier2 template exists (VMID $LAB_TEMPLATE_VMID_TIER2)" "blocker" "PASS" "PASS" "Template found" "reports/templates/TPL-002-qm-status-${LAB_TEMPLATE_VMID_TIER2}.txt"
    else
        record_check "TPL-002" "Tier2 template exists (VMID $LAB_TEMPLATE_VMID_TIER2)" "blocker" "PASS" "FAIL" "Template missing" "reports/templates/TPL-002-qm-status-${LAB_TEMPLATE_VMID_TIER2}.txt"
        failed=1
    fi

    # TPL-003: Template State
    local tpl3_failed=0
    local tpl3_evidence_refs=()
    for vmid in $LAB_TEMPLATE_VMID $LAB_TEMPLATE_VMID_TIER2; do
        local config
        config=$(host_exec "$qm_cmd config $vmid" 2>&1)
        echo "$config" > "${ARTIFACT_DIR}/reports/templates/TPL-003-qm-config-${vmid}.txt"
        tpl3_evidence_refs+=("reports/templates/TPL-003-qm-config-${vmid}.txt")

        if echo "$config" | grep -q "template: 1"; then
             :
        else
             tpl3_failed=1
        fi
    done
    if [[ $tpl3_failed -eq 0 ]]; then
        record_check "TPL-003" "Templates are marked as templates" "high" "PASS" "PASS" "All templates marked correctly" "${tpl3_evidence_refs[@]}"
    else
        record_check "TPL-003" "Templates are marked as templates" "high" "PASS" "FAIL" "One or more templates not marked as template" "${tpl3_evidence_refs[@]}"
        failed=1
    fi

    # TPL-004: Tags
    local tpl4_failed=0
    local tpl4_evidence_refs=()
    for vmid in $LAB_TEMPLATE_VMID $LAB_TEMPLATE_VMID_TIER2; do
        local config
        config=$(host_exec "$qm_cmd config $vmid" 2>&1)
        echo "$config" > "${ARTIFACT_DIR}/reports/templates/TPL-004-tags-${vmid}.txt"
        tpl4_evidence_refs+=("reports/templates/TPL-004-tags-${vmid}.txt")

        if echo "$config" | grep -q "$IDENTITY_TAG_KEY"; then
             :
        else
             tpl4_failed=1
        fi
    done
    if [[ $tpl4_failed -eq 0 ]]; then
        record_check "TPL-004" "Templates have identity markers (ManagedBy tag policy)" "high" "PASS" "PASS" "All templates have identity tags" "${tpl4_evidence_refs[@]}"
    else
        record_check "TPL-004" "Templates have identity markers (ManagedBy tag policy)" "high" "PASS" "FAIL" "One or more templates missing identity tags" "${tpl4_evidence_refs[@]}"
        failed=1
    fi

    # TPL-005: Cloud-init
    local tpl5_failed=0
    local tpl5_evidence_refs=()
    for vmid in $LAB_TEMPLATE_VMID $LAB_TEMPLATE_VMID_TIER2; do
        local config
        config=$(host_exec "$qm_cmd config $vmid" 2>&1)
        echo "$config" > "${ARTIFACT_DIR}/reports/templates/TPL-005-cloudinit-${vmid}.txt"
        tpl5_evidence_refs+=("reports/templates/TPL-005-cloudinit-${vmid}.txt")

        if echo "$config" | grep -q "ciuser:" && echo "$config" | grep -q "sshkeys:"; then
             :
        else
             tpl5_failed=1
        fi
    done
    if [[ $tpl5_failed -eq 0 ]]; then
        record_check "TPL-005" "Templates have cloud-init user and SSH key configured" "high" "PASS" "PASS" "All templates have cloud-init configured" "${tpl5_evidence_refs[@]}"
    else
        record_check "TPL-005" "Templates have cloud-init user and SSH key configured" "high" "PASS" "FAIL" "One or more templates missing cloud-init config" "${tpl5_evidence_refs[@]}"
        failed=1
    fi

    # TPL-006: Naming
    local tpl6_failed=0
    local tpl6_evidence_refs=()
    for vmid in $LAB_TEMPLATE_VMID $LAB_TEMPLATE_VMID_TIER2; do
        local config
        config=$(host_exec "$qm_cmd config $vmid" 2>&1)
        # Check name
        local name
        name=$(echo "$config" | grep "name:" | awk '{print $2}')
        echo "name: $name" > "${ARTIFACT_DIR}/reports/templates/TPL-006-naming-${vmid}.txt"
        tpl6_evidence_refs+=("reports/templates/TPL-006-naming-${vmid}.txt")

        if [[ "$name" =~ ^lab-tpl- ]]; then
            :
        else
            tpl6_failed=1
        fi
    done
    if [[ $tpl6_failed -eq 0 ]]; then
        record_check "TPL-006" "Template metadata conforms to naming policy" "medium" "PASS" "PASS" "All templates named correctly" "${tpl6_evidence_refs[@]}"
    else
        record_check "TPL-006" "Template metadata conforms to naming policy" "medium" "PASS" "FAIL" "One or more templates have invalid names" "${tpl6_evidence_refs[@]}"
        failed=1
    fi

    return $failed
}

remediate_templates() {
    local rem_log="${ARTIFACT_DIR}/logs/remediation-templates.log"

    log_info "Remediating templates..."
    emit_event "remediation_start" "$RUN_ID" "scope=templates" "target_host=${SSH_USER}@${PROXMOX_HOST}"
    mkdir -p "${ARTIFACT_DIR}/logs"
    : > "$rem_log"

    # Helper to destroy if exists
    destroy_if_exists() {
        local vmid="$1"
        if host_exec "sudo -n /usr/sbin/qm status $vmid" >/dev/null 2>&1; then
            log_info "Destroying existing template $vmid..."
            emit_event "remediation_step" "$RUN_ID" "action=destroy" "vmid=$vmid"
            # Purge to remove disk images too
            if ! host_exec "sudo -n /usr/sbin/qm destroy $vmid --purge" >>"$rem_log" 2>&1; then
                log_error "Failed to destroy template $vmid. It might have linked clones."
                emit_event "remediation_error" "$RUN_ID" "action=destroy" "vmid=$vmid"
                return 1
            fi
        fi
        return 0
    }

    # Destroy 9001 and 9002
    if ! destroy_if_exists "$LAB_TEMPLATE_VMID"; then return 1; fi
    if ! destroy_if_exists "$LAB_TEMPLATE_VMID_TIER2"; then return 1; fi

    # Create Tier 1
    log_info "Creating Tier 1 Template ($LAB_TEMPLATE_VMID)..."
    emit_event "remediation_step" "$RUN_ID" "action=create" "vmid=$LAB_TEMPLATE_VMID" "tier=1"
    if ! "$SCRIPT_DIR/create_tier1_template.sh" >>"$rem_log" 2>&1; then
        log_error "Failed to create Tier 1 template."
        emit_event "remediation_error" "$RUN_ID" "action=create" "vmid=$LAB_TEMPLATE_VMID" "tier=1"
        return 1
    fi

    # Create Tier 2
    log_info "Creating Tier 2 Template ($LAB_TEMPLATE_VMID_TIER2)..."
    emit_event "remediation_step" "$RUN_ID" "action=create" "vmid=$LAB_TEMPLATE_VMID_TIER2" "tier=2"
    if ! "$SCRIPT_DIR/create_tier2_template.sh" >>"$rem_log" 2>&1; then
        log_error "Failed to create Tier 2 template."
        emit_event "remediation_error" "$RUN_ID" "action=create" "vmid=$LAB_TEMPLATE_VMID_TIER2" "tier=2"
        return 1
    fi

    emit_event "remediation_complete" "$RUN_ID" "scope=templates" "log=${rem_log#${ARTIFACT_DIR}/}"

    return 0
}

load_rebuild_config() {
    local config_path="${REBUILD_CONFIG_PATH:-${REPO_ROOT:-}/scripts/lab/rebuild-config.json}"
    if [[ ! -f "$config_path" ]]; then
        log_error "Rebuild config not found: $config_path"
        return 1
    fi

    REBUILD_CONFIG_PATH="$config_path"
    REBUILD_DEFAULT_ENVIRONMENT=$(jq -r '.default_environment' "$config_path")
    REBUILD_PROD_CONFIRM_STRING=$(jq -r '.prod_confirm_string' "$config_path")
    REBUILD_SERVICE_DEPLOY_CONFIRM_STRING=$(jq -r '.service_deploy_confirm_string' "$config_path")
    REBUILD_SERVICE_ALLOWLIST_PATH=$(jq -r '.service_allowlist_path' "$config_path")

    mapfile -t REBUILD_REQUIRED_MOUNTS < <(jq -r '.required_host_mounts[]' "$config_path")
    mapfile -t REBUILD_PHASES < <(jq -r '.phases[]' "$config_path")
}

rebuild_should_run_phase() {
    local phase="$1"
    shift
    local -a selected=("$@")
    if [[ ${#selected[@]} -eq 0 ]]; then
        return 0
    fi
    for item in "${selected[@]}"; do
        if [[ "$item" == "$phase" ]]; then
            return 0
        fi
    done
    return 1
}

rebuild_write_preflight_summary() {
    local output_file="$1"
    local environment="$2"
    local mode="$3"
    local confirm="$4"
    shift 4
    local -a phases=("$@")

    mkdir -p "$(dirname "$output_file")"
    {
        echo "Rebuild Preflight Summary"
        echo "Environment: ${environment}"
        echo "Mode: ${mode}"
        echo "Run ID: ${RUN_ID}"
        echo "Evidence Dir: ${ARTIFACT_DIR}"
        echo "Phases: ${phases[*]}"
        echo "Confirm String: ${confirm:-<none>}"
        echo "Backup Dir: ${REBUILD_BACKUP_DIR:-<unset>}"
        echo "Remote Repo Root: ${REMOTE_REPO_ROOT:-/var/lib/homelab-proxmox}"
        echo "Apply Network: ${REBUILD_APPLY_NETWORK:-false}"
        echo "Apply FSTAB: ${REBUILD_APPLY_FSTAB:-false}"
    } > "$output_file"
}

rebuild_write_evidence_index() {
    local output_file="${ARTIFACT_DIR}/reports/rebuild-evidence-index.md"
    mkdir -p "$(dirname "$output_file")"
    cat > "$output_file" <<EOF
# Rebuild Evidence Index

- Preflight summary: reports/preflight-summary.txt
- Mount checks: reports/mounts/
- Restore summary: reports/restore/restore-summary.txt
- IaC summary: reports/iac/iac-summary.txt
- Service logs: reports/services/
- Verification summary: reports/verify/verify-summary.txt
- Checks: checks.json
- State: state.json
EOF
}

rebuild_phase_mounts() {
    local failed=0
    local remediation_attempted=0

    # First pass: validation
    log_info "Validating host NFS mounts..."
    if ! run_rebuild_host_mount_checks; then
        log_warn "Host mount checks failed - attempting automatic remediation"

        # Invoke Ansible mount role
        record_check "MNT-REMEDIATE-001" "Invoking mount remediation" "medium" "PASS" "INFO" "Running task ansible:mounts" "reports/mounts/remediation.log"

        local remediation_log="${ARTIFACT_DIR}/reports/mounts/remediation.log"
        mkdir -p "$(dirname "$remediation_log")"

        if (cd "${REPO_ROOT}" && task ansible:mounts) >> "$remediation_log" 2>&1; then
            log_info "Mount remediation completed - re-validating"
            remediation_attempted=1

            # Re-run validation
            if ! run_rebuild_host_mount_checks; then
                record_check "MNT-REMEDIATE-002" "Mount remediation verification" "blocker" "PASS" "FAIL" "Mounts still failing after remediation" "reports/mounts/remediation.log"
                failed=1
            else
                record_check "MNT-REMEDIATE-002" "Mount remediation verification" "medium" "PASS" "PASS" "Mounts fixed by remediation" "reports/mounts/remediation.log"
            fi
        else
            record_check "MNT-REMEDIATE-001" "Mount remediation" "blocker" "PASS" "FAIL" "Ansible mount role failed" "reports/mounts/remediation.log"
            failed=1
        fi
    fi

    # Immich bind mount checks (no auto-remediation, different failure mode)
    log_info "Validating Immich LXC bind mounts..."
    if ! run_rebuild_immich_bind_mount_checks; then
        if [[ $remediation_attempted -eq 1 ]]; then
            log_warn "Immich bind mount check failed after host mount remediation"
            log_warn "This may indicate LXC config issue (not auto-remediatable)"
        fi
        failed=1
    fi

    return $failed
}

rebuild_phase_restore() {
    local evidence_dir="${ARTIFACT_DIR}/reports/restore"
    mkdir -p "$evidence_dir"
    local summary_file="${evidence_dir}/restore-summary.txt"

    if [[ -z "${REBUILD_BACKUP_DIR:-}" ]]; then
        echo "Missing REBUILD_BACKUP_DIR" > "$summary_file"
        record_check "RESTORE-001" "Backup directory available" "blocker" "PASS" "FAIL" "REBUILD_BACKUP_DIR not set" "reports/restore/restore-summary.txt"
        return 1
    fi

    if ! host_exec "test -d '${REBUILD_BACKUP_DIR}'" >/dev/null 2>&1; then
        echo "Backup dir not found: ${REBUILD_BACKUP_DIR}" > "$summary_file"
        record_check "RESTORE-001" "Backup directory available" "blocker" "PASS" "FAIL" "Backup dir missing" "reports/restore/restore-summary.txt"
        return 1
    fi

    record_check "RESTORE-001" "Backup directory available" "blocker" "PASS" "PASS" "Backup dir present" "reports/restore/restore-summary.txt"

    if [[ "${REBUILD_MODE}" == "plan" ]]; then
        echo "Plan-only: restore steps skipped" >> "$summary_file"
        record_check "RESTORE-PLAN" "Restore phase executed" "high" "PASS" "PASS" "Plan-only run" "reports/restore/restore-summary.txt"
        return 0
    fi

    local restore_failed=0

    if host_exec "cp -a /etc/pve/lxc /root/rebuild-lxc-backup-${RUN_ID}" >/dev/null 2>&1; then
        :
    fi

    if host_exec "cp ${REBUILD_BACKUP_DIR}/proxmox/*.conf /etc/pve/lxc/" >> "$summary_file" 2>&1; then
        record_check "RESTORE-002" "LXC config restore" "high" "PASS" "PASS" "LXC configs restored" "reports/restore/restore-summary.txt"
    else
        record_check "RESTORE-002" "LXC config restore" "high" "PASS" "FAIL" "Failed to restore LXC configs" "reports/restore/restore-summary.txt"
        restore_failed=1
    fi

    if host_exec "cp /etc/pve/storage.cfg /root/rebuild-storage-backup-${RUN_ID}.cfg" >/dev/null 2>&1; then
        :
    fi

    if host_exec "cp ${REBUILD_BACKUP_DIR}/proxmox/storage.cfg /etc/pve/storage.cfg" >> "$summary_file" 2>&1; then
        host_exec "systemctl restart pvedaemon pveproxy" >> "$summary_file" 2>&1 || true
        record_check "RESTORE-003" "Storage config restore" "high" "PASS" "PASS" "Storage config restored" "reports/restore/restore-summary.txt"
    else
        record_check "RESTORE-003" "Storage config restore" "high" "PASS" "FAIL" "Failed to restore storage config" "reports/restore/restore-summary.txt"
        restore_failed=1
    fi

    if [[ "${REBUILD_APPLY_NETWORK:-false}" == "true" ]]; then
        if host_exec "cp /etc/network/interfaces /root/rebuild-network-backup-${RUN_ID}.cfg" >/dev/null 2>&1; then
            :
        fi
        if host_exec "cp ${REBUILD_BACKUP_DIR}/network/interfaces /etc/network/interfaces" >> "$summary_file" 2>&1; then
            record_check "RESTORE-004" "Network config restore" "high" "PASS" "PASS" "Network config restored" "reports/restore/restore-summary.txt"
        else
            record_check "RESTORE-004" "Network config restore" "high" "PASS" "FAIL" "Failed to restore network config" "reports/restore/restore-summary.txt"
            restore_failed=1
        fi
    else
        record_check "RESTORE-004" "Network config restore" "high" "PASS" "PASS" "Skipped network restore (REBUILD_APPLY_NETWORK=false)" "reports/restore/restore-summary.txt"
    fi

    if [[ "${REBUILD_APPLY_FSTAB:-false}" == "true" ]]; then
        if host_exec "cp /etc/fstab /root/rebuild-fstab-backup-${RUN_ID}.cfg" >/dev/null 2>&1; then
            :
        fi
        if host_exec "cp ${REBUILD_BACKUP_DIR}/system/fstab /etc/fstab" >> "$summary_file" 2>&1; then
            host_exec "mount -a" >> "$summary_file" 2>&1 || true
            record_check "RESTORE-005" "FSTAB restore" "high" "PASS" "PASS" "FSTAB restored" "reports/restore/restore-summary.txt"
        else
            record_check "RESTORE-005" "FSTAB restore" "high" "PASS" "FAIL" "Failed to restore fstab" "reports/restore/restore-summary.txt"
            restore_failed=1
        fi
    else
        record_check "RESTORE-005" "FSTAB restore" "high" "PASS" "PASS" "Skipped fstab restore (REBUILD_APPLY_FSTAB=false)" "reports/restore/restore-summary.txt"
    fi

    return $restore_failed
}

rebuild_phase_iac() {
    local evidence_dir="${ARTIFACT_DIR}/reports/iac"
    mkdir -p "$evidence_dir"
    local summary_file="${evidence_dir}/iac-summary.txt"
    local iac_dir="${REBUILD_BACKUP_DIR:-}/iac"
    local target_root="${REBUILD_IAC_TARGET:-${REMOTE_REPO_ROOT:-/var/lib/homelab-proxmox}}"

    if [[ -z "${REBUILD_BACKUP_DIR:-}" ]]; then
        echo "Missing REBUILD_BACKUP_DIR" > "$summary_file"
        record_check "IAC-001" "IaC backup directory available" "high" "PASS" "FAIL" "REBUILD_BACKUP_DIR not set" "reports/iac/iac-summary.txt"
        return 1
    fi

    if ! host_exec "test -d '${iac_dir}'" >/dev/null 2>&1; then
        echo "IaC directory not found: ${iac_dir}" > "$summary_file"
        record_check "IAC-001" "IaC backup directory available" "high" "PASS" "FAIL" "IaC dir missing" "reports/iac/iac-summary.txt"
        return 1
    fi

    record_check "IAC-001" "IaC backup directory available" "high" "PASS" "PASS" "IaC dir present" "reports/iac/iac-summary.txt"

    if [[ "${REBUILD_MODE}" == "apply" ]]; then
        if host_exec "rsync -a '${iac_dir}/' '${target_root}/'" >> "$summary_file" 2>&1; then
            record_check "IAC-002" "IaC artifacts restored" "high" "PASS" "PASS" "IaC artifacts restored" "reports/iac/iac-summary.txt"
        else
            record_check "IAC-002" "IaC artifacts restored" "high" "PASS" "FAIL" "IaC restore failed" "reports/iac/iac-summary.txt"
            return 1
        fi
    else
        echo "Plan-only: IaC restore skipped" >> "$summary_file"
        record_check "IAC-002" "IaC artifacts restored" "high" "PASS" "PASS" "Plan-only run" "reports/iac/iac-summary.txt"
    fi

    if command -v task >/dev/null 2>&1; then
        if (cd "${REPO_ROOT}" && task terraform:plan) >> "$summary_file" 2>&1; then
            record_check "IAC-003" "IaC drift check" "high" "PASS" "PASS" "Terraform plan completed" "reports/iac/iac-summary.txt"
        else
            record_check "IAC-003" "IaC drift check" "high" "PASS" "FAIL" "Terraform plan failed" "reports/iac/iac-summary.txt"
            return 1
        fi
    else
        record_check "IAC-003" "IaC drift check" "high" "PASS" "FAIL" "Task CLI not available" "reports/iac/iac-summary.txt"
        return 1
    fi

    return 0
}

rebuild_phase_services() {
    local evidence_dir="${ARTIFACT_DIR}/reports/services"
    mkdir -p "$evidence_dir"

    local allowlist_path="${REBUILD_SERVICE_ALLOWLIST_PATH:-${REPO_ROOT:-}/scripts/lab/service-scope-allowlist.json}"
    if [[ ! -f "$allowlist_path" ]]; then
        record_check "SRV-001" "Service allowlist present" "high" "PASS" "FAIL" "Allowlist missing" "reports/services"
        return 1
    fi
    record_check "SRV-001" "Service allowlist present" "low" "PASS" "PASS" "Allowlist found: $allowlist_path" "reports/services"

    # Source state library for laptop execution
    # shellcheck source=./state.sh
    if [[ -f "${REPO_ROOT}/scripts/lab/lib/state.sh" ]]; then
        source "${REPO_ROOT}/scripts/lab/lib/state.sh"
    else
        record_check "SRV-002" "State library present" "blocker" "PASS" "FAIL" "State library missing: ${REPO_ROOT}/scripts/lab/lib/state.sh" "reports/services"
        return 1
    fi

    # Enable NAS state for laptop execution
    export USE_NAS_STATE=true
    export ENVIRONMENT="${REBUILD_ENVIRONMENT}"

    # Verify state access before starting
    if ! verify_state_access; then
        record_check "SRV-003" "State storage accessible" "blocker" "PASS" "FAIL" "Cannot write to NAS state: $(resolve_state_root 2>&1)" "reports/services"
        return 1
    fi
    record_check "SRV-003" "State storage accessible" "low" "PASS" "PASS" "NAS state verified: $(resolve_state_root)" "reports/services"

    # Load Proxmox API credentials for Terraform provider
    # These must be set by operator before running rebuild with services phase
    export TF_VAR_proxmox_api_url="${PROXMOX_API_URL:-https://192.168.1.112:8006/api2/json}"
    if [[ -z "${PROXMOX_API_TOKEN_ID:-}" ]]; then
        record_check "SRV-004" "Proxmox API credentials" "blocker" "PASS" "FAIL" "PROXMOX_API_TOKEN_ID not set" "reports/services"
        log_error "PROXMOX_API_TOKEN_ID required for Terraform provider"
        log_error "Example: export PROXMOX_API_TOKEN_ID='root@pam!rebuild'"
        return 1
    fi
    if [[ -z "${PROXMOX_API_TOKEN_SECRET:-}" ]]; then
        record_check "SRV-004" "Proxmox API credentials" "blocker" "PASS" "FAIL" "PROXMOX_API_TOKEN_SECRET not set" "reports/services"
        log_error "PROXMOX_API_TOKEN_SECRET required for Terraform provider"
        return 1
    fi
    export TF_VAR_proxmox_api_token_id="${PROXMOX_API_TOKEN_ID}"
    export TF_VAR_proxmox_api_token_secret="${PROXMOX_API_TOKEN_SECRET}"
    record_check "SRV-004" "Proxmox API credentials" "low" "PASS" "PASS" "Credentials loaded (token_id: ${PROXMOX_API_TOKEN_ID})" "reports/services"

    local env_tfvars="${REPO_ROOT}/terraform/environments/${REBUILD_ENVIRONMENT}.tfvars"
    if [[ ! -f "${env_tfvars}" ]]; then
        record_check "SRV-005" "Environment tfvars present" "high" "PASS" "FAIL" "Missing tfvars file: ${env_tfvars}" "reports/services"
        log_error "Missing required tfvars file: ${env_tfvars}"
        log_error "Create it from example: terraform/environments/${REBUILD_ENVIRONMENT}.tfvars.example"
        return 1
    fi
    record_check "SRV-005" "Environment tfvars present" "low" "PASS" "PASS" "Using tfvars: ${env_tfvars}" "reports/services"

    local -a services
    mapfile -t services < <(jq -r 'keys[]' "$allowlist_path")
    local failed=0
    local idx=5  # Start after SRV-005

    for service in "${services[@]}"; do
        idx=$((idx + 1))
        local check_id
        check_id="SRV-$(printf '%03d' "$idx")"
        local log_file="${evidence_dir}/${service}.log"

        local tf_dir="${REPO_ROOT}/terraform/services/${service}"
        if [[ ! -d "$tf_dir" ]]; then
            record_check "$check_id" "Service ${service} directory" "low" "PASS" "PASS" "Service ${service} not Terraform-managed; skipping" "reports/services/${service}.log"
            continue
        fi

        # Get state file path using state library
        local state_file
        if ! state_file="$(get_service_state_path "$service")"; then
            record_check "$check_id" "Service ${service} state path" "high" "PASS" "FAIL" "State path resolution failed" "reports/services/${service}.log"
            failed=1
            continue
        fi

        mkdir -p "$(dirname "$state_file")"

        # Execute Terraform from laptop
        log_info "Processing service: ${service} (mode: ${REBUILD_MODE})"

        local tf_exit_code=0
        (
            cd "$tf_dir" || exit 1

            # Initialize
            if ! terraform init -input=false -no-color >> "$log_file" 2>&1; then
                echo "ERROR: Terraform init failed for $service" >> "$log_file"
                exit 1
            fi

            # Plan or Apply
            if [[ "${REBUILD_MODE}" == "plan" ]]; then
                terraform plan -var-file="$env_tfvars" -state="$state_file" -input=false -no-color >> "$log_file" 2>&1
            else
                # Apply mode requires confirmation (already validated in preflight)
                terraform apply -var-file="$env_tfvars" -state="$state_file" -input=false -auto-approve -no-color >> "$log_file" 2>&1
            fi
        ) || tf_exit_code=$?

        if [[ $tf_exit_code -eq 0 ]]; then
            record_check "$check_id" "Service rebuild (${service})" "high" "PASS" "PASS" "Service ${service} ${REBUILD_MODE} succeeded" "reports/services/${service}.log"
        else
            record_check "$check_id" "Service rebuild (${service})" "high" "PASS" "FAIL" "Service ${service} ${REBUILD_MODE} failed (see logs)" "reports/services/${service}.log"
            failed=1
        fi
    done

    return $failed
}

rebuild_phase_verify() {
    local evidence_dir="${ARTIFACT_DIR}/reports/verify"
    mkdir -p "$evidence_dir"
    local summary_file="${evidence_dir}/verify-summary.txt"

    if command -v task >/dev/null 2>&1; then
        {
            echo "Running inventory update (best effort)..."
            if (cd "${REPO_ROOT}" && task inventory:update); then
                echo "inventory:update succeeded"
            else
                echo "inventory:update failed; continuing with health checks"
            fi
            echo
            echo "Running health checks..."
            (cd "${REPO_ROOT}" && task healthcheck:run)
        } > "$summary_file" 2>&1

        if [[ $? -eq 0 ]]; then
            record_check "VERIFY-001" "Lifecycle verification" "high" "PASS" "PASS" "Health checks succeeded" "reports/verify/verify-summary.txt"
            return 0
        fi
    fi

    record_check "VERIFY-001" "Lifecycle verification" "high" "PASS" "FAIL" "Lifecycle verify failed" "reports/verify/verify-summary.txt"
    return 1
}

cmd_idempotent_rebuild() {
    local environment=""
    local mode="plan"
    local confirm=""
    local -a selected_phases=()

    if ! run_dependency_preflight; then
        log_error "Dependency preflight failed; install missing tools before rebuild."
        exit 1
    fi

    if ! load_rebuild_config; then
        exit 1
    fi

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --mode)
                mode="${2:-plan}"
                shift 2
                ;;
            --apply)
                mode="apply"
                shift
                ;;
            --environment)
                environment="${2:-}"
                shift 2
                ;;
            --confirm)
                confirm="${2:-}"
                shift 2
                ;;
            --phase)
                selected_phases+=("${2:-}")
                shift 2
                ;;
            --phases)
                IFS=',' read -r -a selected_phases <<< "${2:-}"
                shift 2
                ;;
            --backup-dir)
                REBUILD_BACKUP_DIR="${2:-}"
                shift 2
                ;;
            --remote-repo-root)
                REMOTE_REPO_ROOT="${2:-}"
                shift 2
                ;;
            --iac-target)
                REBUILD_IAC_TARGET="${2:-}"
                shift 2
                ;;
            --apply-network)
                REBUILD_APPLY_NETWORK="true"
                shift
                ;;
            --apply-fstab)
                REBUILD_APPLY_FSTAB="true"
                shift
                ;;
            *)
                log_error "Unknown option: $1"
                exit 1
                ;;
        esac
    done

    if [[ -z "$environment" ]]; then
        environment="$REBUILD_DEFAULT_ENVIRONMENT"
    fi

    if [[ "$mode" != "plan" && "$mode" != "apply" ]]; then
        log_error "Invalid mode: $mode"
        exit 1
    fi

    # Validate required arguments based on selected phases
    local -a phases_to_run=()
    if [[ ${#selected_phases[@]} -eq 0 ]]; then
        # No phases specified, all phases will run
        phases_to_run=("${REBUILD_PHASES[@]}")
    else
        # Only selected phases will run
        for phase in "${REBUILD_PHASES[@]}"; do
            if rebuild_should_run_phase "$phase" "${selected_phases[@]}"; then
                phases_to_run+=("$phase")
            fi
        done
    fi

    # Check if restore or iac phases will run - they require --backup-dir
    local needs_backup_dir=0
    for phase in "${phases_to_run[@]}"; do
        if [[ "$phase" == "restore" || "$phase" == "iac" ]]; then
            needs_backup_dir=1
            break
        fi
    done

    if [[ $needs_backup_dir -eq 1 && -z "${REBUILD_BACKUP_DIR:-}" ]]; then
        log_error "The restore and iac phases require --backup-dir argument"
        log_error ""
        log_error "Usage: task rebuild:plan -- --backup-dir /path/to/backup"
        log_error "   Or: task rebuild:plan -- --phase mounts  # Skip phases that need backup"
        log_error ""
        log_error "Selected phases: ${phases_to_run[*]}"
        exit 1
    fi

    init_rebuild_artifacts
    if ! ensure_artifact_root; then
        log_error "Artifact root missing or not writable: ${ARTIFACT_ROOT}"
        exit 1
    fi

    export RUN_ID_PREFIX="rebuild"
    local base_dir
    base_dir="$(artifact_runs_path)"
    mkdir -p "$base_dir"
    local run_id
    run_id="$(create_evidence_pack "$base_dir")"
    export RUN_ID="$run_id"
    export ARTIFACT_DIR="${base_dir}/${run_id}"
    export EVIDENCE_ROOT="$ARTIFACT_DIR"
    export REBUILD_MODE="$mode"
    export REBUILD_ENVIRONMENT="$environment"
    export REBUILD_CONFIRM="$confirm"

    mkdir -p "${ARTIFACT_DIR}/reports"

    rebuild_state_init "$run_id" "$environment" "$mode" "${REBUILD_PHASES[@]}"
    rebuild_state_set_status "running"

    local preflight_file="${ARTIFACT_DIR}/reports/preflight-summary.txt"
    rebuild_write_preflight_summary "$preflight_file" "$environment" "$mode" "$confirm" "${REBUILD_PHASES[@]}"

    export CURRENT_SOURCE="rebuild"
    export CURRENT_PHASE="preflight"

    if [[ "$environment" == "prod" && "$confirm" != "$REBUILD_PROD_CONFIRM_STRING" ]]; then
        record_check "SAFE-001" "Prod confirmation provided" "blocker" "PASS" "FAIL" "Missing prod confirm string" "reports/preflight-summary.txt"
        rebuild_state_set_status "failed"
        serialize_checks "${ARTIFACT_DIR}/checks.json"
        rebuild_write_evidence_index
        return 1
    fi

    if [[ "$mode" == "apply" && -z "$confirm" ]]; then
        record_check "SAFE-002" "Apply confirmation provided" "blocker" "PASS" "FAIL" "Missing confirm string for apply" "reports/preflight-summary.txt"
        rebuild_state_set_status "failed"
        serialize_checks "${ARTIFACT_DIR}/checks.json"
        rebuild_write_evidence_index
        return 1
    fi

    record_check "SAFE-001" "Prod confirmation provided" "blocker" "PASS" "PASS" "Safety checks satisfied" "reports/preflight-summary.txt"

    local failed=0
    for phase in "${REBUILD_PHASES[@]}"; do
        if ! rebuild_should_run_phase "$phase" "${selected_phases[@]}"; then
            continue
        fi

        export CURRENT_PHASE="$phase"
        rebuild_state_update_phase "$phase" "running"

        case "$phase" in
            mounts)
                if ! rebuild_phase_mounts; then
                    rebuild_state_update_phase "$phase" "failed" "Mount validation failed"
                    log_error "Mount validation failed. See ${ARTIFACT_DIR}/reports/mounts"
                    failed=1
                else
                    rebuild_state_update_phase "$phase" "completed"
                fi
                ;;
            restore)
                if ! rebuild_phase_restore; then
                    rebuild_state_update_phase "$phase" "failed" "Restore phase failed"
                    log_error "Restore phase failed. See ${ARTIFACT_DIR}/reports/restore/restore-summary.txt"
                    failed=1
                else
                    rebuild_state_update_phase "$phase" "completed"
                fi
                ;;
            iac)
                if ! rebuild_phase_iac; then
                    rebuild_state_update_phase "$phase" "failed" "IaC phase failed"
                    log_error "IaC phase failed. See ${ARTIFACT_DIR}/reports/iac/iac-summary.txt"
                    failed=1
                else
                    rebuild_state_update_phase "$phase" "completed"
                fi
                ;;
            services)
                if ! rebuild_phase_services; then
                    rebuild_state_update_phase "$phase" "failed" "Services phase failed"
                    log_error "Services phase failed. See ${ARTIFACT_DIR}/reports/services"
                    failed=1
                else
                    rebuild_state_update_phase "$phase" "completed"
                fi
                ;;
            verify)
                if ! rebuild_phase_verify; then
                    rebuild_state_update_phase "$phase" "failed" "Verify phase failed"
                    log_error "Verify phase failed. See ${ARTIFACT_DIR}/reports/verify/verify-summary.txt"
                    failed=1
                else
                    rebuild_state_update_phase "$phase" "completed"
                fi
                ;;
            *)
                log_warn "Unknown phase: $phase"
                ;;
        esac
    done

    if [[ $failed -eq 0 ]]; then
        rebuild_state_set_status "completed"
    else
        rebuild_state_set_status "failed"
    fi

    serialize_checks "${ARTIFACT_DIR}/checks.json"
    if command -v render_rebuild_phase_summary >/dev/null 2>&1; then
        render_rebuild_phase_summary "${ARTIFACT_DIR}/state.json" "${ARTIFACT_DIR}/reports/rebuild-phase-summary.md"
    fi
    rebuild_write_evidence_index

    if [[ $failed -ne 0 ]]; then
        log_error "Rebuild failed. Evidence: ${ARTIFACT_DIR}"
        log_error "Checks: ${ARTIFACT_DIR}/checks.json"
        log_error "Phase summary: ${ARTIFACT_DIR}/reports/rebuild-phase-summary.md"
    fi

    [[ $failed -eq 0 ]] && return 0 || return 1
}
