#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYDANTIC_DISABLE_PLUGINS=1
export PYTHONPATH="${SCRIPT_DIR}/../../src/src:${SCRIPT_DIR}/../../"

# Colors for output
GREEN='\033[0;32m'
NC='\033[0m'

# Create logs directory if it doesn't exist
LOGS_DIR="${SCRIPT_DIR}/../../logs"
mkdir -p "${LOGS_DIR}"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
SCRIPT_LOG="${LOGS_DIR}/quality_eval_${TIMESTAMP}.log"

SCRIPT_LOG_REL=$(python3 -c "import os; print(os.path.normpath(os.path.relpath('${SCRIPT_LOG}')))")

echo -e "${GREEN}Script output being saved to: ${SCRIPT_LOG_REL}${NC}"

ln -sf "${SCRIPT_LOG}" "${LOGS_DIR}/latest_quality_eval.log"

python3 ${SCRIPT_DIR}/evaluate_quality.py "$@"  2>&1 | tee "${SCRIPT_LOG}"

echo -e "${GREEN}Log saved to ${SCRIPT_LOG_REL}${NC}"
