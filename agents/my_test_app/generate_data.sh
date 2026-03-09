#!/usr/bin/env bash

# Wrapper script to run generate_data.py with various configuration combinations.

# Usage: ./generate_data.sh [-n number_active_users_for_load_test] [-f output_file]
#   -n : number_active_users_for_load_test (default: 5)
#   -f : scenarios_file (optional text file containing pipe-separated configurations/questions, default: test_scenarios.txt)
#   -h : Show this help message
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Set defaults
NUM_USERS=5
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
      echo "Usage: ./generate_data.sh [-n number_active_users_for_load_test] [-f scenarios_file]"
      echo "  -n : number_active_users_for_load_test (default: 5)"
      echo "  -f : scenarios_file (optional text file containing pipe-separated configurations/questions, default: test_scenarios.txt)"
      exit 0
      ;;
    \? )
      echo "Invalid option: -$OPTARG" 1>&2
      echo "Usage: ./generate_data.sh [-n number_active_users_for_load_test] [-f scenarios_file]" 1>&2
      exit 1
      ;;
  esac
done
shift $((OPTIND -1))

START_TIME=$(date +%s)

# Load correct datastore from .env if possible (look in project root)
PROJECT_ROOT="$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")"
if [ -f "${SCRIPT_DIR}/../../.env" ]; then
    source "${SCRIPT_DIR}/../../.env" 2>/dev/null || true
    [ -n "$DATASTORE_ID" ] && export DATASTORE_ID="$DATASTORE_ID"
    [ -n "$WEB_DATASTORE_ID" ] && export WEB_DATASTORE_ID="$WEB_DATASTORE_ID"
elif [ -f .env ]; then
    source .env
    [ -n "$DATASTORE_ID" ] && export DATASTORE_ID="$DATASTORE_ID"
    [ -n "$WEB_DATASTORE_ID" ] && export WEB_DATASTORE_ID="$WEB_DATASTORE_ID"
fi

# Fallback for WEB_DATASTORE_ID if not in .env
if [ -z "$WEB_DATASTORE_ID" ]; then
    export WEB_DATASTORE_ID="/Users/evekhm/projects/adk/agent_operations/project_context/search-test-docs"
fi

# Define the default region
DEFAULT_REGION="us-central1"

echo "======================================================================="
echo " Starting Stress Test Suite for my_test_app                            "
echo " Concurrent Workers: $NUM_USERS                                        "
echo " Scenarios File: $INPUT_FILE                                           "
echo " Default Region: $DEFAULT_REGION                                       "
echo "======================================================================="

export PYTHONWARNINGS="ignore"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Create logs directory if it doesn't exist
LOGS_DIR="${SCRIPT_DIR}/../../logs"
mkdir -p "${LOGS_DIR}"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
SCRIPT_LOG="${LOGS_DIR}/data_${TIMESTAMP}.log"

# Get relative path for display
SCRIPT_LOG_REL=$(python3 -c "import os; print(os.path.normpath(os.path.relpath('${SCRIPT_LOG}')))")

# Run the agent with caching enabled (replaces adk run) and pipe to tee
echo -e "${GREEN}Script output being saved to: ${SCRIPT_LOG_REL}${NC}"

# Create latest_script.log symlink
ln -sf "${SCRIPT_LOG}" "${LOGS_DIR}/latest_data.log"

# Execute the multi-process python script
python3 "${SCRIPT_DIR}/generate_data.py" --scenarios-file "$INPUT_FILE" --max-workers "$NUM_USERS" | tee "${SCRIPT_LOG}"

EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    echo "⚠️  Test failed or encountered an error (Exit Code: $EXIT_CODE)"
else
    echo "✅  Test completed."
fi

echo -e "${GREEN}Log saved to ${SCRIPT_LOG_REL}${NC}"
LOGS_DIR_REL=$(python3 -c "import os; print(os.path.normpath(os.path.relpath('${LOGS_DIR}')))")
echo -e "${GREEN}Tip: ${LOGS_DIR_REL}/latest_data.log always contains the latest log ${NC}"

# Update the views
if [ -f "${SCRIPT_DIR}/../../tools/update_views.sh" ]; then
    sh "${SCRIPT_DIR}/../../tools/update_views.sh"
else
    echo "generate_data.sh: update_views.sh not found, skipping view update."
fi

echo ""
echo "======================================================================="
echo " Stress Test Suite Finished!                                           "

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))
echo " Total Wall Time: ${DURATION} seconds"
echo "======================================================================="
