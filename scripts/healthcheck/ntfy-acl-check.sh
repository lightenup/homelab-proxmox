#!/usr/bin/env bash
# ntfy ACL matrix check (spec 082, SC-002; extended by spec 090, spec 087, spec 095)
#
# Asserts every cell in data-model.md § "The access matrix the SC-002 check asserts":
#
#   (095 adds the hermes-lab-in / hermes-lab scratch cells below, per
#   specs/095-ntfy-two-way/contracts/acl-matrix.md § LAB scratch pair.)
#
#   Credential ↓ / action → | read alerts | read hermes | read pve-backup | read versions | read mutation | write alerts | write hermes | write pve-backup | write versions | write mutation | write other
#   ------------------------+-------------+-------------+-----------------+---------------+---------------+--------------+--------------+------------------+----------------+----------------+-------------
#   none                    | ✗           | ✗           | ✗               | ✗             | ✗             | ✗            | ✗            | ✗                | ✗              | ✗              | ✗
#   owner token             | ✓           | ✓           | ✓               | ✓             | ✓             | ✗            | ✗            | ✗                | ✗              | ✗              | ✗
#   alertmanager token      | ✗           | ✗           | ✗               | ✗             | ✗             | ✓            | ✗            | ✗                | ✗              | ✗              | ✗
#   hermes token            | ✗           | ✗           | ✗               | ✗             | ✗             | ✗            | ✓            | ✗                | ✗              | ✗              | ✗
#   pve_backup token        | ✗           | ✗           | ✗               | ✗             | ✗             | ✗            | ✗            | ✓                | ✗              | ✗              | ✗
#   version_check token     | ✗           | ✗           | ✗               | ✗             | ✗             | ✗            | ✗            | ✗                | ✓              | ✗              | ✗
#   mutation token           | ✗           | ✗           | ✗               | ✗             | ✗             | ✗            | ✗            | ✗                | ✗              | ✓              | ✗
#
# ✓ = HTTP 200; ✗ = HTTP 401 or 403.
#
# Reads use GET /<topic>/json?poll=1&since=1m (the JSON API), because GET /<topic>
# serves the web app with a 200 to anyone and would fail the read cells.
# Writes use POST /<topic> with a tagged body.
#
# Usage:
#   NTFY_URL=http://192.168.1.222 \
#   NTFY_OWNER_TOKEN=... NTFY_ALERTMANAGER_TOKEN=... NTFY_HERMES_TOKEN=... \
#   NTFY_PVE_BACKUP_TOKEN=... NTFY_VERSION_CHECK_TOKEN=... NTFY_MUTATION_TOKEN=... \
#     scripts/healthcheck/ntfy-acl-check.sh
#
# Exits non-zero on any FAIL. Never echoes tokens.
#
# Rate limiting: ntfy's `visitor-request-limit-burst` defaults to 60 requests per visitor
# (source IP, since `behind-proxy: true` makes it see the real client, not Caddy), replenished
# one per `visitor-request-limit-replenish` (default 5s) — confirmed against
# `binwiederhier/ntfy:v2.28.0 serve --help`, 2026-10-25. Neither is overridden in
# ansible/roles/ntfy/templates/server.yml.j2, so the server default applies. The matrix has
# grown every spec that touched it (20 cells at 082, 35 at 089, 54 at 090) and 095's
# hermes_lab row is the first to cross it (120 cells today). A single run from one host now
# always exhausts the burst, so every request past the 60th retries on 429 below rather than
# widening the server's own abuse protection, which is unrelated to this script's own volume.
set -euo pipefail

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  cat <<'EOF'
ntfy-acl-check.sh — assert the ntfy access-control matrix (spec 082, SC-002)

Environment variables (all required):
  NTFY_URL                 Base URL, e.g. http://192.168.1.222 or https://ntfy.hus-sky.no
  NTFY_OWNER_TOKEN         Bearer token for the owner account
  NTFY_ALERTMANAGER_TOKEN  Bearer token for the alertmanager account
  NTFY_HERMES_TOKEN        Bearer token for the hermes account
  NTFY_PVE_BACKUP_TOKEN    Bearer token for the pve_backup account (spec 089)
  NTFY_VERSION_CHECK_TOKEN Bearer token for the version_check account (spec 090)
  NTFY_MUTATION_TOKEN      Bearer token for the mutation account (spec 087)
  NTFY_HERMES_LAB_TOKEN    Bearer token for the hermes_lab scratch account (spec 095 FR-011)

A full run now makes more requests than ntfy's default per-visitor burst (60), so it retries on
429 and can take several minutes — this is expected, not a hang.

Exit code: 0 if all cells match, 1 otherwise.
EOF
  exit 0
fi

