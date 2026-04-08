#!/bin/bash

# Script to test the deployed pto_agent

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

python "${SCRIPT_DIR}/test_remote_agent.py"


