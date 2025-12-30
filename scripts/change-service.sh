#!/bin/bash
set -e

HOSTNAME=$1
if [ -z "$HOSTNAME" ]; then
    echo "Usage: $0 <hostname> [options]"
    exit 1
fi

HOST_VARS_FILE="ansible/host_vars/${HOSTNAME}.yml"

if [ ! -f "$HOST_VARS_FILE" ]; then
    echo "Error: Service $HOSTNAME does not exist (file $HOST_VARS_FILE missing)."
    echo "Use add-service.sh to create a new service."
    exit 1
fi

# Pass all arguments to add-service.sh
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
"$DIR/add-service.sh" "$@"
