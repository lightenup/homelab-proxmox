#!/usr/bin/env bash
set -euo pipefail

# tfvars provisioning helpers
#
# Primary entrypoint:
#   _tfvars_provision_and_write_proof <reports_dir> <tfvars_dir> <environment>
#
# Design constraints:
# - Never log secrets
# - Write redacted proof under <reports_dir>/<environment>-tfvars/
# - Enforce token ID: terraform@pve!terraform-token

_tfvars_now_utc() {
	if command -v date >/dev/null 2>&1; then
		date -u +"%Y-%m-%dT%H:%M:%SZ"
		return 0
	fi
	echo "1970-01-01T00:00:00Z"
}

_tfvars_sha256() {
	local file_path="$1"
	if command -v sha256sum >/dev/null 2>&1; then
		sha256sum "${file_path}" | awk '{print $1}' | tr '[:upper:]' '[:lower:]'
		return 0
	fi
	if command -v shasum >/dev/null 2>&1; then
		shasum -a 256 "${file_path}" | awk '{print $1}' | tr '[:upper:]' '[:lower:]'
		return 0
	fi
	if command -v openssl >/dev/null 2>&1; then
		# Output format: "SHA2-256(file)= <hash>"
		openssl dgst -sha256 "${file_path}" | awk '{print $NF}' | tr '[:upper:]' '[:lower:]'
		return 0
	fi
	return 1
}

_tfvars_escape_hcl_string() {
	local s="$1"
	s="${s//\\/\\\\}"
	s="${s//\"/\\\"}"
	printf '%s' "${s}"
}

_tfvars_write_validation_json() {
	local out_path="$1"
	local timestamp="$2"
	local template_source="$3"
	local rendered_path="$4"
	local validation_status="$5"
	local token_id="$6"
	local secret_present="$7"   # true|false
	local file_hash="$8"
	local errors_json_array="$9" # JSON array string
	local drift_results_json="${10:-}"  # JSON object string or ""
	local change_warnings_json="${11:-}" # JSON array string or ""

	local ts_esc src_esc rp_esc
	ts_esc="$(_tfvars_escape_hcl_string "${timestamp}")"
	src_esc="$(_tfvars_escape_hcl_string "${template_source}")"
	rp_esc="$(_tfvars_escape_hcl_string "${rendered_path}")"

	local drift_line=""
	if [[ -n "${drift_results_json}" ]]; then
		drift_line="  \"drift_results\": ${drift_results_json},"$'\n'
	else
		drift_line="  \"drift_results\": {},"$'\n'
	fi

	local warnings_line=""
	if [[ -n "${change_warnings_json}" ]]; then
		warnings_line="  \"change_warnings\": ${change_warnings_json}"$'\n'
	else
		warnings_line="  \"change_warnings\": []"$'\n'
	fi

	cat >"${out_path}" <<EOF
{
  "timestamp": "${ts_esc}",
  "template_source": "${src_esc}",
  "rendered_path": "${rp_esc}",
  "validation_status": "${validation_status}",
  "token_id": "${token_id}",
  "secret_present": ${secret_present},
  "file_hash": "${file_hash}",
  "validation_errors": ${errors_json_array},
${drift_line}${warnings_line}}
EOF
}

# Extract top-level HCL key names from a tfvars file.
# Outputs one key name per line (no duplicates).
_tfvars_extract_top_level_keys() {
	local file_path="$1"
	grep -E '^[[:space:]]*[a-zA-Z_][a-zA-Z0-9_]*[[:space:]]*=' "${file_path}" 2>/dev/null \
		| grep -v '^[[:space:]]*#' \
		| awk -F'[[:space:]]*=' '{gsub(/^[[:space:]]+/, "", $1); print $1}' \
		| sort -u
}

