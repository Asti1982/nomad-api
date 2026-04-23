#!/usr/bin/env bash
set -euo pipefail

PORT_VALUE="${NOMAD_API_PORT:-8787}"
export NOMAD_API_HOST="${NOMAD_API_HOST:-0.0.0.0}"
export NOMAD_API_PORT="$PORT_VALUE"

if [[ -n "${CODESPACE_NAME:-}" && -n "${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN:-}" ]]; then
  export NOMAD_PUBLIC_API_URL="https://${CODESPACE_NAME}-${PORT_VALUE}.${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN}"
fi

echo "Nomad API host: ${NOMAD_API_HOST}:${NOMAD_API_PORT}"
echo "Nomad public URL: ${NOMAD_PUBLIC_API_URL:-not set yet}"
echo
echo "After the API starts, set port ${PORT_VALUE} visibility to Public in the Codespaces Ports panel if GitHub did not do it automatically."
echo "Health check: ${NOMAD_PUBLIC_API_URL:-http://127.0.0.1:${PORT_VALUE}}/health"
echo "Agent card:   ${NOMAD_PUBLIC_API_URL:-http://127.0.0.1:${PORT_VALUE}}/.well-known/agent-card.json"
echo

python nomad_api.py
