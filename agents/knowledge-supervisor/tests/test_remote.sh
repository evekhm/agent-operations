#!/bin/bash

# Script to test the deployed knowledge-supervisor agent

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Source .env file from project root if it exists
if [ -f "${SCRIPT_DIR}/../../.env" ]; then
    source "${SCRIPT_DIR}/../../.env"
fi

PROJECT="${PROJECT_ID:-$(gcloud config get-value project)}"
LOCATION="${SUPERVISOR_REGION:-us-central1}"

# Get the reasoning engine ID using display name if not provided
if [ -z "$1" ]; then
    echo "Searching for Reasoning Engine with display name 'knowledge-supervisor'..."
    TOKEN=$(gcloud auth print-access-token)
    RESPONSE=$(curl -s -H "Authorization: Bearer ${TOKEN}" \
        "https://${LOCATION}-aiplatform.googleapis.com/v1/projects/${PROJECT}/locations/${LOCATION}/reasoningEngines")
    
    ENGINE_ID=$(echo "$RESPONSE" | grep -B 2 '"displayName": "knowledge-supervisor"' | grep '"name":' | head -n 1 | sed -E 's/.*"name": "(.*)".*/\1/')
    
    if [ -z "$ENGINE_ID" ]; then
        echo "ERROR: No Reasoning Engine found with name 'knowledge-supervisor'!"
        exit 1
    fi
    echo "Using discovered engine ID: $ENGINE_ID"
else
    ENGINE_ID="$1"
fi

echo "Sending query 'Hi how many PTO days are left' to $ENGINE_ID..."

curl -s -H "Authorization: Bearer $(gcloud auth print-access-token)" \
     -H "Content-Type: application/json" \
     "https://${LOCATION}-aiplatform.googleapis.com/v1/${ENGINE_ID}:query" \
     -d '{"class_method": "query", "input": {"query": "Hi how many PTO days are left"}}'

echo -e "\n----------------------------------------\n"

echo "Sending query 'What are the open hiring contexts?' to $ENGINE_ID..."

curl -s -H "Authorization: Bearer $(gcloud auth print-access-token)" \
     -H "Content-Type: application/json" \
     "https://${LOCATION}-aiplatform.googleapis.com/v1/${ENGINE_ID}:query" \
     -d '{"class_method": "query", "input": {"query": "What are the open hiring contexts?"}}'

echo ""
