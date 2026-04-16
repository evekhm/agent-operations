#!/usr/bin/env bash
# =============================================================================
# Knowledge Supervisor Agent - Evaluation Runner
#
# Runs LLM-as-a-judge evaluations using ADK eval.
#
# Usage:
#   ./tests/eval/run_evals.sh                    # Run all evalsets
#   ./tests/eval/run_evals.sh basic              # Run only basic evalset
#   ./tests/eval/run_evals.sh routing            # Run only routing evalset
#   ./tests/eval/run_evals.sh edge_cases         # Run only edge cases evalset
#   ./tests/eval/run_evals.sh routing:route_pto_balance,route_pto_sick_leave_balance
#                                                 # Run specific cases from an evalset
#
# Exit codes:
#   0 - All evaluations passed
#   1 - One or more evaluations failed
# =============================================================================

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
EVAL_DIR="$SCRIPT_DIR"
EVALSETS_DIR="$EVAL_DIR/evalsets"
CONFIG_FILE="$EVAL_DIR/eval_config.json"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m' # No Color

cd "$AGENT_DIR"

passed=0
failed=0
errors=()

header() {
    echo ""
    echo -e "${BLUE}===============================================================================${NC}"
    echo -e "${BLUE}| ${BOLD}$1${NC}"
    echo -e "${BLUE}===============================================================================${NC}"
}

run_evalset() {
    local evalset_arg="$1"
    local evalset_file
    local display_name

    # Support both full path and short name (e.g., "routing" or "routing:case1,case2")
    if [[ "$evalset_arg" == *.evalset.json* ]]; then
        evalset_file="$evalset_arg"
        display_name="$(basename "$evalset_file")"
    else
        # Extract name and optional case filter
        local name="${evalset_arg%%:*}"
        local filter="${evalset_arg#*:}"
        evalset_file="$EVALSETS_DIR/${name}.evalset.json"
        display_name="${name}.evalset.json"
        if [[ "$filter" != "$name" ]]; then
            evalset_file="${evalset_file}:${filter}"
            display_name="${display_name}:${filter}"
        fi
    fi

    # Verify file exists (check without the :filter suffix)
    local file_only="${evalset_file%%:*}"
    if [[ ! -f "$file_only" ]]; then
        echo -e "${RED}ERROR: Evalset file not found: $file_only${NC}"
        failed=$((failed + 1))
        errors+=("$display_name: file not found")
        return
    fi

    echo ""
    echo -e "${YELLOW}>>> Running: ${BOLD}$display_name${NC}"
    echo ""

    local start_time=$SECONDS

    # Note: --print_detailed_results is omitted due to a bug in adk eval's
    # pretty_print_eval_result (KeyError: 'rubric_id') that causes a crash
    # even when all tests pass. Detailed per-case results are still written
    # to app/.adk/eval_history/*.evalset_result.json for inspection.
    if uv run adk eval ./app "$evalset_file" \
        --config_file_path="$CONFIG_FILE" 2>&1; then
        local elapsed=$(( SECONDS - start_time ))
        echo -e "${GREEN}PASSED${NC} $display_name (${elapsed}s)"
        passed=$((passed + 1))
    else
        local elapsed=$(( SECONDS - start_time ))
        echo -e "${RED}FAILED${NC} $display_name (${elapsed}s)"
        failed=$((failed + 1))
        errors+=("$display_name")
    fi
}

# ---- Main ----

header "Knowledge Supervisor - Evaluation Suite"

# Ensure dependencies are installed
echo "Installing eval dependencies..."
uv sync --dev --extra eval --quiet 2>/dev/null || uv sync --dev --extra eval

if [[ $# -gt 0 ]]; then
    # Run specific evalset(s) passed as arguments
    for arg in "$@"; do
        run_evalset "$arg"
    done
else
    # Run all evalsets
    for evalset in "$EVALSETS_DIR"/*.evalset.json; do
        run_evalset "$evalset"
    done
fi

# ---- Summary ----

header "Evaluation Summary"

total=$((passed + failed))
echo ""
echo -e "  Total:  ${BOLD}$total${NC} evalset(s)"
echo -e "  Passed: ${GREEN}${BOLD}$passed${NC}"
echo -e "  Failed: ${RED}${BOLD}$failed${NC}"

if [[ ${#errors[@]} -gt 0 ]]; then
    echo ""
    echo -e "${RED}Failed evalsets:${NC}"
    for err in "${errors[@]}"; do
        echo -e "  ${RED}- $err${NC}"
    done
fi

echo ""

if [[ $failed -gt 0 ]]; then
    echo -e "${RED}${BOLD}RESULT: FAIL${NC}"
    exit 1
else
    echo -e "${GREEN}${BOLD}RESULT: PASS${NC}"
    exit 0
fi
