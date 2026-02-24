#!/bin/bash
set -eo pipefail

echo "=========================================================="
echo "    Datastore Setup Script for Observability Agent        "
echo "=========================================================="

# 1. Configuration Check
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -f "$SCRIPT_DIR/.env" ]; then
    source "$SCRIPT_DIR/.env"
else
    echo "WARNING: .env file not found at $SCRIPT_DIR/.env"
fi

DOCS_PATH="$SCRIPT_DIR/project_context/search-test-docs"
if [ ! -d "$DOCS_PATH" ]; then
    echo "ERROR: Directory $DOCS_PATH not found!"
    exit 1
fi

# Get the active project from gcloud
PROJECT_ID=$(gcloud config get-value project)
if [ -z "$PROJECT_ID" ]; then
    echo "ERROR: Could not determine PROJECT_ID. Please run 'gcloud config set project <your-project-id>'."
    exit 1
fi

# Define the region for Vertex AI Search
REGION=${SEARCH_APP_REGION:-"global"}
BUCKET_NAME="gs://${PROJECT_ID}-obs-docs"
BQ_LOCATION=$DATASET_LOCATION

echo "Project ID:          $PROJECT_ID"
echo "Datastore Region:    $REGION"
echo "BQ Location Region:  $BQ_LOCATION"
echo "Bucket Name:         $BUCKET_NAME"
echo "Data Store ID:       $DATASTORE_ID"
echo "Web Data Store ID:   $WEB_DATASTORE_ID"
echo "----------------------------------------------------------"

ACCESS_TOKEN=$(gcloud auth print-access-token)
# Define the APIs needed for the project
APIS=(
  "discoveryengine.googleapis.com"        # For specialized GenAI search and applications
  "aiplatform.googleapis.com"            # For Vertex AI: model hosting, MLOps, and vector databases
  "artifactregistry.googleapis.com"      # For storing and managing container images (Docker/OCI)
  "cloudbuild.googleapis.com"            # For building and testing code/containers
  "run.googleapis.com"                   # For deploying serverless containers (like your agent)
  "iam.googleapis.com"                   # For managing Identity and Access Management (Permissions)
  "cloudresourcemanager.googleapis.com"   # For managing projects, folders, and organizations
  "iap.googleapis.com"                    # For IAP
)

echo "Starting Google Cloud API enablement process..."
for API in "${APIS[@]}"; do
  echo "Enabling $API..."

  # Request enablement for the API in the background (--async)
  gcloud services enable "$API" --async

  # Check the exit status of the previous command
  if [ $? -eq 0 ]; then
    :
  else
    echo "  -> ERROR: Failed to submit enablement request for $API."
    exit 1
  fi
done
sleep 10

# Create BigQuery Dataset
echo "Creating BigQuery Dataset (if it doesn't exist)..."
if [ -n "$DATASET_ID" ]; then
    bq show --dataset "${PROJECT_ID}:${DATASET_ID}" >/dev/null 2>&1 || {
        echo "Dataset ${DATASET_ID} not found. Creating..."
        bq mk --location="${BQ_LOCATION}" --dataset "${PROJECT_ID}:${DATASET_ID}"
    }
else
    echo "WARNING: DATASET_ID not set in .env. Skipping dataset creation."
fi

# Create GCS Buckets
echo "Creating GCS Bucket..."
gcloud storage buckets create "$GOOGLE_CLOUD_STAGING_BUCKET" --location="$LOCATION" --project="$PROJECT_ID" || {
    echo "Failed to create bucket. It might already exist or you lack permissions."
}
gcloud storage buckets create "$BUCKET_NAME" --location="$LOCATION" --project="$PROJECT_ID" || {
    echo "Failed to create bucket. It might already exist or you lack permissions."
}

