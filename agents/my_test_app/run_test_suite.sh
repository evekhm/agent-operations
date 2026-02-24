#!/usr/bin/env bash

# Wrapper script to run test_suit.py with various configuration combinations.

# Usage: ./run_test_suite.sh [-n number_active_users_for_load_test] [-f output_file]
#   -n : number_active_users_for_load_test (default: 1)
#   -f : output_file (optional text file containing pipe-separated configurations/questions, default: test_scenarios.txt)
#   -h : Show this help message
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Set defaults
NUM_USERS=1
INPUT_FILE="${SCRIPT_DIR}/test_scenarios.txt"

# Parse arguments
while getopts "n:f:h" opt; do
  case ${opt} in
    n )
      NUM_USERS=$OPTARG
      ;;
    f )
      INPUT_FILE=$OPTARG
      ;;
    h )
      echo "Usage: ./run_test_suite.sh [-n number_active_users_for_load_test] [-f output_file]"
      echo "  -n : number_active_users_for_load_test (default: 1)"
      echo "  -f : output_file (optional text file containing pipe-separated configurations/questions, default: test_scenarios.txt)"
      exit 0
      ;;
    \? )
      echo "Invalid option: -$OPTARG" 1>&2
      echo "Usage: ./run_test_suite.sh [-n number_active_users_for_load_test] [-f output_file]" 1>&2
      exit 1
      ;;
  esac
done
shift $((OPTIND -1))

START_TIME=$(date +%s)

# Load correct datastore from .env if possible (look in project root)
PROJECT_ROOT="$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")"
if [ -f "${SCRIPT_DIR}/../../.env" ]; then
    source "${SCRIPT_DIR}/../../.env"
    [ -n "$DATASTORE_ID" ] && VALID_DATASTORE="$DATASTORE_ID"
    [ -n "$WEB_DATASTORE_ID" ] && VALID_WEB_DATASTORE="$WEB_DATASTORE_ID"
elif [ -f .env ]; then
    source .env
    [ -n "$DATASTORE_ID" ] && VALID_DATASTORE="$DATASTORE_ID"
    [ -n "$WEB_DATASTORE_ID" ] && VALID_WEB_DATASTORE="$WEB_DATASTORE_ID"
fi

# Fallback for WEB_DATASTORE_ID if not in .env
if [ -z "$VALID_WEB_DATASTORE" ]; then
    VALID_WEB_DATASTORE="/Users/evekhm/projects/adk/agent_operations/project_context/search-test-docs"
fi

# Define the default region
DEFAULT_REGION="us-central1"

echo "======================================================================="
echo " Starting Stress Test Suite for my_test_app                            "
echo " Concurrent Users per test: $NUM_USERS                                 "
echo " Default Region: $DEFAULT_REGION                                       "
echo "======================================================================="

# Load scenarios
if [ -n "$INPUT_FILE" ] && [ -f "$INPUT_FILE" ]; then
    echo " Loading scenarios from file: $INPUT_FILE"
    SCENARIOS=()
    while IFS= read -r line; do
        SCENARIOS+=("$line")
    done < <(grep -v '^\s*#' "$INPUT_FILE" | grep -v '^\s*$')
else
    # Define the default scenarios to test: "SCENARIO_TARGET|MODEL_ID|AGENT_CONFIG|REGION|QUESTION1|...|QUESTION_N"
    SCENARIOS=(
        "VALID_ALL|gemini-2.5-flash|NORMAL|\$DEFAULT_REGION|What is Agent Observability top 3 features?|What tables are available in the BigQuery dataset?|Hello, my name is Alice|Write 5000 words essay about agents|Throw an exception"
        "VALID_ALL|gemini-2.5-flash|NORMAL|\$DEFAULT_REGION|Sleep 2.5 seconds|Sleep 2 seconds"
        "NOK_ADK_DATASTORE|gemini-2.5-flash|NORMAL|\$DEFAULT_REGION|How do I create a new LlmAgent with ADK?|What is the difference between ParallelAgent and SequentialAgent in ADK?"
    )
fi

