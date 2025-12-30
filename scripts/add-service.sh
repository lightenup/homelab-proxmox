#!/bin/bash
set -e

# Usage: ./add-service.sh <hostname> [options]
# Options:
#   --scheme <http|https>
#   --port <number>
#   --path <string>
#   --profile <lan|tailscale|both|none>
#   --verify-ssl <true|false>
#   --expect-status <code (200)>
#   --verification-command <string> (only if profile=none)

HOSTNAME=$1
if [ -z "$HOSTNAME" ]; then
    echo "Usage: $0 <hostname> [options]"
    echo "Example: $0 my-service --port 8080 --path /health"
    exit 1
fi
shift

# Defaults
SCHEME="http"
PORT="80"
PATH_VAL="/"
PROFILE="both"
VERIFY_SSL="true"
EXPECT_STATUS="200"
VERIFICATION_COMMAND=""

while [[ "$#" -gt 0 ]]; do
    case $1 in
        --scheme) SCHEME="$2"; shift ;;
        --port) PORT="$2"; shift ;;
        --path) PATH_VAL="$2"; shift ;;
        --profile) PROFILE="$2"; shift ;;
        --verify-ssl) VERIFY_SSL="$2"; shift ;;
        --expect-status) EXPECT_STATUS="$2"; shift ;;
        --verification-command) VERIFICATION_COMMAND="$2"; shift ;;
        *) echo "Unknown parameter passed: $1"; exit 1 ;;
    esac
    shift
done

HOST_VARS_FILE="ansible/host_vars/${HOSTNAME}.yml"
mkdir -p "ansible/host_vars"

if [ ! -f "$HOST_VARS_FILE" ]; then
    echo "Creating new file: $HOST_VARS_FILE"
    echo "---" > "$HOST_VARS_FILE"
else
    echo "Updating existing file: $HOST_VARS_FILE"
fi

# Use Python to safely remove existing healthcheck config and append new config
python3 -c "
import re
import sys
import os

file_path = '$HOST_VARS_FILE'
scheme = '$SCHEME'
port = '$PORT'
path = '$PATH_VAL'
profile = '$PROFILE'
verify_ssl = '$VERIFY_SSL'
expect_status = '$EXPECT_STATUS'
verification_command = '$VERIFICATION_COMMAND'

if os.path.exists(file_path):
    with open(file_path, 'r') as f:
        content = f.read()
else:
    content = '---\n'

# Remove healthcheck_url block (key + indented lines)
# Matches 'healthcheck_url:' at start of line, followed by lines starting with whitespace
content = re.sub(r'^healthcheck_url:\s*\n(\s+.*\n)*', '', content, flags=re.MULTILINE)

# Remove flat healthcheck keys
content = re.sub(r'^healthcheck_\w+:.*\n?', '', content, flags=re.MULTILINE)

# Clean up multiple newlines
content = re.sub(r'\n{3,}', '\n\n', content)
content = content.rstrip() + '\n'

# Append new config
new_config = f'''
healthcheck_url:
  scheme: {scheme}
  port: {port}
  path: {path}
healthcheck_profile: {profile}
healthcheck_verify_ssl: {verify_ssl}
healthcheck_expect_status: {expect_status}
'''

if profile == 'none' and verification_command:
    new_config += f'healthcheck_verification_command: \"{verification_command}\"\n'

with open(file_path, 'w') as f:
    f.write(content + new_config)
"

echo "Successfully updated $HOST_VARS_FILE"
