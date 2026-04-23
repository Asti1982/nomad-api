#!/usr/bin/env bash
set -euo pipefail

LIMIT="${NOMAD_COLD_OUTREACH_LIMIT:-10}"
QUERY="${NOMAD_HITL_OUTREACH_QUERY:-agent-card human-in-the-loop}"
SEND_FLAG=""

if [[ "${1:-}" == "--send" ]]; then
  SEND_FLAG="--send"
fi

if [[ -z "${NOMAD_PUBLIC_API_URL:-}" ]]; then
  if [[ -n "${CODESPACE_NAME:-}" && -n "${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN:-}" ]]; then
    export NOMAD_PUBLIC_API_URL="https://${CODESPACE_NAME}-${NOMAD_API_PORT:-8787}.${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN}"
  else
    echo "NOMAD_PUBLIC_API_URL is not set and this does not look like GitHub Codespaces." >&2
    exit 1
  fi
fi

echo "Checking Nomad public URL: ${NOMAD_PUBLIC_API_URL}"
python - <<'PY'
import os
import sys
import requests

base = os.environ["NOMAD_PUBLIC_API_URL"].rstrip("/")
for path in ("/health", "/.well-known/agent-card.json"):
    url = base + path
    response = requests.get(url, timeout=15)
    print(f"{url} -> {response.status_code}")
    if not response.ok:
        sys.exit(1)
PY

echo
echo "Starting HITL cold outreach campaign. Send flag: ${SEND_FLAG:-queue-only}"
python main.py --cli cold-outreach --discover ${SEND_FLAG} --limit "$LIMIT" --query "$QUERY" --json
