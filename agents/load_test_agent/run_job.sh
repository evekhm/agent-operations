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

DURATION_MINUTES=60
TIMEOUT_SECONDS=$(( (DURATION_MINUTES + 10) * 60 ))

gcloud run jobs execute knowledge-supervisor-test \
  --project=$PROJECT_ID \
  --region=$REGION \
  --task-timeout="${TIMEOUT_SECONDS}s" \
  --update-env-vars="^|^CONCURRENCY=10|DURATION_MINUTES=${DURATION_MINUTES}|TOPICS_CONFIG=paid time off calculations:10,ADK documentation and tools:10,AI observability and tracing:10,BigQuery data analysis:10,general knowledge search:10,database lookups and item retrieval:5,complex calculations:5,internal company policies and HR procedures:10"
