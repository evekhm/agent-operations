#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYDANTIC_DISABLE_PLUGINS=1
export PYTHONPATH="${SCRIPT_DIR}/../../"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Create logs directory if it doesn't exist
LOGS_DIR="${SCRIPT_DIR}/../../logs"
mkdir -p "${LOGS_DIR}"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
SCRIPT_LOG="${LOGS_DIR}/report_${TIMESTAMP}.log"

# Get relative path for display
SCRIPT_LOG_REL=$(python3 -c "import os; print(os.path.normpath(os.path.relpath('${SCRIPT_LOG}')))")

# Run the agent with caching enabled (replaces adk run) and pipe to tee
echo -e "${GREEN}Script output being saved to: ${SCRIPT_LOG_REL}${NC}"

# Create latest_script.log symlink
ln -sf "${SCRIPT_LOG}" "${LOGS_DIR}/latest_report.log"

python3 ${SCRIPT_DIR}/generate_report.py "$@"  2>&1 | tee "${SCRIPT_LOG}"

echo -e "${GREEN}Log saved to ${SCRIPT_LOG_REL}${NC}"
LOGS_DIR_REL=$(python3 -c "import os; print(os.path.normpath(os.path.relpath('${LOGS_DIR}')))")
echo -e "${GREEN}Tip: ${LOGS_DIR_REL}/latest_report.log always contains the latest log ${NC}"

