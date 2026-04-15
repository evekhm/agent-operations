#!/bin/bash
# Send a query to the deployed knowledge-supervisor Reasoning Engine.
#
# Usage:
#   bash test_remote.sh                                  # default test queries
#   bash test_remote.sh -q "How many PTO days left?"     # custom query

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_PATH="${SCRIPT_DIR}/../../../.env"

if [ -f "${ENV_PATH}" ]; then
    source "${ENV_PATH}"
fi

PROJECT="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null)}"
LOCATION="${SUPERVISOR_REGION:-us-central1}"
DISPLAY_NAME="knowledge-supervisor"
echo PROJECT=${PROJECT_ID}

# Parse arguments
QUERY=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        -q|--query)
            QUERY="$2"
            shift 2
            ;;
        *)
            echo "Usage: $0 [-q \"your question\"]"
            exit 1
            ;;
    esac
done

# Discover Reasoning Engine by display name
echo "Discovering Reasoning Engine '${DISPLAY_NAME}' in ${PROJECT}/${LOCATION}..."
TOKEN=$(gcloud auth print-access-token)
RESPONSE=$(curl -s -H "Authorization: Bearer ${TOKEN}" \
    "https://${LOCATION}-aiplatform.googleapis.com/v1/projects/${PROJECT}/locations/${LOCATION}/reasoningEngines")

ENGINE_ID=$(echo "$RESPONSE" | jq -r ".reasoningEngines[]? | select(.displayName == \"${DISPLAY_NAME}\") | .name" | head -n 1)

if [ -z "$ENGINE_ID" ]; then
    echo "ERROR: No Reasoning Engine found with display name '${DISPLAY_NAME}'!"
    exit 1
fi
echo "Found: ${ENGINE_ID}"
echo ""

send_query() {
    local q="$1"
    echo "─────────────────────────────────────────"
    echo "Q: ${q}"
    echo "─────────────────────────────────────────"
    RESULT=$(curl -s -H "Authorization: Bearer ${TOKEN}" \
         -H "Content-Type: application/json" \
         "https://${LOCATION}-aiplatform.googleapis.com/v1/${ENGINE_ID}:query" \
         -d "{\"class_method\": \"query\", \"input\": {\"query\": \"${q}\"}}")
    echo "$RESULT" | jq -r '.output // .' 2>/dev/null || echo "$RESULT"
    echo ""
}

if [ -n "$QUERY" ]; then
    send_query "$QUERY"
else
    send_query "Hi how many PTO days are left"
    send_query "What are the open hiring contexts?"
fi
