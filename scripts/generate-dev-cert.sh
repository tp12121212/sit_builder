#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   scripts/generate-dev-cert.sh 10.0.0.159
#
# Requires:
#   - mkcert installed
#   - local CA trusted via `mkcert -install`

IP_ADDR="${1:-}"
if [[ -z "${IP_ADDR}" ]]; then
  echo "Usage: $0 <lan-ip-address>"
  exit 1
fi

CERT_DIR="$(pwd)/frontend/certs"
mkdir -p "${CERT_DIR}"

mkcert -cert-file "${CERT_DIR}/dev-cert.pem" -key-file "${CERT_DIR}/dev-key.pem" \
  localhost 127.0.0.1 ::1 "${IP_ADDR}"

cat <<EOF
Created:
  ${CERT_DIR}/dev-cert.pem
  ${CERT_DIR}/dev-key.pem

Set in frontend/.env:
  VITE_DEV_HTTPS_CERT_PATH=${CERT_DIR}/dev-cert.pem
  VITE_DEV_HTTPS_KEY_PATH=${CERT_DIR}/dev-key.pem
EOF