for var in NTFY_URL NTFY_OWNER_TOKEN NTFY_ALERTMANAGER_TOKEN NTFY_HERMES_TOKEN NTFY_PVE_BACKUP_TOKEN NTFY_VERSION_CHECK_TOKEN NTFY_MUTATION_TOKEN NTFY_HERMES_LAB_TOKEN; do
  if [[ -z "${!var:-}" ]]; then
    echo "ERROR: ${var} is not set. See --help." >&2
    exit 2
  fi
done

NTFY_URL="${NTFY_URL%/}"
FAILURES=0
TOTAL=0

# Matches ntfy's own visitor-request-limit-replenish default (5s); used only when a 429
# response carries no Retry-After header to read instead.
readonly DEFAULT_RETRY_AFTER_SECONDS=5
# Generous bound: in steady state one retry per request suffices once past the burst (each
# wait regenerates exactly the one token the next request consumes). Higher in case something
# else sharing this IP is also calling ntfy concurrently.
readonly MAX_RATE_LIMIT_RETRIES=8

# do_request <token_or_empty> <method: GET|POST> <topic> <expected: allow|deny>
do_request() {
  local token="$1" method="$2" topic="$3" expected="$4"
  local url code attempt header_file retry_after

  TOTAL=$((TOTAL + 1))

  # Build the curl argument array.
  header_file="$(mktemp -t ntfy-acl-check.XXXXXX)"
  local -a curl_args=(-s -o /dev/null -D "${header_file}" -w '%{http_code}')

  if [[ "$method" == "GET" ]]; then
    # JSON API poll: GET /<topic>/json?poll=1&since=1m
    url="${NTFY_URL}/${topic}/json?poll=1&since=1m"
  else
    # POST /<topic> with a tagged body
    url="${NTFY_URL}/${topic}"
    curl_args+=(-X POST -d "acl-check $(date -u +%Y-%m-%dT%H:%M:%SZ)" -H "Tags: acl-check" -H "Priority: min")
  fi

  if [[ -n "$token" ]]; then
    curl_args+=(-H "Authorization: Bearer ${token}")
  fi

  attempt=0
  while :; do
    code=$(curl "${curl_args[@]}" "$url" 2>/dev/null || true)
    if [[ "$code" != "429" || "$attempt" -ge "$MAX_RATE_LIMIT_RETRIES" ]]; then
      break
    fi
    attempt=$((attempt + 1))
    retry_after="$(grep -i '^retry-after:' "${header_file}" | tr -d '\r' | awk '{print $2}')"
    sleep "${retry_after:-$DEFAULT_RETRY_AFTER_SECONDS}"
  done
  rm -f "${header_file}"

  local got_label
  case "$code" in
    200) got_label="allow" ;;
    401|403) got_label="deny" ;;
    *) got_label="unexpected(${code})" ;;
  esac

  local credential_label
  if [[ -z "$token" ]]; then
    credential_label="none"
  elif [[ "$token" == "$NTFY_OWNER_TOKEN" ]]; then
    credential_label="owner"
  elif [[ "$token" == "$NTFY_ALERTMANAGER_TOKEN" ]]; then
    credential_label="alertmanager"
  elif [[ "$token" == "$NTFY_PVE_BACKUP_TOKEN" ]]; then
    credential_label="pve_backup"
  elif [[ "$token" == "$NTFY_VERSION_CHECK_TOKEN" ]]; then
    credential_label="version_check"
  elif [[ "$token" == "$NTFY_MUTATION_TOKEN" ]]; then
    credential_label="mutation"
  elif [[ "$token" == "$NTFY_HERMES_LAB_TOKEN" ]]; then
    credential_label="hermes_lab"
  else
    credential_label="hermes"
  fi

  if [[ "$got_label" == "$expected" ]]; then
    echo "PASS ${credential_label} ${method} ${topic} got=${code}"
  else
    echo "FAIL ${credential_label} ${method} ${topic} got=${code} expected=${expected}"
    FAILURES=$((FAILURES + 1))
  fi
}

# --- Row: no credential ---
do_request "" GET  alerts     deny
do_request "" GET  hermes     deny
do_request "" GET  pve-backup deny
do_request "" GET  versions   deny
do_request "" GET  mutation  deny
do_request "" GET  hermes-lab-in deny
do_request "" GET  hermes-lab deny
do_request "" POST alerts     deny
do_request "" POST hermes     deny
do_request "" POST pve-backup deny
do_request "" POST versions   deny
do_request "" POST mutation  deny
do_request "" POST other      deny

