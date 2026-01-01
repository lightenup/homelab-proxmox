#!/bin/bash
# scripts/lab/lib/rebuild.sh
# Rebuild Orchestrator Library (019f)

cmd_rebuild() {
    local profile="rebuild-hypervisor-nested-workload"
    local apply=false
    local dry_run=true
    local keep=false
    local no_verify=false
    local start_time_epoch
    local start_time_iso

    start_time_epoch="$(date +%s)"
    start_time_iso="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --profile) profile="$2"; shift 2 ;;
            --apply) apply=true; dry_run=false; shift ;;
            --dry-run) dry_run=true; apply=false; shift ;;
            --keep) keep=true; shift ;;
            --verify) no_verify=false; shift ;;
            --no-verify) no_verify=true; shift ;;
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
    run_id="$(create_evidence_pack "artifacts/019-lab")"
    export RUN_ID="$run_id"
    export ARTIFACT_DIR="artifacts/019-lab/${run_id}"
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
    
    if cmd_run --profile "$SUITE_PROFILE" $([[ "$keep" == "true" ]] && echo "--keep") $([[ "$no_verify" == "true" ]] && echo "--no-verify" || echo "--verify"); then
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

    # --- Feature 020: Deterministic teardown helpers (VM/LXC) ---

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
        output=$(ssh $SSH_OPTS "$SSH_USER@$PROXMOX_HOST" "$remote_cmd" 2>&1)
        local rc=$?
        append_teardown_log "$evidence_file" "$label" "$remote_cmd" "$rc" "$output"
        return $rc
    }

    teardown_vm_with_retries() {
        local vmid="$1"
        local evidence_file="${EVIDENCE_ROOT}/reports/cleanup/teardown-vm-${vmid}.txt"
        mkdir -p "$(dirname "$evidence_file")"

        local exists=true
        if ! ssh $SSH_OPTS "$SSH_USER@$PROXMOX_HOST" "qm status $vmid" >/dev/null 2>&1; then
            exists=false
            append_teardown_log "$evidence_file" "vm-$vmid" "qm status $vmid" "1" "VM $vmid not found"
        fi

        local attempts=0
        local success=false
        local last_rc=0

        while [[ $attempts -lt 3 && "$exists" == "true" ]]; do
            attempts=$((attempts + 1))

            run_teardown_cmd "$evidence_file" "vm-$vmid stop attempt $attempts" "qm stop $vmid --skiplock"

            # Wait for not-running state (best-effort)
            for _ in {1..5}; do
                if ssh $SSH_OPTS "$SSH_USER@$PROXMOX_HOST" "qm status $vmid" 2>/dev/null | grep -q "status: running"; then
                    sleep 2
                else
                    break
                fi
            done

            run_teardown_cmd "$evidence_file" "vm-$vmid destroy attempt $attempts" "qm destroy $vmid --purge"
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
        if ! ssh $SSH_OPTS "$SSH_USER@$PROXMOX_HOST" "pct status $ctid" >/dev/null 2>&1; then
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
                if ssh $SSH_OPTS "$SSH_USER@$PROXMOX_HOST" "pct status $ctid" 2>/dev/null | grep -q "status: running"; then
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
    local ssh_target="${SSH_USER}@${PROXMOX_HOST}"
    local failed=0

    # HOST-001: SSH
    local ssh_output
    local ssh_evidence="${ARTIFACT_DIR}/reports/host/HOST-001-ssh.txt"
    if ssh_output=$(ssh $SSH_OPTS "$ssh_target" "echo pong" 2>&1); then
        echo "$ssh_output" > "$ssh_evidence"
        record_check "HOST-001" "Proxmox host reachable via SSH" "blocker" "PASS" "PASS" "SSH connection successful" "reports/host/HOST-001-ssh.txt"
    else
        echo "$ssh_output" > "$ssh_evidence"
        record_check "HOST-001" "Proxmox host reachable via SSH" "blocker" "PASS" "FAIL" "SSH connection failed" "reports/host/HOST-001-ssh.txt"
        return 1
    fi

    # HOST-002: Bridge
    local bridge_check
    bridge_check=$(ssh $SSH_OPTS "$ssh_target" "ip addr show $LAB_BRIDGE" 2>&1)
    echo "$bridge_check" > "${ARTIFACT_DIR}/reports/host/HOST-002-bridge.txt"
    
    if echo "$bridge_check" | grep -q "$LAB_GATEWAY"; then
        record_check "HOST-002" "Required bridge exists and has expected gateway IP" "blocker" "PASS" "PASS" "Bridge $LAB_BRIDGE has IP $LAB_GATEWAY" "reports/host/HOST-002-bridge.txt"
    else
        record_check "HOST-002" "Required bridge exists and has expected gateway IP" "blocker" "PASS" "FAIL" "Bridge $LAB_BRIDGE missing or wrong IP" "reports/host/HOST-002-bridge.txt"
        failed=1
    fi

    # HOST-003: Storage
    local storage_check
    storage_check=$(ssh $SSH_OPTS "$ssh_target" "pvesm status" 2>&1)
    echo "$storage_check" > "${ARTIFACT_DIR}/reports/host/HOST-003-storage.txt"
    
    if echo "$storage_check" | grep -q "local-lvm"; then
        record_check "HOST-003" "Required storage backend exists" "blocker" "PASS" "PASS" "Storage local-lvm found" "reports/host/HOST-003-storage.txt"
    else
        record_check "HOST-003" "Required storage backend exists" "blocker" "PASS" "FAIL" "Storage local-lvm missing" "reports/host/HOST-003-storage.txt"
        failed=1
    fi

    # HOST-004: Nested
    local nested_check
    nested_check=$(ssh $SSH_OPTS "$ssh_target" "cat /sys/module/kvm_intel/parameters/nested 2>/dev/null || cat /sys/module/kvm_amd/parameters/nested 2>/dev/null")
    echo "$nested_check" > "${ARTIFACT_DIR}/reports/host/HOST-004-nested.txt"
    
    if [[ "$nested_check" == "Y" || "$nested_check" == "1" ]]; then
        record_check "HOST-004" "Host nested virtualization enabled" "high" "PASS" "PASS" "Nested virtualization enabled ($nested_check)" "reports/host/HOST-004-nested.txt"
    else
        record_check "HOST-004" "Host nested virtualization enabled" "high" "PASS" "FAIL" "Nested virtualization disabled ($nested_check)" "reports/host/HOST-004-nested.txt"
    fi

    return $failed
}

