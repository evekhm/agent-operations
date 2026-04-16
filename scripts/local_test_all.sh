#!/bin/bash
# =============================================================================
# Local End-to-End Test
# =============================================================================
# Starts ALL agents on a single ADK API server (with A2A for PTO), then runs
# the load generator against the knowledge_supervisor.
# No cloud deployments needed.
#
# Usage:
#   ./scripts/local_test_all.sh                # defaults: 3 concurrency, 5 min
#   CONCURRENCY=1 DURATION_MINUTES=2 ./scripts/local_test_all.sh  # quick smoke test
#   ./scripts/local_test_all.sh --interactive   # start agents, then test manually
#
# Port: localhost:8000 (all agents)
#
# To stop everything: Ctrl+C (cleanup is automatic)
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${SCRIPT_DIR}/.."
VENV="${PROJECT_ROOT}/.venv/bin"

# Source .env
if [ -f "${PROJECT_ROOT}/.env" ]; then
    source "${PROJECT_ROOT}/.env"
fi

SERVER_PORT=${SERVER_PORT:-8000}

# Point knowledge_supervisor to the local PTO agent (same server, A2A enabled)
export PTO_AGENT_URL="http://localhost:${SERVER_PORT}"

# Ensure aiohttp is available
"${VENV}/pip" show aiohttp > /dev/null 2>&1 || {
    echo "Installing aiohttp (needed for local load generator)..."
    "${VENV}/pip" install aiohttp -q
}

# Cleanup function
SERVER_PID=""

cleanup() {
    echo ""
    echo "=== Shutting down ==="
    [ -n "$SERVER_PID" ] && kill "$SERVER_PID" 2>/dev/null && echo "Stopped ADK server (PID $SERVER_PID)"
    wait 2>/dev/null
    echo "Done."
}
trap cleanup EXIT INT TERM

# ---- Step 1: Start ADK API Server (all agents) ----
echo "=== [1/2] Starting ADK API Server on port ${SERVER_PORT} ==="
echo "  PTO_AGENT_URL: ${PTO_AGENT_URL}"
echo "  Agents dir:    ${PROJECT_ROOT}/agents/"
echo ""

cd "${PROJECT_ROOT}"
"${VENV}/adk" api_server \
    --port "${SERVER_PORT}" \
    --a2a \
    --auto_create_session \
    agents/ > /tmp/adk_server.log 2>&1 &
SERVER_PID=$!
echo "Server PID: ${SERVER_PID} (logs: /tmp/adk_server.log)"

# Wait for server to be ready
echo -n "Waiting for server..."
for i in $(seq 1 60); do
    if curl -s "http://localhost:${SERVER_PORT}/list-apps" > /dev/null 2>&1; then
        echo " ready!"
        APPS=$(curl -s "http://localhost:${SERVER_PORT}/list-apps")
        echo "  Available apps: ${APPS}"
        break
    fi
    if ! kill -0 "$SERVER_PID" 2>/dev/null; then
        echo " FAILED (process died)"
        echo "Last logs:"
        tail -30 /tmp/adk_server.log
        exit 1
    fi
    echo -n "."
    sleep 1
done

echo ""
echo "=== Server running at http://localhost:${SERVER_PORT} ==="
echo ""

# ---- Interactive mode ----
if [ "$1" = "--interactive" ]; then
    echo "Interactive mode — all agents are running. Test examples:"
    echo ""
    echo "  # PTO balance:"
    echo "  curl -s http://localhost:${SERVER_PORT}/run -H 'Content-Type: application/json' \\"
    echo "    -d '{\"app_name\":\"knowledge_supervisor\",\"user_id\":\"test\",\"session_id\":\"s1\",\"new_message\":{\"role\":\"user\",\"parts\":[{\"text\":\"How many PTO days do I have?\"}]},\"streaming\":false}'"
    echo ""
    echo "  # Sick leave:"
    echo "  curl -s http://localhost:${SERVER_PORT}/run -H 'Content-Type: application/json' \\"
    echo "    -d '{\"app_name\":\"knowledge_supervisor\",\"user_id\":\"test\",\"session_id\":\"s2\",\"new_message\":{\"role\":\"user\",\"parts\":[{\"text\":\"What is my sick leave balance?\"}]},\"streaming\":false}'"
    echo ""
    echo "  # Company policy:"
    echo "  curl -s http://localhost:${SERVER_PORT}/run -H 'Content-Type: application/json' \\"
    echo "    -d '{\"app_name\":\"knowledge_supervisor\",\"user_id\":\"test\",\"session_id\":\"s3\",\"new_message\":{\"role\":\"user\",\"parts\":[{\"text\":\"What is the expense report policy?\"}]},\"streaming\":false}'"
    echo ""
    echo "  # Run load test separately:"
    echo "  SERVER_PORT=${SERVER_PORT} ./scripts/local_test_load.sh"
    echo ""
    echo "Press Ctrl+C to stop."
    wait
    exit 0
fi

# ---- Step 2: Run Load Test ----
echo "=== [2/2] Running Load Test ==="
echo ""

export CONCURRENCY=${CONCURRENCY:-3}
export DURATION_MINUTES=${DURATION_MINUTES:-5}
export TOPICS_CONFIG=${TOPICS_CONFIG:-'pto and sick leave balances:3,vacation planning and working days:2,company policies and HR procedures:2,ADK documentation and tools:2,general knowledge and technology:2,database lookups and calculations:1,Google Cloud and GCP services:2'}

"${VENV}/python3" "${SCRIPT_DIR}/local_load_generator.py" \
    --supervisor-url "http://localhost:${SERVER_PORT}" \
    --app-name "knowledge_supervisor"

echo ""
echo "=== Load test complete ==="
echo "Server logs: /tmp/adk_server.log"
