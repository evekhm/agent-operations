#!/bin/bash

# Script to test the deployed pto_agent

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_PATH="${SCRIPT_DIR}/../../../.env"
# Source .env file from project root if it exists
if [ -f "${ENV_PATH}" ]; then
    source "${ENV_PATH}"
fi

echo gcloud run services describe $PTO_AGENT_SERVICE_NAME --platform managed --region $PTO_AGENT_LOCATION --format 'value(status.url)' --project $PROJECT_ID
PTO_AGENT_URL=$(gcloud run services describe $PTO_AGENT_SERVICE_NAME --platform managed --region $PTO_AGENT_LOCATION --format 'value(status.url)' --project $PROJECT_ID)
ID_TOKEN=$(gcloud auth print-identity-token --quiet)

echo "Testing URL: $PTO_AGENT_URL/a2a/pto_agent/.well-known/agent-card.json"
curl -i -H "Authorization: Bearer $ID_TOKEN" $PTO_AGENT_URL/a2a/pto_agent/.well-known/agent-card.json
echo

