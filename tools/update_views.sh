#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
PYTHONPATH="${ROOT_DIR}" python ${SCRIPT_DIR}/update_views.py