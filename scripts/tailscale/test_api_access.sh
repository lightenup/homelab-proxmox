#!/usr/bin/env bash
# scripts/tailscale/test_api_access.sh
# Usage: TS_OAUTH_CLIENT_ID=... TS_OAUTH_SECRET=... ./test_api_access.sh

set -euo pipefail

if ! command -v jq >/dev/null 2>&1; then
  echo "Error: jq is not installed."
  echo "Install with: brew install jq (macOS) or apt install jq (Debian/Ubuntu)"
  exit 1
fi

if [ -z "$TS_OAUTH_CLIENT_ID" ] || [ -z "$TS_OAUTH_SECRET" ]; then
  echo "Error: TS_OAUTH_CLIENT_ID and TS_OAUTH_SECRET must be set."
  echo "Usage: TS_OAUTH_CLIENT_ID=... TS_OAUTH_SECRET=... $0"
  exit 1
fi

echo "Generating Access Token..."
RESPONSE=$(curl -s -d "client_id=$TS_OAUTH_CLIENT_ID" -d "client_secret=$TS_OAUTH_SECRET" "https://api.tailscale.com/api/v2/oauth/token")
ACCESS_TOKEN=$(echo "$RESPONSE" | jq -r '.access_token')

if [ "$ACCESS_TOKEN" == "null" ] || [ -z "$ACCESS_TOKEN" ]; then
  echo "Error: Failed to get access token."
  echo "Response: $RESPONSE"
  exit 1
fi

echo "Access Token generated successfully."

echo "Listing Devices (first 2)..."
curl -s -H "Authorization: Bearer $ACCESS_TOKEN" "https://api.tailscale.com/api/v2/tailnet/-/devices" | jq '.devices[:2]'