# --- Row: owner token (read *) ---
do_request "$NTFY_OWNER_TOKEN" GET  alerts     allow
do_request "$NTFY_OWNER_TOKEN" GET  hermes     allow
do_request "$NTFY_OWNER_TOKEN" GET  pve-backup allow
do_request "$NTFY_OWNER_TOKEN" GET  versions   allow
do_request "$NTFY_OWNER_TOKEN" GET  mutation  allow
do_request "$NTFY_OWNER_TOKEN" POST alerts     deny
do_request "$NTFY_OWNER_TOKEN" POST hermes     deny
do_request "$NTFY_OWNER_TOKEN" POST pve-backup deny
do_request "$NTFY_OWNER_TOKEN" POST versions   deny
do_request "$NTFY_OWNER_TOKEN" POST mutation  deny
do_request "$NTFY_OWNER_TOKEN" POST other      deny
do_request "$NTFY_OWNER_TOKEN" GET hermes-lab-in allow
do_request "$NTFY_OWNER_TOKEN" POST hermes-lab-in allow  # 095 FR-011: owner writes the scratch inbound
do_request "$NTFY_OWNER_TOKEN" GET hermes-lab allow
do_request "$NTFY_OWNER_TOKEN" POST hermes-lab deny

# --- Row: alertmanager token (write alerts only) ---
do_request "$NTFY_ALERTMANAGER_TOKEN" GET  alerts     deny
do_request "$NTFY_ALERTMANAGER_TOKEN" GET  hermes     deny
do_request "$NTFY_ALERTMANAGER_TOKEN" GET  pve-backup deny
do_request "$NTFY_ALERTMANAGER_TOKEN" GET  versions   deny
do_request "$NTFY_ALERTMANAGER_TOKEN" GET  mutation  deny
do_request "$NTFY_ALERTMANAGER_TOKEN" POST alerts     allow
do_request "$NTFY_ALERTMANAGER_TOKEN" POST hermes     deny
do_request "$NTFY_ALERTMANAGER_TOKEN" POST pve-backup deny
do_request "$NTFY_ALERTMANAGER_TOKEN" POST versions   deny
do_request "$NTFY_ALERTMANAGER_TOKEN" POST mutation  deny
do_request "$NTFY_ALERTMANAGER_TOKEN" POST other      deny
do_request "$NTFY_ALERTMANAGER_TOKEN" GET hermes-lab-in deny
do_request "$NTFY_ALERTMANAGER_TOKEN" POST hermes-lab-in deny
do_request "$NTFY_ALERTMANAGER_TOKEN" GET hermes-lab deny
do_request "$NTFY_ALERTMANAGER_TOKEN" POST hermes-lab deny

# --- Row: hermes token (write hermes only) ---
do_request "$NTFY_HERMES_TOKEN" GET  alerts     deny
do_request "$NTFY_HERMES_TOKEN" GET  hermes     deny
do_request "$NTFY_HERMES_TOKEN" GET  pve-backup deny
do_request "$NTFY_HERMES_TOKEN" GET  versions   deny
do_request "$NTFY_HERMES_TOKEN" GET  mutation  deny
do_request "$NTFY_HERMES_TOKEN" POST alerts     deny
do_request "$NTFY_HERMES_TOKEN" POST hermes     allow
do_request "$NTFY_HERMES_TOKEN" POST pve-backup deny
do_request "$NTFY_HERMES_TOKEN" POST versions   deny
do_request "$NTFY_HERMES_TOKEN" POST mutation  deny
do_request "$NTFY_HERMES_TOKEN" POST other      deny
do_request "$NTFY_HERMES_TOKEN" GET hermes-lab-in deny
do_request "$NTFY_HERMES_TOKEN" POST hermes-lab-in deny
do_request "$NTFY_HERMES_TOKEN" GET hermes-lab deny
do_request "$NTFY_HERMES_TOKEN" POST hermes-lab deny

# --- Row: pve_backup token (write pve-backup only) ---
do_request "$NTFY_PVE_BACKUP_TOKEN" GET  alerts     deny
do_request "$NTFY_PVE_BACKUP_TOKEN" GET  hermes     deny
do_request "$NTFY_PVE_BACKUP_TOKEN" GET  pve-backup deny
do_request "$NTFY_PVE_BACKUP_TOKEN" GET  versions   deny
do_request "$NTFY_PVE_BACKUP_TOKEN" GET  mutation  deny
do_request "$NTFY_PVE_BACKUP_TOKEN" POST alerts     deny
do_request "$NTFY_PVE_BACKUP_TOKEN" POST hermes     deny
do_request "$NTFY_PVE_BACKUP_TOKEN" POST pve-backup allow
do_request "$NTFY_PVE_BACKUP_TOKEN" POST versions   deny
do_request "$NTFY_PVE_BACKUP_TOKEN" POST mutation  deny
do_request "$NTFY_PVE_BACKUP_TOKEN" POST other      deny
do_request "$NTFY_PVE_BACKUP_TOKEN" GET hermes-lab-in deny
do_request "$NTFY_PVE_BACKUP_TOKEN" POST hermes-lab-in deny
do_request "$NTFY_PVE_BACKUP_TOKEN" GET hermes-lab deny
do_request "$NTFY_PVE_BACKUP_TOKEN" POST hermes-lab deny

