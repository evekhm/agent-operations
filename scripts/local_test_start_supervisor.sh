#!/bin/bash
# Starts all agents locally on port 8000 (including knowledge_supervisor).
# PTO agent A2A is on the same server.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${SCRIPT_DIR}/.."
VENV="${PROJECT_ROOT}/.venv/bin"

# Source .env
if [ -f "${PROJECT_ROOT}/.env" ]; then
    source "${PROJECT_ROOT}/.env"
fi

SUPERVISOR_PORT=${SUPERVISOR_PORT:-8000}

# Point knowledge_supervisor to local PTO agent (same server, A2A enabled)
export PTO_AGENT_URL="http://localhost:${SUPERVISOR_PORT}"

echo "=== Starting All Agents on port ${SUPERVISOR_PORT} ==="
echo "PTO_AGENT_URL: ${PTO_AGENT_URL}"
echo ""

cd "${PROJECT_ROOT}"
exec "${VENV}/adk" api_server \
    --port "${SUPERVISOR_PORT}" \
    --a2a \
    --auto_create_session \
    agents/