for SCENARIO_RAW in "${SCENARIOS[@]}"; do
    # Strip leading/trailing quotes if user provided them
    SCENARIO="${SCENARIO_RAW%\"}"
    SCENARIO="${SCENARIO#\"}"
    
    IFS='|' read -r -a fields <<< "$SCENARIO"
    
    if [ ${#fields[@]} -lt 5 ]; then
        echo "⚠️ Skipping invalid scenario (not enough fields): $SCENARIO"
        continue
    fi
    
    # Extract baseline fields
    SCENARIO_TARGET="${fields[0]}"
    MODEL="${fields[1]}"
    CONFIG="${fields[2]}"
    CURRENT_REGION="${fields[3]}"

    # Substitute potential variables if they are literal in the scenario string
    CURRENT_REGION="${CURRENT_REGION//\$DEFAULT_REGION/$DEFAULT_REGION}"
    
    # Enforce global region for gemini-3 models, us-central1 for others
    if [[ "$MODEL" == gemini-3* ]]; then
        CURRENT_REGION="global"
    elif [[ "$CURRENT_REGION" == "\$DEFAULT_REGION" ]] || [[ "$CURRENT_REGION" == "$DEFAULT_REGION" ]]; then
        CURRENT_REGION="us-central1"
    fi
    
    CLEANUP_REPLAY=0
    FINAL_REPLAY_FILE=""

    # Handle the file or questions
    if [[ "${fields[4]}" == *.json ]]; then
        FINAL_REPLAY_FILE="${fields[4]}"
    else
        QUESTIONS=("${fields[@]:4}")
        if [ ${#QUESTIONS[@]} -eq 0 ]; then
             echo "Skipping scenario, no replay file or questions: $SCENARIO"
             continue
        fi
        
        TMP_JSON=$(mktemp)
        python3 -c "import json, sys; json.dump({'queries': sys.argv[1:], 'state': {}}, open('$TMP_JSON', 'w'))" "${QUESTIONS[@]}"
        FINAL_REPLAY_FILE="$TMP_JSON"
        CLEANUP_REPLAY=1
    fi

    # Prefix with script dir if it's a relative real json file
    if [[ "$FINAL_REPLAY_FILE" != /* ]] && [ $CLEANUP_REPLAY -eq 0 ]; then
        FINAL_REPLAY_FILE="${SCRIPT_DIR}/$FINAL_REPLAY_FILE"
    fi

    echo ""
    echo "-----------------------------------------------------------------------"
    if [ $CLEANUP_REPLAY -eq 1 ]; then
        echo "Running: TARGET=$SCENARIO_TARGET | MODEL_ID=$MODEL | AGENT_CONFIG=$CONFIG | REGION=$CURRENT_REGION | QUESTIONS=${#QUESTIONS[@]}"
    else
        echo "Running: TARGET=$SCENARIO_TARGET | MODEL_ID=$MODEL | AGENT_CONFIG=$CONFIG | REGION=$CURRENT_REGION | REPLAY_FILE=$FINAL_REPLAY_FILE"
    fi
    echo "-----------------------------------------------------------------------"

    # Export variables for the Python process to pick up based on Test Target
    if [ "$SCENARIO_TARGET" == "NOK_ADK_DATASTORE" ]; then
        echo "  -> Target: NOK ADK (Failing Vertex AI connection: invalid-adk-ds-123)"
        export DATASTORE_ID="invalid-adk-ds-123"
        export WEB_DATASTORE_ID="$VALID_WEB_DATASTORE"
    elif [ "$SCENARIO_TARGET" == "NOK_OBS_DATASTORE" ]; then
        echo "  -> Target: NOK Observability (Failing Vertex AI connection: invalid-obs-ds)"
        export DATASTORE_ID="$VALID_DATASTORE"
        export WEB_DATASTORE_ID="invalid-obs-ds"
    else
        echo "  -> Target: VALID_ALL (Using valid configured datastores for both tools)"
        export DATASTORE_ID="$VALID_DATASTORE"
        export WEB_DATASTORE_ID="$VALID_WEB_DATASTORE"
    fi

    export MODEL_ID=$MODEL
    export AGENT_CONFIG=$CONFIG
    export GCP_LOCATION=$CURRENT_REGION
    export LOCATION=$CURRENT_REGION
    export PYTHONWARNINGS="ignore"
    
    # Execute the stress test script
    python3 "${SCRIPT_DIR}/test_suit.py" "$NUM_USERS" --replay-file "$FINAL_REPLAY_FILE"
    
    # Capture exit code
    EXIT_CODE=$?
    
    if [ $EXIT_CODE -ne 0 ]; then
        echo "⚠️  Test failed or encountered an error (Exit Code: $EXIT_CODE)"
    else
        echo "✅  Test completed."
    fi
    
    if [ $CLEANUP_REPLAY -eq 1 ]; then
        rm -f "$FINAL_REPLAY_FILE"
    fi
    
    # Small delay between runs to avoid immediate rate limit spikes
    sleep 2
done


# Update the views
sh ${SCRIPT_DIR}/../../tools/update_views.sh
echo ""
echo "======================================================================="
echo " Stress Test Suite Finished!                                           "

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))
echo " Total Wall Time: ${DURATION} seconds"
echo "======================================================================="
