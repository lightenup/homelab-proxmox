#!/usr/bin/env bash
# alerting-heartbeat: out-of-band check of the homelab alerting path (RCA 2026-10-27).
# Managed by Ansible (role alerting_heartbeat). DO NOT EDIT on the host.
#
# Asks the monitoring LXC's Alertmanager whether the always-firing Watchdog alert is active.
# Watchdog active means Prometheus is evaluating rules, Prometheus can reach Alertmanager, and
# Alertmanager is up. If it is missing (or Alertmanager does not answer) for FAIL_THRESHOLD
# consecutive runs, page Pushover directly, never through Alertmanager, which is the thing
# being checked. While it stays down, repeat at most every REPEAT_SECONDS; after a page,
# announce the recovery once.
#
# Secrets come from the environment (systemd EnvironmentFile, 0600) and reach curl on stdin
# (-K -), never on its command line, so they do not show up in ps.
set -uo pipefail

: "${AM_URL:?AM_URL not set}"
: "${PUSHOVER_USER_KEY:?PUSHOVER_USER_KEY not set}"
: "${PUSHOVER_API_TOKEN:?PUSHOVER_API_TOKEN not set}"
PUSHOVER_URL="${PUSHOVER_URL:-https://api.pushover.net/1/messages.json}"
STATE_DIR="${STATE_DIR:-/var/lib/alerting-heartbeat}"
FAIL_THRESHOLD="${FAIL_THRESHOLD:-3}"
REPEAT_SECONDS="${REPEAT_SECONDS:-21600}"
now="${NOW:-$(date +%s)}"   # NOW: tests only
state_file="$STATE_DIR/state" # "<consecutive failures> <unix time of the last DOWN page, 0 = none>"

fails=0
paged_at=0
if [[ -r "$state_file" ]]; then
  read -r fails paged_at <"$state_file" || true
fi
[[ "$fails" =~ ^[0-9]+$ ]] || fails=0
[[ "$paged_at" =~ ^[0-9]+$ ]] || paged_at=0

save_state() {
  mkdir -p "$STATE_DIR"
  printf '%s %s\n' "$1" "$2" >"$state_file.tmp" && mv "$state_file.tmp" "$state_file"
}

# page TITLE MESSAGE PRIORITY -> 0 only if Pushover accepted it.
page() {
  local status
  status=$(printf 'data-urlencode = "token=%s"\ndata-urlencode = "user=%s"\n' \
    "$PUSHOVER_API_TOKEN" "$PUSHOVER_USER_KEY" |
    curl -sS -o /dev/null -w '%{http_code}' --max-time 15 -K - \
      --data-urlencode "title=$1" --data-urlencode "message=$2" --data-urlencode "priority=$3" \
      "$PUSHOVER_URL" 2>/dev/null) || status="${status:-curl-failed}"
  if [[ "$status" == "200" ]]; then
    echo "paged Pushover: $1"
    return 0
  fi
  echo "Pushover page failed (HTTP $status): $1" >&2
  return 1
}

reason=""
body=$(curl -sS --fail --max-time 10 -G "$AM_URL/api/v2/alerts" \
  --data-urlencode 'filter=alertname="Watchdog"' --data-urlencode active=true \
  --data-urlencode silenced=false --data-urlencode inhibited=false 2>&1)
rc=$?
if ((rc != 0)); then
  reason="Alertmanager at $AM_URL is unreachable or erroring (${body:0:160})"
else
  count=$(printf '%s' "$body" | python3 -c 'import json,sys; print(len(json.load(sys.stdin)))' 2>/dev/null) || count=""
  if [[ ! "$count" =~ ^[0-9]+$ ]]; then
    reason="Alertmanager at $AM_URL returned an answer that is not a JSON alert list"
  elif ((count == 0)); then
    reason="the Watchdog alert is not active in Alertmanager: Prometheus is not evaluating rules or cannot reach Alertmanager (or Watchdog was silenced)"
  fi
fi

if [[ -z "$reason" ]]; then
  if ((paged_at > 0)); then
    if ! page "Homelab alerting path recovered" \
      "The Watchdog alert is active in Alertmanager again; alerts are being delivered." 0; then
      save_state 0 "$paged_at" # keep the page marker so the recovery message is retried
      exit 0
    fi
  fi
  echo "ok: Watchdog active in Alertmanager"
  save_state 0 0
  exit 0
fi

fails=$((fails + 1))
echo "FAIL $fails/$FAIL_THRESHOLD: $reason" >&2
if ((fails >= FAIL_THRESHOLD)) && ((paged_at == 0 || now - paged_at >= REPEAT_SECONDS)); then
  if page "Homelab alerting path DOWN" \
    "Failed $fails checks in a row: $reason. Alerts are NOT being delivered. Checked from pve by alerting-heartbeat.timer; runbook: docs/operations/monitoring/alerting-heartbeat.md" 1; then
    paged_at=$now
  fi
fi
save_state "$fails" "$paged_at"
exit 1