# Copy docs into it
echo "Copying documents to GCS Bucket..."
gcloud storage cp -r "$DOCS_PATH"/* "$BUCKET_NAME"

ACCESS_TOKEN=$(gcloud auth print-access-token)

# 5. Create Vertex AI Search Datastore
echo "Creating Vertex AI Data Store for pdf documents..."
curl -s -X POST \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Content-Type: application/json" \
  -H "X-Goog-User-Project: ${PROJECT_ID}" \
  "https://discoveryengine.googleapis.com/v1alpha/projects/${PROJECT_ID}/locations/${REGION}/collections/default_collection/dataStores?dataStoreId=${DATASTORE_ID}" \
  -d '{
    "displayName": "'"${DATASTORE_ID}"'",
    "industryVertical": "GENERIC",
    "solutionTypes": ["SOLUTION_TYPE_SEARCH"],
    "contentConfig": "CONTENT_REQUIRED",
    "documentProcessingConfig": {
        "chunkingConfig": {
            "layoutBasedChunkingConfig": {}
        }
    }
}'

echo ""
echo "Waiting for datastore creation to propagate (15 seconds)..."
sleep 15

# 6. Import data from GCS into Datastore
echo "Importing documents from GCS into Data Store..."

curl -s -X POST \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Content-Type: application/json" \
  -H "X-Goog-User-Project: ${PROJECT_ID}" \
  "https://discoveryengine.googleapis.com/v1alpha/projects/${PROJECT_ID}/locations/${REGION}/collections/default_collection/dataStores/${DATASTORE_ID}/branches/default_branch/documents:import" \
  -d '{
    "gcsSource": {
      "inputUris": ["'"${BUCKET_NAME}"'/*"],
      "dataSchema": "content"
    },
    "reconciliationMode": "INCREMENTAL"
}'

echo ""


#  Create Vertex AI Web Data Store
echo "Creating Vertex AI Web Data Store for ADK web site index..."
if [ -z "$ACCESS_TOKEN" ]; then
    ACCESS_TOKEN=$(gcloud auth print-access-token)
fi
curl -s -X POST \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Content-Type: application/json" \
  -H "X-Goog-User-Project: ${PROJECT_ID}" \
  "https://discoveryengine.googleapis.com/v1alpha/projects/${PROJECT_ID}/locations/${REGION}/collections/default_collection/dataStores?dataStoreId=${WEB_DATASTORE_ID}" \
  -d '{
    "displayName": "'"${WEB_DATASTORE_ID}"'",
    "industryVertical": "GENERIC",
    "solutionTypes": ["SOLUTION_TYPE_SEARCH"],
    "contentConfig": "PUBLIC_WEBSITE"
}'

echo ""
echo "Waiting for web datastore creation to propagate (15 seconds)..."
sleep 15

# 8. Add target site to Web Data Store
echo "Registering ADK documentation web link to Web Data Store..."
curl -s -X POST \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Content-Type: application/json" \
  -H "X-Goog-User-Project: ${PROJECT_ID}" \
  "https://discoveryengine.googleapis.com/v1alpha/projects/${PROJECT_ID}/locations/${REGION}/collections/default_collection/dataStores/${WEB_DATASTORE_ID}/siteSearchEngine/targetSites" \
  -d '{
    "providedUriPattern": "www.google.github.io/adk-docs/*",
    "type": "INCLUDE",
    "exactMatch": false
}'

echo ""
echo "=========================================================="
echo "Setup Complete!"
echo "Data store creation and import process started."
echo "=========================================================="
echo ""


#TODO via service account
# Required permission for BigQuery Access for BQ Plugin
# gcloud projects add-iam-policy-binding <PROJECT_ID> \
  #    --member="serviceAccount:<SERVICE_ACCOUNT_EMAIL>" \
  #    --role="roles/bigquery.dataEditor" \
  #    --condition=None


# You need to assign the roles/bigquery.dataEditor role to your Agent's Service Account. This role is a "one-stop shop" for this issue because it includes:
  #bigquery.tables.updateData: Allows appending rows.
  #bigquery.tables.get: Allows the agent to see the table schema.
  #bigquery.tables.create: Necessary if your plugin needs to build the table from scratch.
  #A