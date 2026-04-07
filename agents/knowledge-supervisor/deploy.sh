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

PROJECT=${PROJECT_ID:-"agent-operations-ek-05"}
echo "Using Project: ${PROJECT}"

# Export dependencies to requirements file using uv export.
echo "Exporting dependencies..."
uv export --no-hashes --no-header --no-dev --no-emit-project --no-annotate > app/app_utils/.requirements.txt

# Run deployment command
echo "Deploying to Agent Engine..."
uv run -m app.app_utils.deploy \
    --source-packages=./app \
    --entrypoint-module=app.agent_engine_app \
    --entrypoint-object=agent_engine \
    --requirements-file=app/app_utils/.requirements.txt \
    --project="${PROJECT}"
