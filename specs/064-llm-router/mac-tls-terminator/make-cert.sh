#!/bin/bash
# Generate the long-lived self-signed certificate the TLS terminator serves.
#
# The SAN must carry the mDNS name, because FR-013 requires the gateway to address the Mac
# by name and the gateway VERIFIES the certificate rather than skipping verification. The IP
# is included only as a convenience for diagnostics; nothing in the deploy uses it.
#
# 10 years, deliberately. A homelab has no certificate authority and no renewal automation,
# so a short life buys nothing but a future outage. Expiry is legible when it comes: the
# gateway fails with a TLS verification error naming the certificate, not a hang.

set -euo pipefail

DIR="${HERMES_TLS_DIR:-$HOME/.config/hermes-tls}"
CN="${HERMES_TLS_CN:-xmjdvvw39y2t.local}"
IP="${HERMES_TLS_IP:-192.168.1.177}"

mkdir -p "$DIR"
chmod 700 "$DIR"

openssl req -x509 -newkey rsa:2048 -nodes -days 3650 \
  -keyout "$DIR/key.pem" -out "$DIR/cert.pem" \
  -subj "/CN=${CN}" \
  -addext "subjectAltName=DNS:${CN},IP:${IP}" \
  -addext "basicConstraints=critical,CA:TRUE" \
  -addext "keyUsage=critical,digitalSignature,keyEncipherment,keyCertSign" \
  -addext "extendedKeyUsage=serverAuth" 2>/dev/null

chmod 600 "$DIR/key.pem"
chmod 644 "$DIR/cert.pem"

echo "wrote $DIR/cert.pem and $DIR/key.pem"
openssl x509 -in "$DIR/cert.pem" -noout -subject -enddate -ext subjectAltName | sed 's/^/  /'
echo
echo "Copy the PUBLIC cert into the homelab repo so the gateway can verify against it:"
echo "  cp $DIR/cert.pem <repo>/ansible/roles/llm_router/files/mac-ca.pem"
echo "The key never leaves this machine."
