#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PORT_VALUE="${NOMAD_API_PORT:-8787}"
export NOMAD_API_HOST="${NOMAD_API_HOST:-0.0.0.0}"
export NOMAD_API_PORT="$PORT_VALUE"

if [[ -n "${CODESPACE_NAME:-}" && -n "${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN:-}" ]]; then
  export NOMAD_PUBLIC_API_URL="https://${CODESPACE_NAME}-${PORT_VALUE}.${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN}"
fi

if python - <<'PY'
import os
import socket
import sys

port = int(os.environ.get("NOMAD_API_PORT", "8787"))
sock = socket.socket()
sock.settimeout(0.5)
try:
    sock.connect(("127.0.0.1", port))
except OSError:
    sys.exit(1)
finally:
    sock.close()
PY
then
  echo "Nomad API already appears to be listening on port ${PORT_VALUE}."
  exit 0
fi

echo "Starting Nomad API on ${NOMAD_API_HOST}:${NOMAD_API_PORT}"
echo "Nomad public URL: ${NOMAD_PUBLIC_API_URL:-not set yet}"
nohup python app.py >/tmp/nomad-api.log 2>&1 &
echo "Nomad API background pid: $!"
echo "Log: /tmp/nomad-api.log"
