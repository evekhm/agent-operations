#!/usr/bin/env bash

# Wrapper script to run stress_test.py with various configuration combinations.

# Usage: ./run_stress_test_suite.sh [NUM_USERS]
# If NUM_USERS is not provided, it defaults to 2 concurrent users.

NUM_USERS=${1:-2}

# Define the matrix of configurations to test
# These map directly to the configurations defined in agent.py
AGENT_CONFIGS=("OK_CONFIG2" "OK_CONFIG1" "WRONG_CONFIG1" "WRONG_CONFIG2")

# Define the models to test
MODELS=("gemini-3-pro-preview" "gemini-2.5-pro")

# Define the default region
DEFAULT_REGION="us-central1"

echo "======================================================================="
echo " Starting Stress Test Suite for my_test_app                            "
echo " Concurrent Users per test: $NUM_USERS                                 "
echo " Default Region: $DEFAULT_REGION                                       "
echo "======================================================================="

for MODEL in "${MODELS[@]}"; do
    for CONFIG in "${AGENT_CONFIGS[@]}"; do
        
        # Gemini 3 models require the 'global' region
        if [[ "$MODEL" == *"gemini-3"* ]]; then
            CURRENT_REGION="global"
        else
            CURRENT_REGION=$DEFAULT_REGION
        fi

        echo ""
        echo "-----------------------------------------------------------------------"
        echo "Running: MODEL_ID=$MODEL | AGENT_CONFIG=$CONFIG | REGION=$CURRENT_REGION"
        echo "-----------------------------------------------------------------------"
        
        # Export variables for the Python process to pick up
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
done

echo ""
echo "======================================================================="
echo " Stress Test Suite Finished!                                           "
echo "======================================================================="
