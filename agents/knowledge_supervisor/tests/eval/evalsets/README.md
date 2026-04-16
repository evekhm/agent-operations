# Evaluation Sets

This directory contains evaluation sets for testing the knowledge_supervisor agent using `adk eval` with LLM-as-a-judge scoring.

## Evalsets

| Evalset | Cases | What it tests |
|---|---|---|
| `basic.evalset.json` | 5 | Smoke tests: greeting + one query per major sub-agent |
| `routing.evalset.json` | 15 | Routing correctness for every sub-agent path |
| `edge_cases.evalset.json` | 11 | Ambiguous queries (e.g. PTO balance vs PTO policy) |

## Running Evaluations

```bash
# Run all evalsets with summary report
./tests/eval/run_evals.sh

# Run a specific evalset by name
./tests/eval/run_evals.sh basic
./tests/eval/run_evals.sh routing
./tests/eval/run_evals.sh edge_cases

# Run specific cases from an evalset
./tests/eval/run_evals.sh routing:route_pto_balance,route_pto_sick_leave_balance

# Using Make
make eval                                                # basic evalset
make eval EVALSET=tests/eval/evalsets/routing.evalset.json
make eval-all                                            # all evalsets
```

## How Pass/Fail Works

Each test case is scored on two dimensions:

1. **Trajectory matching** (`tool_trajectory_avg_score`) -- did the supervisor route to the correct sub-agent? Compared against `intermediate_data.tool_uses` in the evalset. Deterministic 0/1.

2. **LLM-as-judge rubrics** -- a judge model scores the response against four rubrics defined in `eval_config.json`:
   - `relevance` -- response addresses the specific query
   - `routing_correctness` -- correct sub-agent was selected
   - `helpfulness` -- response is actionable with clear details
   - `no_hallucination` -- no fabricated data beyond tool output

Both must meet the **threshold (0.8)** or the case is marked FAILED.

Exit codes: `0` = all passed, `1` = one or more failed.

## Evalset Format

Each `.evalset.json` follows the ADK evaluation format:

```json
{
  "eval_set_id": "unique_id",
  "name": "Human-readable name",
  "description": "What this evalset tests",
  "eval_cases": [
    {
      "eval_id": "case_id",
      "conversation": [
        {
          "user_content": {
            "parts": [{"text": "User message"}]
          },
          "intermediate_data": {
            "tool_uses": [
              {"name": "transfer_to_agent", "args": {"agent_name": "target_agent"}}
            ]
          }
        }
      ],
      "session_input": {
        "app_name": "knowledge_supervisor",
        "user_id": "eval_user",
        "state": {}
      }
    }
  ]
}
```

## Adding New Test Cases

1. Identify the query and which sub-agent should handle it
2. Add an entry to the appropriate evalset (or create a new `.evalset.json`)
3. Include `intermediate_data.tool_uses` with the expected `transfer_to_agent` call
4. Run `./tests/eval/run_evals.sh <evalset_name>` to verify

## Sub-Agent Routing Reference

| Query type | Expected sub-agent |
|---|---|
| PTO/sick leave **balance**, vacation planning, working days | `pto_agent` |
| Company **policies**, HR procedures, benefits, onboarding | `internal_docs_agent` |
| BigQuery data analysis, SQL queries | `bigquery_data_agent` |
| Single item lookup by ID, calculations | `local_tools_agent` |
| Multiple item lookups in parallel | `parallel_db_lookup` |
| ADK documentation | `adk_documentation_agent` |
| Google Cloud/Firebase/Android docs | `developer_docs_agent` |
| General knowledge (fallback) | `google_search_agent` |
