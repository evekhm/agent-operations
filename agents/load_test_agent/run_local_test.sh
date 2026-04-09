#!/bin/bash
# Script to run the load test locally

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_PATH="${SCRIPT_DIR}/../../.env"

# Source .env file if it exists in project root
if [ -f "${ENV_PATH}" ]; then
    source "${ENV_PATH}"
else
    echo "Warning: .env file not found at ${ENV_PATH}"
fi

# Set default env vars if not provided
export TOPICS_CONFIG=${TOPICS_CONFIG:-'paid time off calculations:3,ADK documentation and tools:2,BigQuery data analysis:2,general knowledge search:2,database lookups:1'}
export CONCURRENCY=${CONCURRENCY:-3}
export DURATION_MINUTES=${DURATION_MINUTES:-5}
export PYTHONPATH="${SCRIPT_DIR}/../..:${PYTHONPATH}"

# Dynamically fetch PTO_AGENT_URL if not set
if [ -z "$PTO_AGENT_URL" ]; then
    echo "Fetching PTO_AGENT_URL dynamically..."
    PROJECT_ID=${PROJECT_ID:-${GOOGLE_CLOUD_PROJECT:-$(gcloud config get-value project)}}
    REGION="us-central1" # Default region for this project
    
    PTO_AGENT_URL=$(gcloud run services describe "$PTO_AGENT_SERVICE_NAME" \
      --project="$PROJECT_ID" \
      --region="$REGION" \
      --format="value(status.url)" 2>/dev/null)
      
    if [ -z "$PTO_AGENT_URL" ]; then
        echo "WARNING: Failed to fetch PTO_AGENT_URL dynamically. Falling back to localhost:8000"
        PTO_AGENT_URL="http://localhost:8000"
    else
        echo "Discovered PTO_AGENT_URL: $PTO_AGENT_URL"
    fi
fi
export PTO_AGENT_URL

echo "--- Starting Local Load Test ---"
echo "TOPICS_CONFIG: $TOPICS_CONFIG"
echo "CONCURRENCY: $CONCURRENCY"
echo "DURATION_MINUTES: $DURATION_MINUTES"
echo "PTO_AGENT_URL: $PTO_AGENT_URL"
echo "--------------------------------"

# Run from project root to ensure imports work correctly
cd "${SCRIPT_DIR}/../.."
python3 agents/load_test_agent/load_generator.py
