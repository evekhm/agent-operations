#!/bin/bash
# Query agent responses and evaluate quality.
# Eval is on by default. Use --no-eval to browse Q&A only.
#
# Usage:
#   ./query_responses_sdk.sh                          # evaluate last 100 sessions
#   ./query_responses_sdk.sh --limit 50               # evaluate last 50
#   ./query_responses_sdk.sh --session <id>           # single-session deep dive
#   ./query_responses_sdk.sh --no-eval                # browse Q&A only
#   ./query_responses_sdk.sh --persist                # evaluate + persist to BQ
#   ./query_responses_sdk.sh --time_period 7d         # evaluate last 7 days

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYDANTIC_DISABLE_PLUGINS=1

# Log eval runs (skip logging for --no-eval or --session)
if [[ " $* " != *" --no-eval "* ]] && [[ " $* " != *" --session "* ]]; then
    LOGS_DIR="${SCRIPT_DIR}/../../logs"
    mkdir -p "${LOGS_DIR}"
    TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
    SCRIPT_LOG="${LOGS_DIR}/quality_eval_${TIMESTAMP}.log"
    ln -sf "${SCRIPT_LOG}" "${LOGS_DIR}/latest_quality_eval.log"
    echo -e "\033[0;32mLog: ${SCRIPT_LOG}\033[0m"
    python3 ${SCRIPT_DIR}/query_responses.py "$@" 2>&1 | tee "${SCRIPT_LOG}"
else
    python3 ${SCRIPT_DIR}/query_responses.py "$@"
fi
