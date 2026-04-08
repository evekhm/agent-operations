#!/bin/bash
# Script to deploy the test agent as a Cloud Run Job

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_PATH="${SCRIPT_DIR}/../../.env"
PWD=`(pwd)`
# Source .env file if it exists in project root
if [ -f "${ENV_PATH}" ]; then
    source "${ENV_PATH}"
else
    echo "Warning: .env file not found at ${ENV_PATH}"
fi

# Navigate to agent directory for build
cd "${SCRIPT_DIR}"


JOB_NAME="knowledge-supervisor-test"
IMAGE_NAME="$REGION-docker.pkg.dev/$PROJECT_ID/cloud-run-source-deploy/load-test-job"

echo "Building image with Cloud Build..."
echo "Project: $PROJECT_ID"
echo "Image: $IMAGE_NAME"

gcloud builds submit --tag "$IMAGE_NAME" \
  --project="$PROJECT_ID" \
  .

# Generate resolved env file to avoid quoting issues
cat <<EOF > resolved_env.yaml
PROJECT_ID: "$PROJECT_ID"
REGION: "$REGION"
CONCURRENCY: "${CONCURRENCY:-2}"
DURATION_MINUTES: "${DURATION_MINUTES:-5}"
TOPICS_CONFIG: "${TOPICS_CONFIG:-paid time off calculations:5}"
EOF

gcloud run jobs deploy "$JOB_NAME" \
  --image "$IMAGE_NAME" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --env-vars-file=resolved_env.yaml

rm resolved_env.yaml

echo "Deployment complete. You can run the job using:"
echo "gcloud run jobs execute $JOB_NAME --project=$PROJECT_ID --region=$REGION"
echo ""
echo "To override parameters on the fly (using the new format):"
echo "gcloud run jobs execute $JOB_NAME --project=$PROJECT_ID --region=$REGION --update-env-vars=\"TOPICS_CONFIG='pto and hiring:5,general knowledge:3',CONCURRENCY=5\""

cd "${PWD}"