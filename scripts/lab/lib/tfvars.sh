#!/usr/bin/env bash
set -euo pipefail

# tfvars provisioning helpers
#
# Primary entrypoint:
#   _tfvars_provision_prod_and_write_proof <reports_dir> <tfvars_dir>
#
# Design constraints:
# - Never log secrets
# - Write redacted proof under <reports_dir>/prod-tfvars/
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
	local secret_present="$7" # true|false
	local file_hash="$8"
	local errors_json_array="$9" # JSON array string

	local ts_esc src_esc rp_esc
	ts_esc="$(_tfvars_escape_hcl_string "${timestamp}")"
	src_esc="$(_tfvars_escape_hcl_string "${template_source}")"
	rp_esc="$(_tfvars_escape_hcl_string "${rendered_path}")"

	cat >"${out_path}" <<EOF
{
  "timestamp": "${ts_esc}",
  "template_source": "${src_esc}",
  "rendered_path": "${rp_esc}",
  "validation_status": "${validation_status}",
  "token_id": "${token_id}",
  "secret_present": ${secret_present},
  "file_hash": "${file_hash}",
  "validation_errors": ${errors_json_array}
}
EOF
}

_tfvars_provision_prod_and_write_proof() {
	local reports_dir="$1"
	local tfvars_dir="$2"

	local required_token_id="terraform@pve!terraform-token"
	local rendered_path="${tfvars_dir%/}/prod.tfvars"

	mkdir -p "${reports_dir%/}/prod-tfvars" "${tfvars_dir%/}"

	local timestamp
	timestamp="$(_tfvars_now_utc)"

	# Secret passed by GitHub Actions (preferred). Back-compat supports PROXMOX_TOKEN_SECRET.
	# If neither is present, we will attempt to reuse an existing rendered prod.tfvars
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
			candidates+=("${repo_root}/terraform/environments/prod.tfvars")
			candidates+=("${repo_root}/terraform/environments/prod.tfvars.example")
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

	# If no token secret is available, prefer validating an existing rendered prod.tfvars
	# (so we don't overwrite a locally-managed secret with an empty value). This also
	# satisfies the "template" requirement when no repo template exists.
	if [[ -z "${token_secret}" && -f "${rendered_path}" ]]; then
		template_path="${rendered_path}"
		template_source="file:${rendered_path}"
		secret_source="existing_file"
	fi

	if [[ -z "${template_path}" ]]; then
		# No template -> fail early, but still write proof artifacts.
		local errors_json='["Missing prod.tfvars template (set PROD_TFVARS_TEMPLATE or ensure terraform/environments/prod.tfvars.example exists)"]'
		_tfvars_write_validation_json "${reports_dir%/}/prod-tfvars/validation.json" "${timestamp}" "missing" "${rendered_path}" "fail" "${required_token_id}" "false" "0000000000000000000000000000000000000000000000000000000000000000" "${errors_json}"
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
		} >"${reports_dir%/}/prod-tfvars/provisioning.txt"
		echo "0000000000000000000000000000000000000000000000000000000000000000" >"${reports_dir%/}/prod-tfvars/prod.tfvars.sha256"
		return 1
	fi

	# Render to a temp file; only move into place if validation passes.
	umask 077
	local tmp
	tmp="$(mktemp -t prod.tfvars.XXXXXX)"
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

	# Inject secret only if provided. If no env secret is available, do NOT overwrite
	# any existing secret in the file.
	if [[ -n "${token_secret}" ]]; then
		local secret_escaped
		secret_escaped="$(_tfvars_escape_hcl_string "${token_secret}")"
		if grep -Eq '^[[:space:]]*proxmox_api_token_secret[[:space:]]*=' "${tmp}"; then
			# macOS/BSD sed requires a backup suffix; GNU sed ignores it.
			sed -i.bak -E "s|^[[:space:]]*proxmox_api_token_secret[[:space:]]*=.*$|proxmox_api_token_secret = \"${secret_escaped}\"|" "${tmp}" 2>/dev/null || true
			rm -f "${tmp}.bak" 2>/dev/null || true
		else
			printf 'proxmox_api_token_secret = "%s"\n' "${secret_escaped}" >>"${tmp}"
		fi
	fi

	# Validation (no secrets in outputs)
	local -a errors=()

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

	_tfvars_write_validation_json "${reports_dir%/}/prod-tfvars/validation.json" "${timestamp}" "${template_source}" "${rendered_path}" "${validation_status}" "${required_token_id}" "${secret_present}" "${file_hash}" "${errors_json}"

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
	} >"${reports_dir%/}/prod-tfvars/provisioning.txt"

	echo "${file_hash}" >"${reports_dir%/}/prod-tfvars/prod.tfvars.sha256"

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

