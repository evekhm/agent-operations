#!/bin/bash
# Starts the PTO agent locally on port 8001 with A2A enabled.
# This must be running before starting the knowledge_supervisor.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${SCRIPT_DIR}/.."
VENV="${PROJECT_ROOT}/.venv/bin"

# Source .env
if [ -f "${PROJECT_ROOT}/.env" ]; then
    source "${PROJECT_ROOT}/.env"
fi

PTO_PORT=${PTO_PORT:-8001}
export PTO_AGENT_URL="http://localhost:${PTO_PORT}"

echo "=== Starting PTO Agent on port ${PTO_PORT} (A2A mode) ==="

cd "${PROJECT_ROOT}"
exec "${VENV}/adk" api_server \
    --port "${PTO_PORT}" \
    --a2a \
    --auto_create_session \
    agents/