run_baseline_template_checks() {
    local ssh_target="${SSH_USER}@${PROXMOX_HOST}"
    local failed=0

    # TPL-001: Base Template
    local tpl1_status
    tpl1_status=$(ssh $SSH_OPTS "$ssh_target" "qm status $LAB_TEMPLATE_VMID" 2>&1)
    echo "$tpl1_status" > "${ARTIFACT_DIR}/reports/templates/TPL-001-qm-status-${LAB_TEMPLATE_VMID}.txt"
    
    if echo "$tpl1_status" | grep -q "status:"; then
        record_check "TPL-001" "Base template exists (VMID $LAB_TEMPLATE_VMID)" "blocker" "PASS" "PASS" "Template found" "reports/templates/TPL-001-qm-status-${LAB_TEMPLATE_VMID}.txt"
    else
        record_check "TPL-001" "Base template exists (VMID $LAB_TEMPLATE_VMID)" "blocker" "PASS" "FAIL" "Template missing" "reports/templates/TPL-001-qm-status-${LAB_TEMPLATE_VMID}.txt"
        failed=1
    fi

    # TPL-002: Tier2 Template
    local tpl2_status
    tpl2_status=$(ssh $SSH_OPTS "$ssh_target" "qm status $LAB_TEMPLATE_VMID_TIER2" 2>&1)
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
        config=$(ssh $SSH_OPTS "$ssh_target" "qm config $vmid" 2>&1)
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
        config=$(ssh $SSH_OPTS "$ssh_target" "qm config $vmid" 2>&1)
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
        config=$(ssh $SSH_OPTS "$ssh_target" "qm config $vmid" 2>&1)
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
        config=$(ssh $SSH_OPTS "$ssh_target" "qm config $vmid" 2>&1)
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
    local ssh_target="${SSH_USER}@${PROXMOX_HOST}"
    local rem_log="${ARTIFACT_DIR}/logs/remediation-templates.log"
    
    log_info "Remediating templates..."
    emit_event "remediation_start" "$RUN_ID" "scope=templates" "target_host=$ssh_target"
    mkdir -p "${ARTIFACT_DIR}/logs"
    : > "$rem_log"

    # Helper to destroy if exists
    destroy_if_exists() {
        local vmid="$1"
        if ssh $SSH_OPTS "$ssh_target" "qm status $vmid" >/dev/null 2>&1; then
            log_info "Destroying existing template $vmid..."
            emit_event "remediation_step" "$RUN_ID" "action=destroy" "vmid=$vmid"
            # Purge to remove disk images too
            if ! ssh $SSH_OPTS "$ssh_target" "qm destroy $vmid --purge" >>"$rem_log" 2>&1; then
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
