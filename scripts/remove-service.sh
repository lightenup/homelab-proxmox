#!/bin/bash
set -e

HOSTNAME=$1
if [ -z "$HOSTNAME" ]; then
    echo "Usage: $0 <hostname>"
    exit 1
fi

HOST_VARS_FILE="ansible/host_vars/${HOSTNAME}.yml"

if [ ! -f "$HOST_VARS_FILE" ]; then
    echo "Error: File $HOST_VARS_FILE does not exist."
    exit 1
fi

python3 -c "
import re
import sys

file_path = '$HOST_VARS_FILE'

with open(file_path, 'r') as f:
    content = f.read()

# Remove healthcheck_url block
content = re.sub(r'^healthcheck_url:\s*\n(\s+.*\n)*', '', content, flags=re.MULTILINE)

# Remove flat healthcheck keys
content = re.sub(r'^healthcheck_\w+:.*\n?', '', content, flags=re.MULTILINE)

# Clean up
content = re.sub(r'\n{3,}', '\n\n', content)
content = content.rstrip() + '\n'

with open(file_path, 'w') as f:
    f.write(content)
"

echo "Removed healthcheck configuration from $HOST_VARS_FILE"
