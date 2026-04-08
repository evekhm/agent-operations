#!/bin/bash
# Script to deploy knowledge_supervisor agent to Agent Engine

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_PATH="${SCRIPT_DIR}/../../.env"
TEMP_ENV_PATH="${SCRIPT_DIR}/.env.tmp"

# Source .env file if it exists in project root
if [ -f "${ENV_PATH}" ]; then
    echo "Sourcing .env file..."
    source "${ENV_PATH}"
    cp "${ENV_PATH}" "${TEMP_ENV_PATH}"
else
    echo "Creating empty temp env file..."
    touch "${TEMP_ENV_PATH}"
fi

echo "Discovering pto_agent URL..."
DISCOVERED_URL=$(gcloud run services describe "$PTO_AGENT_SERVICE_NAME" \
  --platform managed \
  --region "${PTO_AGENT_LOCATION:-us-central1}" \
  --project="$PROJECT_ID" \
  --format='value(status.url)')
echo "Discovered URL: $DISCOVERED_URL"

echo "" >> "${TEMP_ENV_PATH}"
echo "PTO_AGENT_URL=\"$DISCOVERED_URL\"" >> "${TEMP_ENV_PATH}"

REGION=${SUPERVISOR_REGION:-"us-central1"}

echo "Deploying knowledge_supervisor to Agent Engine..."
echo "Project: $PROJECT_ID"
echo "Region: $REGION"

# Run deployment command from the parent directory
cd "$(dirname "$0")/.."

# Create a clean staging directory to preserve package structure
STAGE_DIR="stage_tmp_$(date +%Y%m%d_%H%M%S)"
mkdir -p "${STAGE_DIR}/knowledge_supervisor"

# Copy files to staging directory
cp -r knowledge_supervisor/* "${STAGE_DIR}/knowledge_supervisor/"

# Clean up __pycache__ in staging
find "${STAGE_DIR}" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null

# Copy temp env file to staging package directory
cp "${TEMP_ENV_PATH}" "${STAGE_DIR}/knowledge_supervisor/.env.tmp"

# Copy requirements.txt to staging root so ADK finds it
cp "knowledge_supervisor/requirements.txt" "${STAGE_DIR}/requirements.txt"

adk deploy agent_engine --project="$PROJECT_ID" --region="$REGION" --display_name="$SUPERVISOR_DISPLAY_NAME" --adk_app="knowledge_supervisor.agent" --adk_app_object="app" --env_file="${STAGE_DIR}/knowledge_supervisor/.env.tmp" "${STAGE_DIR}"

# Clean up local temp files
rm -rf "${STAGE_DIR}"
rm "${TEMP_ENV_PATH}"
