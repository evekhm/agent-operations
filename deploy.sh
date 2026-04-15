#!/bin/bash
set -eo pipefail

# 1. Configuration Check
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -f "$SCRIPT_DIR/.env" ]; then
    source "$SCRIPT_DIR/.env"
else
    echo "WARNING: .env file not found at $SCRIPT_DIR/.env"
fi

# Deploy pto-agent A2A to Cloud Run
echo "Deploying pto_agent..."
(cd "$SCRIPT_DIR/agents/pto_agent" && ./deploy.sh)

# Deploy knowledge_supervisor to Agent Engine
echo "Deploying knowledge_supervisor..."
(cd "$SCRIPT_DIR/agents/knowledge_supervisor" && ./deploy.sh)

# Deploy Load Tester as Cloud Run Job
echo "Load Tester..."
(cd "$SCRIPT_DIR/agents/load_test_agent" && ./deploy.sh)
