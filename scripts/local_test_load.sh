#!/bin/bash
# Runs the load generator against a LOCAL knowledge_supervisor (port 8000).
# Instead of calling the Reasoning Engine API, this uses the local ADK API server.
#
# Requires:
#   1. PTO agent running on port 8001 (local_test_start_pto.sh)
#   2. Knowledge supervisor running on port 8000 (local_test_start_supervisor.sh)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${SCRIPT_DIR}/.."
VENV="${PROJECT_ROOT}/.venv/bin"

# Source .env
if [ -f "${PROJECT_ROOT}/.env" ]; then
    source "${PROJECT_ROOT}/.env"
fi

SUPERVISOR_PORT=${SERVER_PORT:-${SUPERVISOR_PORT:-8000}}
SUPERVISOR_URL="http://localhost:${SUPERVISOR_PORT}"

# Ensure aiohttp is available
"${VENV}/pip" show aiohttp > /dev/null 2>&1 || {
    echo "Installing aiohttp (needed for local load generator)..."
    "${VENV}/pip" install aiohttp -q
}

# Check supervisor is running
echo "Checking supervisor at ${SUPERVISOR_URL}..."
if ! curl -s "${SUPERVISOR_URL}/list-apps" > /dev/null 2>&1; then
    echo "ERROR: Knowledge supervisor not responding on port ${SUPERVISOR_PORT}."
    echo "Start it first with: ./scripts/local_test_start_supervisor.sh"
    exit 1
fi
echo "Supervisor is ready."

# Configuration
export TOPICS_CONFIG=${TOPICS_CONFIG:-'pto and sick leave balances:3,vacation planning and working days:2,company policies and HR procedures:2,ADK documentation and tools:2,general knowledge and technology:2,database lookups and calculations:1,Google Cloud and GCP services:2'}
export CONCURRENCY=${CONCURRENCY:-3}
export DURATION_MINUTES=${DURATION_MINUTES:-5}

echo ""
echo "=== Local Load Test Configuration ==="
echo "SUPERVISOR_URL: ${SUPERVISOR_URL}"
echo "TOPICS_CONFIG:  ${TOPICS_CONFIG}"
echo "CONCURRENCY:    ${CONCURRENCY}"
echo "DURATION_MINUTES: ${DURATION_MINUTES}"
echo "======================================"
echo ""

cd "${PROJECT_ROOT}"
exec "${VENV}/python3" scripts/local_load_generator.py \
    --supervisor-url "${SUPERVISOR_URL}" \
    --app-name "knowledge_supervisor"
