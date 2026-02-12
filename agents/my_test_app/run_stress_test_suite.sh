#!/usr/bin/env bash

# Wrapper script to run stress_test.py with various configuration combinations.

# Usage: ./run_stress_test_suite.sh [NUM_USERS]
# If NUM_USERS is not provided, it defaults to 2 concurrent users.

NUM_USERS=${1:-2}

START_TIME=$(date +%s)

# Load correct datastore from .env if possible
if [ -f .env ]; then
    source .env
    [ -n "$DATASTORE_ID" ] && VALID_DATASTORE="$DATASTORE_ID"
fi

# Define the default region
DEFAULT_REGION="us-central1"

echo "======================================================================="
echo " Starting Stress Test Suite for my_test_app                            "
echo " Concurrent Users per test: $NUM_USERS                                 "
echo " Default Region: $DEFAULT_REGION                                       "
echo "======================================================================="

# Define the scenarios to test: "DATASTORE_ID|MODEL_ID|AGENT_CONFIG|REGION"
SCENARIOS=(
    "$VALID_DATASTORE|gemini-2.5-flash|OK_CONFIG1|$DEFAULT_REGION"
    "$VALID_DATASTORE|gemini-2.5-pro|OK_CONFIG1|$DEFAULT_REGION"
    "dummy-datastore-12345|gemini-2.5-flash|OK_CONFIG1|$DEFAULT_REGION"
    "$VALID_DATASTORE|gemini-2.5-flash|WRONG_CONFIG1|$DEFAULT_REGION"
    "$VALID_DATASTORE|gemini-3-pro-preview|OK_CONFIG1|global"
    "dummy-datastore-12345|gemini-3-pro-preview|OK_CONFIG1|global"
)

for SCENARIO in "${SCENARIOS[@]}"; do
    IFS='|' read -r DATASTORE MODEL CONFIG CURRENT_REGION <<< "$SCENARIO"

    echo ""
    echo "-----------------------------------------------------------------------"
    echo "Running: DATASTORE_ID=$DATASTORE | MODEL_ID=$MODEL | AGENT_CONFIG=$CONFIG | REGION=$CURRENT_REGION"
    echo "-----------------------------------------------------------------------"
    
    # Export variables for the Python process to pick up
    export DATASTORE_ID=$DATASTORE
    export MODEL_ID=$MODEL
    export AGENT_CONFIG=$CONFIG
    export GCP_LOCATION=$CURRENT_REGION
    export PYTHONWARNINGS="ignore"
    
    # Execute the stress test script
    python agents/my_test_app/stress_test.py "$NUM_USERS"
    
    # Capture exit code
    EXIT_CODE=$?
    
    if [ $EXIT_CODE -ne 0 ]; then
        echo "⚠️  Test failed or encountered an error (Exit Code: $EXIT_CODE)"
    else
        echo "✅  Test completed."
    fi
    
    # Small delay between runs to avoid immediate rate limit spikes
    sleep 2
done

echo ""
echo "======================================================================="
echo " Stress Test Suite Finished!                                           "

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))
echo " Total Wall Time: ${DURATION} seconds"
echo "======================================================================="
