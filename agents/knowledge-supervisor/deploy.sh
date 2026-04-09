#!/bin/bash
# Script to deploy knowledge-supervisor agent to Agent Engine

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_PATH="${SCRIPT_DIR}/../../.env"

# Source .env file if it exists in project root to get PROJECT_ID
if [ -f "${ENV_PATH}" ]; then
    echo "Sourcing .env file from project root..."
    source "${ENV_PATH}"
else
    echo "Warning: .env file not found at ${ENV_PATH}"
fi

echo "Using Project: ${PROJECT_ID}"

# Ensure requirements.txt exists for ADK to find
if [ -f "requirements.txt" ]; then
    echo "Using existing requirements.txt..."
else
    echo "Exporting dependencies using uv..."
    uv export --no-hashes --no-header --no-dev --no-emit-project --no-annotate > requirements.txt
fi

echo "Discovering pto_agent URL..."

DISCOVERED_URL=$(gcloud run services describe "$PTO_AGENT_SERVICE_NAME" \
  --platform managed \
  --region "$PTO_AGENT_LOCATION" \
  --project="${PROJECT_ID}" \
  --format='value(status.url)')

if [ $? -ne 0 ]; then
    echo "ERROR: Failed to discover pto_agent URL!"
    echo "gcloud output: $DISCOVERED_URL"
    exit 1
fi

echo "Discovered URL: $DISCOVERED_URL"

if [[ ! "$DISCOVERED_URL" =~ ^https?:// ]]; then
    echo "ERROR: Discovered output does not look like a URL!"
    exit 1
fi

# Create a clean staging directory
STAGE_DIR="stage_tmp_$(date +%Y%m%d_%H%M%S)"
mkdir -p "${STAGE_DIR}/app"

# Copy app files to staging directory
echo "Staging files..."
cp -r app/* "${STAGE_DIR}/app/"

# Copy requirements.txt to staging root
cp requirements.txt "${STAGE_DIR}/requirements.txt"

# Create temporary env file in staging
cp "${ENV_PATH}" "${STAGE_DIR}/.env.tmp"
echo "PTO_AGENT_URL=\"$DISCOVERED_URL\"" >> "${STAGE_DIR}/.env.tmp"

# Get project number to construct service account email
PROJECT_NUMBER=$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')
SERVICE_ACCOUNT="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

echo "Granting BigQuery Data Editor and User roles to ${SERVICE_ACCOUNT}..."
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${SERVICE_ACCOUNT}" \
    --role="roles/bigquery.dataEditor" \
    --quiet
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${SERVICE_ACCOUNT}" \
    --role="roles/bigquery.user" \
    --quiet
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${SERVICE_ACCOUNT}" \
    --role="roles/bigquery.jobUser" \
    --quiet

REASONING_SA="service-${PROJECT_NUMBER}@gcp-sa-aiplatform-re.iam.gserviceaccount.com"
echo "Granting BigQuery Data Editor and User roles to ${REASONING_SA}..."
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${REASONING_SA}" \
    --role="roles/bigquery.dataEditor" \
    --quiet
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${REASONING_SA}" \
    --role="roles/bigquery.user" \
    --quiet
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${REASONING_SA}" \
    --role="roles/bigquery.jobUser" \
    --quiet

echo "Granting Discovery Engine Viewer role to ${SERVICE_ACCOUNT}..."
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${SERVICE_ACCOUNT}" \
    --role="roles/discoveryengine.viewer" \
    --quiet

echo "Granting Discovery Engine Viewer role to ${REASONING_SA}..."
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${REASONING_SA}" \
    --role="roles/discoveryengine.viewer" \
    --quiet

echo "Granting Cloud Run Invoker role to ${REASONING_SA} for ${PTO_AGENT_SERVICE_NAME}..."
gcloud run services add-iam-policy-binding "${PTO_AGENT_SERVICE_NAME}" \
    --member="serviceAccount:${REASONING_SA}" \
    --role="roles/run.invoker" \
    --region="${PTO_AGENT_LOCATION}" \
    --project="${PROJECT_ID}" \
    --quiet

# Run deployment command
REGION=${SUPERVISOR_REGION:-"us-central1"}
TOKEN=$(gcloud auth print-access-token)

echo "Searching for existing Reasoning Engine with display name 'knowledge-supervisor'..."
RESPONSE=$(curl -s -H "Authorization: Bearer ${TOKEN}" \
  "https://${REGION}-aiplatform.googleapis.com/v1/projects/${PROJECT_ID}/locations/${REGION}/reasoningEngines")

REASONING_ENGINE_ID=$(echo "$RESPONSE" | jq -r '.reasoningEngines[]? | select(.displayName == "knowledge-supervisor") | .name' | head -n 1)

if [ -n "$REASONING_ENGINE_ID" ]; then
    echo "Found existing Reasoning Engine: $REASONING_ENGINE_ID"
    echo "Updating existing Reasoning Engine..."
    adk deploy agent_engine --project="${PROJECT_ID}" --region="${REGION}" --display_name="knowledge-supervisor" --adk_app="app.agent" --adk_app_object="app" --env_file="${STAGE_DIR}/.env.tmp" --agent_engine_id="${REASONING_ENGINE_ID}" "${STAGE_DIR}"
else
    echo "No existing Reasoning Engine found with name 'knowledge-supervisor'."
    echo "Deploying to NEW Agent Engine..."
    adk deploy agent_engine --project="${PROJECT_ID}" --region="${REGION}" --display_name="knowledge-supervisor" --adk_app="app.agent" --adk_app_object="app" --env_file="${STAGE_DIR}/.env.tmp" "${STAGE_DIR}"
fi

if [ $? -ne 0 ]; then
    echo "ERROR: ADK Deployment failed!"
    rm -rf "${STAGE_DIR}"
    exit 1
fi

echo "Deployment step completed."
rm -rf "${STAGE_DIR}"