_tfvars_provision_and_write_proof() {
	local reports_dir="$1"
	local tfvars_dir="$2"
	local environment="$3"

	local required_token_id="terraform@pve!terraform-token"
	local rendered_path="${tfvars_dir%/}/${environment}.tfvars"
	local evidence_subdir="${environment}-tfvars"

	mkdir -p "${reports_dir%/}/${evidence_subdir}" "${tfvars_dir%/}"

	local timestamp
	timestamp="$(_tfvars_now_utc)"

	# Secret passed by GitHub Actions (preferred). Back-compat supports PROXMOX_TOKEN_SECRET.
	# If neither is present, we will attempt to reuse an existing rendered tfvars
	# (common when secrets are managed locally on PVE).
	local token_secret="${PROXMOX_API_TOKEN_SECRET:-${PROXMOX_TOKEN_SECRET:-}}"
	local secret_source=""
	if [[ -n "${PROXMOX_API_TOKEN_SECRET:-}" ]]; then
		secret_source="PROXMOX_API_TOKEN_SECRET"
	elif [[ -n "${PROXMOX_TOKEN_SECRET:-}" ]]; then
		secret_source="PROXMOX_TOKEN_SECRET"
	else
		secret_source="(missing)"
	fi

	# Choose a template source (non-secret). Prefer explicit override.
	local template_path="${PROD_TFVARS_TEMPLATE:-}"
	local template_source=""
	if [[ -n "${template_path}" ]]; then
		if [[ ! -f "${template_path}" ]]; then
			template_path=""
		else
			template_source="file:${template_path}"
		fi
	fi

	if [[ -z "${template_path}" ]]; then
		local repo_root="${REPO_ROOT:-}"
		local candidates=()
		if [[ -n "${repo_root}" ]]; then
			candidates+=("${repo_root}/terraform/environments/${environment}.tfvars.template")
			candidates+=("${repo_root}/terraform/environments/${environment}.tfvars.example")
		fi

		local c
		for c in "${candidates[@]}"; do
			if [[ -f "${c}" ]]; then
				template_path="${c}"
				template_source="file:${c}"
				break
			fi
		done
	fi

	# If no token secret is available, prefer validating an existing rendered tfvars
	# (so we don't overwrite a locally-managed secret with an empty value). This also
	# satisfies the "template" requirement when no repo template exists.
	if [[ -z "${token_secret}" && -f "${rendered_path}" ]]; then
		template_path="${rendered_path}"
		template_source="file:${rendered_path}"
		secret_source="existing_file"
	fi

	if [[ -z "${template_path}" ]]; then
		# No template -> fail early, but still write proof artifacts.
		local errors_json="[\"Missing ${environment}.tfvars template (set PROD_TFVARS_TEMPLATE or ensure terraform/environments/${environment}.tfvars.example exists)\"]"
		_tfvars_write_validation_json \
			"${reports_dir%/}/${evidence_subdir}/validation.json" \
			"${timestamp}" \
			"missing" \
			"${rendered_path}" \
			"fail" \
			"${required_token_id}" \
			"false" \
			"0000000000000000000000000000000000000000000000000000000000000000" \
			"${errors_json}" \
			"" \
			""
		{
			echo "timestamp=${timestamp}"
			echo "template_source=missing"
			echo "rendered_path=${rendered_path}"
			echo "validation_status=fail"
			echo "token_id=${required_token_id}"
			echo "secret_present=false"
			echo "secret_source=${secret_source}"
			echo "file_hash=0000000000000000000000000000000000000000000000000000000000000000"
			echo "error=missing template"
		} >"${reports_dir%/}/${evidence_subdir}/provisioning.txt"
		echo "0000000000000000000000000000000000000000000000000000000000000000" >"${reports_dir%/}/${evidence_subdir}/${environment}.tfvars.sha256"
		return 1
	fi

	# Render to a temp file; only move into place if validation passes.
	umask 077
	local tmp
	tmp="$(mktemp -t "${environment}.tfvars.XXXXXX")"
	trap 'rm -f "${tmp}" 2>/dev/null || true' RETURN

	# Start from template and enforce token_id + secret.
	# Note: we intentionally do not echo any content that includes secrets.
	cp "${template_path}" "${tmp}"

	# Ensure required token id value is present.
	if grep -Eq '^[[:space:]]*proxmox_api_token_id[[:space:]]*=' "${tmp}"; then
		sed -i.bak -E "s|^[[:space:]]*proxmox_api_token_id[[:space:]]*=.*$|proxmox_api_token_id     = \"${required_token_id}\"|" "${tmp}" 2>/dev/null || true
		rm -f "${tmp}.bak" 2>/dev/null || true
	else
		printf '\nproxmox_api_token_id     = "%s"\n' "${required_token_id}" >>"${tmp}"
	fi

	# Inject secret via sentinel replacement. Skip comment lines to preserve
	# any documentation examples of the sentinel marker in comments.
	if [[ -n "${token_secret}" ]]; then
		local secret_escaped
		secret_escaped="$(_tfvars_escape_hcl_string "${token_secret}")"
		sed -i.bak '/^[[:space:]]*#/! s|__INJECT_TOKEN_SECRET__|'"${secret_escaped}"'|g' "${tmp}" 2>/dev/null || true
		rm -f "${tmp}.bak" 2>/dev/null || true
	fi

	# Post-injection sentinel validation: scan non-comment lines for any remaining
	# __INJECT_*__ markers. Fail if any are found (means secret was not provided).
	local -a errors=()
	local remaining_sentinels
	remaining_sentinels="$(grep -v '^[[:space:]]*#' "${tmp}" 2>/dev/null | grep -oE '__INJECT_[A-Z_]+__' | sort -u || true)"
	if [[ -n "${remaining_sentinels}" ]]; then
		while IFS= read -r sentinel; do
			if [[ -n "${sentinel}" ]]; then
				errors+=("Un-injected sentinel: ${sentinel} (source: PROXMOX_API_TOKEN_SECRET not set)")
			fi
		done <<<"${remaining_sentinels}"
	fi

	local token_id_in_file=""
	token_id_in_file="$(awk -F'"' '/^[[:space:]]*proxmox_api_token_id[[:space:]]*=/ {print $2; exit}' "${tmp}" 2>/dev/null || true)"
	if [[ "${token_id_in_file}" != "${required_token_id}" ]]; then
		errors+=("Invalid token_id: expected '${required_token_id}', got '${token_id_in_file}'")
	fi

	# Validate secret presence without leaking it. If no env secret is present,
	# validate the existing secret value in the file (if any).
	local secret_in_file=""
	secret_in_file="$(awk -F'"' '/^[[:space:]]*proxmox_api_token_secret[[:space:]]*=/ {print $2; exit}' "${tmp}" 2>/dev/null || true)"
	local secret_value_for_validation="${token_secret}"
	if [[ -z "${secret_value_for_validation}" ]]; then
		secret_value_for_validation="${secret_in_file}"
	fi

	local secret_present="true"
	if [[ -z "${secret_value_for_validation}" ]]; then
		secret_present="false"
		errors+=("Secret is empty")
	else
		case "${secret_value_for_validation}" in
			REDACTED|redacted|CHANGEME|changeme|PLACEHOLDER|placeholder)
				secret_present="false"
				errors+=("Secret is placeholder")
				;;
		esac
	fi

	local file_hash="0000000000000000000000000000000000000000000000000000000000000000"
	if _tfvars_sha256 "${tmp}" >/dev/null 2>&1; then
		file_hash="$(_tfvars_sha256 "${tmp}" || echo "${file_hash}")"
	fi

	# Key-set drift detection: compare top-level keys between template and existing rendered file.
	local drift_results_json=""
	if [[ -f "${rendered_path}" ]]; then
		local template_keys
		template_keys="$(_tfvars_extract_top_level_keys "${tmp}")"
		local rendered_keys
		rendered_keys="$(_tfvars_extract_top_level_keys "${rendered_path}")"

		local -a provisioning_gaps=()
		local -a manual_additions=()

		# Keys in template missing from rendered (provisioning gaps)
		local key
		while IFS= read -r key; do
			if [[ -n "${key}" ]] && ! grep -qxF "${key}" <<<"${rendered_keys}"; then
				provisioning_gaps+=("${key}")
			fi
		done <<<"${template_keys}"

		# Keys in rendered missing from template (manual additions)
		while IFS= read -r key; do
			if [[ -n "${key}" ]] && ! grep -qxF "${key}" <<<"${template_keys}"; then
				manual_additions+=("${key}")
			fi
		done <<<"${rendered_keys}"

		# Build JSON arrays
		local gaps_json='[]'
		if [[ ${#provisioning_gaps[@]} -gt 0 ]]; then
			gaps_json='['
			local i
			for i in "${!provisioning_gaps[@]}"; do
				local g_esc
				g_esc="$(_tfvars_escape_hcl_string "${provisioning_gaps[$i]}")"
				if [[ $i -gt 0 ]]; then gaps_json+=','; fi
				gaps_json+="\"${g_esc}\""
			done
			gaps_json+=']'
		fi

		local additions_json='[]'
		if [[ ${#manual_additions[@]} -gt 0 ]]; then
			additions_json='['
			local j
			for j in "${!manual_additions[@]}"; do
				local a_esc
				a_esc="$(_tfvars_escape_hcl_string "${manual_additions[$j]}")"
				if [[ $j -gt 0 ]]; then additions_json+=','; fi
				additions_json+="\"${a_esc}\""
			done
			additions_json+=']'
		fi

		drift_results_json="{\"provisioning_gaps\":${gaps_json},\"manual_additions\":${additions_json}}"
	fi

	# Non-secret value change warnings: compare simple key="value" pairs between
	# existing rendered file and temp (post-injection). Skip secret key.
	local change_warnings_json='[]'
	local -a provisioning_txt_warnings=()
	if [[ -f "${rendered_path}" ]]; then
		# Extract simple single-line string assignments: key = "value"
		local -A rendered_vals=()
		local -A template_vals=()

		local kv_line kv_key kv_val
		while IFS= read -r kv_line; do
			kv_key="$(echo "${kv_line}" | awk -F'[[:space:]]*=[[:space:]]*' '{gsub(/^[[:space:]]+|[[:space:]]+$/, "", $1); print $1}')"
			kv_val="$(echo "${kv_line}" | sed -n 's/^[^"]*"\([^"]*\)"[[:space:]]*$/\1/p')"
			if [[ -n "${kv_key}" && -n "${kv_val}" && "${kv_key}" != "proxmox_api_token_secret" ]]; then
				rendered_vals["${kv_key}"]="${kv_val}"
			fi
		done < <(grep -E '^[[:space:]]*[a-zA-Z_][a-zA-Z0-9_]*[[:space:]]*=[[:space:]]*"[^"]*"[[:space:]]*$' "${rendered_path}" 2>/dev/null | grep -v '^[[:space:]]*#' || true)

		while IFS= read -r kv_line; do
			kv_key="$(echo "${kv_line}" | awk -F'[[:space:]]*=[[:space:]]*' '{gsub(/^[[:space:]]+|[[:space:]]+$/, "", $1); print $1}')"
			kv_val="$(echo "${kv_line}" | sed -n 's/^[^"]*"\([^"]*\)"[[:space:]]*$/\1/p')"
			if [[ -n "${kv_key}" && -n "${kv_val}" && "${kv_key}" != "proxmox_api_token_secret" ]]; then
				template_vals["${kv_key}"]="${kv_val}"
			fi
		done < <(grep -E '^[[:space:]]*[a-zA-Z_][a-zA-Z0-9_]*[[:space:]]*=[[:space:]]*"[^"]*"[[:space:]]*$' "${tmp}" 2>/dev/null | grep -v '^[[:space:]]*#' || true)

		local warn_key
		local -a warnings_arr=()
		for warn_key in "${!template_vals[@]}"; do
			if [[ -v rendered_vals["${warn_key}"] ]]; then
				local old_v="${rendered_vals[${warn_key}]}"
				local new_v="${template_vals[${warn_key}]}"
				if [[ "${old_v}" != "${new_v}" ]]; then
					local wk_esc ov_esc nv_esc
					wk_esc="$(_tfvars_escape_hcl_string "${warn_key}")"
					ov_esc="$(_tfvars_escape_hcl_string "${old_v}")"
					nv_esc="$(_tfvars_escape_hcl_string "${new_v}")"
					warnings_arr+=("{\"key\":\"${wk_esc}\",\"old_value\":\"${ov_esc}\",\"new_value\":\"${nv_esc}\"}")
					provisioning_txt_warnings+=("changed: ${warn_key}: old=\"${old_v}\" -> new=\"${new_v}\"")
				fi
			fi
		done

		if [[ ${#warnings_arr[@]} -gt 0 ]]; then
			change_warnings_json='['
			local wi
			for wi in "${!warnings_arr[@]}"; do
				if [[ $wi -gt 0 ]]; then change_warnings_json+=','; fi
				change_warnings_json+="${warnings_arr[$wi]}"
			done
			change_warnings_json+=']'
		fi
	fi

	local validation_status="pass"
	if [[ ${#errors[@]} -gt 0 ]]; then
		validation_status="fail"
	fi

	# Build JSON array for errors without jq dependency.
	local errors_json='[]'
	if [[ ${#errors[@]} -gt 0 ]]; then
		errors_json='['
		local i
		for i in "${!errors[@]}"; do
			local e_esc
			e_esc="$(_tfvars_escape_hcl_string "${errors[$i]}")"
			if [[ $i -gt 0 ]]; then
				errors_json+=','
			fi
			errors_json+=$'\n  "'
			errors_json+="${e_esc}"
			errors_json+='"'
		done
		errors_json+=$'\n]'
	fi

	_tfvars_write_validation_json \
		"${reports_dir%/}/${evidence_subdir}/validation.json" \
		"${timestamp}" \
		"${template_source}" \
		"${rendered_path}" \
		"${validation_status}" \
		"${required_token_id}" \
		"${secret_present}" \
		"${file_hash}" \
		"${errors_json}" \
		"${drift_results_json}" \
		"${change_warnings_json}"

	{
		echo "timestamp=${timestamp}"
		echo "template_source=${template_source}"
		echo "rendered_path=${rendered_path}"
		echo "validation_status=${validation_status}"
		echo "token_id=${required_token_id}"
		echo "secret_present=${secret_present}"
		echo "secret_source=${secret_source}"
		echo "file_hash=${file_hash}"
		if [[ ${#errors[@]} -gt 0 ]]; then
			echo "validation_errors:"
			printf '  - %s\n' "${errors[@]}"
		fi
		if [[ ${#provisioning_txt_warnings[@]} -gt 0 ]]; then
			echo "change_warnings:"
			printf '  - %s\n' "${provisioning_txt_warnings[@]}"
		fi
	} >"${reports_dir%/}/${evidence_subdir}/provisioning.txt"

	echo "${file_hash}" >"${reports_dir%/}/${evidence_subdir}/${environment}.tfvars.sha256"

	if [[ "${validation_status}" != "pass" ]]; then
		return 1
	fi

	# Install rendered file atomically.
	mkdir -p "$(dirname "${rendered_path}")"
	chmod 600 "${tmp}" 2>/dev/null || true
	mv -f "${tmp}" "${rendered_path}"
	trap - RETURN

	chmod 600 "${rendered_path}" 2>/dev/null || true
	return 0
}
