# 1. Configuration Check
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -f "$SCRIPT_DIR/.env" ]; then
    source "$SCRIPT_DIR/.env"
else
    echo "WARNING: .env file not found at $SCRIPT_DIR/.env"
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

SERVICE_NAME=$(basename "agents/agent2-server")

adk deploy cloud_run --project=${PROJECT_ID} --region=${DATASET_LOCATION} \
    --service_name=${SERVICE_NAME} \
    --a2a --with_ui agents/agent2-server/ \
    -- --no-allow-unauthenticated --set-env-vars="DATASET_LOCATION=${DATASET_LOCATION},DATASET_ID=${DATASET_ID},TABLE_ID=${TABLE_ID}"