# --- Row: version_check token (write versions only) ---
do_request "$NTFY_VERSION_CHECK_TOKEN" GET  alerts     deny
do_request "$NTFY_VERSION_CHECK_TOKEN" GET  hermes     deny
do_request "$NTFY_VERSION_CHECK_TOKEN" GET  pve-backup deny
do_request "$NTFY_VERSION_CHECK_TOKEN" GET  versions   deny
do_request "$NTFY_VERSION_CHECK_TOKEN" GET  mutation  deny
do_request "$NTFY_VERSION_CHECK_TOKEN" POST alerts     deny
do_request "$NTFY_VERSION_CHECK_TOKEN" POST hermes     deny
do_request "$NTFY_VERSION_CHECK_TOKEN" POST pve-backup deny
do_request "$NTFY_VERSION_CHECK_TOKEN" POST versions   allow
do_request "$NTFY_VERSION_CHECK_TOKEN" POST mutation  deny
do_request "$NTFY_VERSION_CHECK_TOKEN" POST other      deny
do_request "$NTFY_VERSION_CHECK_TOKEN" GET hermes-lab-in deny
do_request "$NTFY_VERSION_CHECK_TOKEN" POST hermes-lab-in deny
do_request "$NTFY_VERSION_CHECK_TOKEN" GET hermes-lab deny
do_request "$NTFY_VERSION_CHECK_TOKEN" POST hermes-lab deny

# --- Row: mutation token (write mutation only) ---
do_request "$NTFY_MUTATION_TOKEN" GET  alerts     deny
do_request "$NTFY_MUTATION_TOKEN" GET  hermes     deny
do_request "$NTFY_MUTATION_TOKEN" GET  pve-backup deny
do_request "$NTFY_MUTATION_TOKEN" GET  versions   deny
do_request "$NTFY_MUTATION_TOKEN" GET  mutation  deny
do_request "$NTFY_MUTATION_TOKEN" POST alerts     deny
do_request "$NTFY_MUTATION_TOKEN" POST hermes     deny
do_request "$NTFY_MUTATION_TOKEN" POST pve-backup deny
do_request "$NTFY_MUTATION_TOKEN" POST versions   deny
do_request "$NTFY_MUTATION_TOKEN" POST mutation  allow
do_request "$NTFY_MUTATION_TOKEN" POST other      deny
do_request "$NTFY_MUTATION_TOKEN" GET hermes-lab-in deny
do_request "$NTFY_MUTATION_TOKEN" POST hermes-lab-in deny
do_request "$NTFY_MUTATION_TOKEN" GET hermes-lab deny
do_request "$NTFY_MUTATION_TOKEN" POST hermes-lab deny

# --- Row: hermes_lab token (095 FR-011 LAB scratch pair) ---
do_request "$NTFY_HERMES_LAB_TOKEN" GET  hermes-lab-in allow
do_request "$NTFY_HERMES_LAB_TOKEN" POST hermes-lab-in deny  # FR-011: scratch agent cannot write its own inbound
do_request "$NTFY_HERMES_LAB_TOKEN" GET  hermes-lab    deny
do_request "$NTFY_HERMES_LAB_TOKEN" POST hermes-lab    allow
do_request "$NTFY_HERMES_LAB_TOKEN" GET  hermes         deny  # FR-011/SC-002: no production topic, read or write
do_request "$NTFY_HERMES_LAB_TOKEN" POST hermes         deny
do_request "$NTFY_HERMES_LAB_TOKEN" GET  hermes-in      deny
do_request "$NTFY_HERMES_LAB_TOKEN" POST hermes-in      deny
do_request "$NTFY_HERMES_LAB_TOKEN" GET  alerts         deny
do_request "$NTFY_HERMES_LAB_TOKEN" POST alerts         deny
do_request "$NTFY_HERMES_LAB_TOKEN" GET  pve-backup     deny
do_request "$NTFY_HERMES_LAB_TOKEN" POST pve-backup     deny
do_request "$NTFY_HERMES_LAB_TOKEN" GET  versions       deny
do_request "$NTFY_HERMES_LAB_TOKEN" POST versions       deny
do_request "$NTFY_HERMES_LAB_TOKEN" GET  mutation       deny
do_request "$NTFY_HERMES_LAB_TOKEN" POST mutation       deny
do_request "$NTFY_HERMES_LAB_TOKEN" POST other          deny

echo ""
echo "=== ntfy ACL check: $((TOTAL - FAILURES))/${TOTAL} PASS, ${FAILURES} FAIL ==="

if [[ $FAILURES -gt 0 ]]; then
  exit 1
fi
