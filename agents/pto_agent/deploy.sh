# 1. Configuration Check
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

ENV_PATH="$SCRIPT_DIR/../../.env"
if [ -f "$ENV_PATH" ]; then
    source "$ENV_PATH"
else
    echo "WARNING: .env file not found at $ENV_PATH"
fi


# Get project number for service account
PROJECT_NUMBER=$(gcloud projects describe ${PROJECT_ID} --format="value(projectNumber)" --quiet)
SERVICE_ACCOUNT="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

echo "Ensuring Storage Object Viewer permission for Cloud Build..."
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
    --member="serviceAccount:${SERVICE_ACCOUNT}" \
    --role="roles/storage.objectViewer" --quiet

echo "Ensuring Artifact Registry Writer permission for Cloud Build..."
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
    --member="serviceAccount:${SERVICE_ACCOUNT}" \
    --role="roles/artifactregistry.writer" --quiet

echo "Ensuring Logs Writer permission for Cloud Build..."
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
    --member="serviceAccount:${SERVICE_ACCOUNT}" \
    --role="roles/logging.logWriter" --quiet

echo "Ensuring Vertex AI User permission for Cloud Run..."
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
    --member="serviceAccount:${SERVICE_ACCOUNT}" \
    --role="roles/aiplatform.user" --quiet

adk deploy cloud_run --project=${PROJECT_ID} --region=${DATASET_LOCATION} \
    --service_name=${PTO_AGENT_SERVICE_NAME} \
    --a2a --with_ui "${SCRIPT_DIR}"/ \
    -- --no-allow-unauthenticated --set-env-vars="TEST_DATASET_LOCATION=${TEST_DATASET_LOCATION},TEST_DATASET_ID=${TEST_DATASET_ID},TEST_TABLE_ID=${TEST_TABLE_ID},PTO_MODEL_ID=${PTO_MODEL_ID},PTO_AGENT_LOCATION=${PTO_AGENT_LOCATION}"
