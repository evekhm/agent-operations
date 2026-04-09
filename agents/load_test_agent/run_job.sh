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

gcloud run jobs execute knowledge-supervisor-test \
  --project=$PROJECT_ID \
  --region=$REGION \
  --update-env-vars="^|^CONCURRENCY=10|DURATION_MINUTES=60|TOPICS_CONFIG=paid time off calculations:50,new hiring and onboarding:10"
