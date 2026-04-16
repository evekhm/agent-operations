# Observability Agent

An ADK-based agent that analyzes agent telemetry stored in BigQuery and generates observability reports (latency, errors, quality scores, trends).

## Prerequisites

- Python 3.11+ with a virtualenv (`.venv`)
- A `.env` file at the repo root with at least:
  ```
  PROJECT_ID=<gcp-project>
  DATASET_ID=<bq-dataset>
  TABLE_ID=<bq-table>
  DATASET_LOCATION=<bq-location>   # e.g. "us"
  ```
- The `bigquery_agent_analytics` SDK:
  ```bash
  pip install git+https://github.com/GoogleCloudPlatform/BigQuery-Agent-Analytics-SDK.git
  ```

## Scripts

All shell wrappers live in this directory and can be run from anywhere (they resolve paths relative to themselves).

### 1. Query Responses & Evaluate Quality

Browse user questions and agent answers, and run AI quality evaluation.
The same core evaluation logic (`eval_common.py`) is shared between the standalone CLI and the report generation pipeline.

| Script | Approach | A2A handling |
|---|---|---|
| `query_responses.sh` | Pure SQL via `bq` CLI | Built-in SQL CTEs with time-window join |
| `query_responses_sdk.sh` | Python + `bigquery_agent_analytics` SDK | A2A_INTERACTION events + time-window fallback |

**SQL version** (no Python dependencies beyond `bq` CLI):

```bash
bash query_responses.sh              # last 100 sessions with AI evaluation
bash query_responses.sh 50           # last 50 sessions
bash query_responses.sh --no-eval    # skip AI evaluation (faster, cheaper)
bash query_responses.sh 20 --no-eval
```

**SDK version** (uses the Python SDK, runs full categorical quality evaluation by default):

```bash
bash query_responses_sdk.sh                        # evaluate last 100 sessions (default)
bash query_responses_sdk.sh --limit 50             # evaluate last 50 sessions
bash query_responses_sdk.sh --no-eval              # browse Q&A pairs without evaluation
bash query_responses_sdk.sh --time_period 7d       # evaluate last 7 days
bash query_responses_sdk.sh --persist              # evaluate and persist results to BQ
bash query_responses_sdk.sh --model gemini-2.5-pro  # use a different model
bash query_responses_sdk.sh --session <session_id>  # deep dive into a single session
```

Evaluates two metrics:
- **Usefulness** - meaningful / unhelpful / partial
- **Grounding** - grounded / ungrounded / no_tool_needed

Output includes per-session details, per-agent quality breakdown, and an overall quality summary.

### 2. Generate Report

Runs the full observability agent to produce an end-to-end report (health, trends, incidents). This is the main agent entry point. The report includes a **Response Quality Analysis** section powered by the same evaluation logic as the standalone script above.

```bash
bash generate_report.sh                          # default: overview, 7d
bash generate_report.sh --playbook health        # health playbook
bash generate_report.sh --time_period 24h        # last 24 hours
bash generate_report.sh --playbook trend --bucket_size 1d
```

Options:
- `--time_period` - Time range for current data (e.g. `24h`, `7d`)
- `--baseline_period` - Time range for historical baseline
- `--bucket_size` - Bucket size for trend analysis (e.g. `1h`, `1d`)
- `--playbook` - Force a specific playbook: `overview`, `health`, `incident`, `trend`, `latest`

Output is logged to `logs/report_<timestamp>.log` (symlinked as `logs/latest_report.log`).

## A2A Response Resolution

When the supervisor agent (`knowledge_supervisor`) calls a remote A2A agent (e.g. `pto_agent` on Cloud Run), the remote agent's response needs to be extracted from the trace data. Two strategies are used:

1. **A2A_INTERACTION events** (primary): The ADK logs `A2A_INTERACTION` events under the supervisor's session containing the remote agent's response in `artifacts[0].parts[0].text`.
2. **Time-window fallback**: For older data without `A2A_INTERACTION` events, the scripts find the supervisor's `AGENT_STARTING`/`AGENT_COMPLETED` timestamps for the remote agent, then query for the remote agent's own `LLM_RESPONSE` events that fall within that time window.

A2A sessions are tagged with `[A2A]` in the output.

## Architecture

The evaluation logic is structured to avoid code duplication:

```
eval_common.py                 # Shared core: metrics, trace helpers, run_evaluation()
    |
    +-- query_responses.py     # Standalone CLI (imports eval_common)
    |
    +-- quality_evaluation.py  # Report pipeline async wrapper (imports eval_common)
            |
            +-- report_data.py     # Calls evaluate_response_quality()
            +-- generate_report.py # Renders quality section in report
```

## Project Structure

```
agents/observability_agent/
  agent.py                  # ADK agent definition (root_agent)
  config.py                 # Configuration from .env
  prompts.py                # Agent prompts/playbooks
  eval_common.py            # Shared evaluation logic (metrics, trace helpers, runner)
  generate_report.py        # CLI entry point for report generation
  generate_report.sh        # Shell wrapper
  query_responses.py        # SDK-based Q&A viewer + quality evaluation
  query_responses.sh        # Pure SQL Q&A viewer
  query_responses_sdk.sh    # Shell wrapper for query_responses.py
  agent_tools/              # Tool implementations used by the agent
    report_generation/
      generate_report.py    # Report rendering (markdown + charts)
      report_data.py        # BigQuery data queries
      quality_evaluation.py # Async wrapper for eval_common + AI summary
```
