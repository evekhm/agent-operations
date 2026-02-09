#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYDANTIC_DISABLE_PLUGINS=1
export PYTHONPATH="${SCRIPT_DIR}/../"
python3 ${SCRIPT_DIR}/run_observability_analyst.py

