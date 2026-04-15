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
- The `bigquery_agent_analytics` SDK. Install it from the source repo:
  ```bash
  pip install git+https://github.com/haiyuan-eng-google/BigQuery-Agent-Analytics-SDK.git
  ```
  Or add to your `requirements.txt`:
  ```
  bigquery-agent-analytics @ git+https://github.com/haiyuan-eng-google/BigQuery-Agent-Analytics-SDK.git
  ```

## Scripts

All shell wrappers live in this directory and can be run from anywhere (they resolve paths relative to themselves).

### 1. Query Responses

View user questions and agent answers from BigQuery.

| Script | Approach | A2A handling |
|---|---|---|
| `query_responses.sh` | Pure SQL via `bq` CLI | Built-in SQL CTEs with time-window join |
| `query_responses_sdk.sh` | Python + `bigquery_agent_analytics` SDK | Python-level fallback with time-window SQL |

**SQL version** (no Python dependencies beyond `bq` CLI):

```bash
bash query_responses.sh              # last 100 sessions with AI evaluation
bash query_responses.sh 50           # last 50 sessions
bash query_responses.sh --no-eval    # skip AI evaluation (faster, cheaper)
bash query_responses.sh 20 --no-eval
```

**SDK version** (uses the Python SDK, supports `--eval` for per-session AI quality evaluation):

```bash
bash query_responses_sdk.sh                # last 100 sessions
bash query_responses_sdk.sh --limit 50     # last 50 sessions
bash query_responses_sdk.sh --eval         # include per-session quality evaluation
```

### 2. Generate Report

Runs the full observability agent to produce an end-to-end report (health, trends, incidents). This is the main agent entry point.

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

### 3. Evaluate Quality

Uses the SDK's categorical evaluator to classify agent responses across quality dimensions. Shows user question, agent response, and AI evaluator reasoning for each session. Includes an A2A workaround that detects remote agent transfers and re-evaluates those sessions with the resolved response (see [A2A Trace Correlation Gap](#a2a-trace-correlation-gap)).

```bash
bash evaluate_quality.sh                          # all time, last 100 sessions
bash evaluate_quality.sh --time_period 24h        # last 24 hours
bash evaluate_quality.sh --limit 50               # only 50 sessions
bash evaluate_quality.sh --time_period all        # all sessions, no time filter
bash evaluate_quality.sh --persist                # save results to BigQuery
bash evaluate_quality.sh --model gemini-2.5-pro
bash evaluate_quality.sh --no-a2a-fix             # disable A2A workaround
```

Options:
- `--time_period` - Time range (e.g. `24h`, `7d`) or `all` for no time filter (default: `all`)
- `--limit` - Max sessions to evaluate (default: `100`)
- `--model` - Model for evaluation (default: `gemini-2.5-flash`)
- `--persist` - Save results to BigQuery
- `--no-a2a-fix` - Disable A2A re-evaluation workaround (use to verify upstream fix)

Evaluates two metrics:
- **Usefulness** - meaningful / unhelpful / partial
- **Grounding** - grounded / ungrounded / no_tool_needed

A2A sessions are tagged with `[A2A]` in the output. The summary shows how many were detected and re-evaluated.

Output is logged to `logs/quality_eval_<timestamp>.log`.

### 4. Test Report Quality Module

Standalone test for the `evaluate_response_quality()` function used by the report agent (in `agent_tools/report_generation/quality_evaluation.py`). Runs the same evaluation with A2A workaround that the full report uses, but without the full report cycle (~1-2 min vs ~8 min).

```bash
bash test_quality_evaluation.sh                          # all time
bash test_quality_evaluation.sh --time_period 7d         # last 7 days
bash test_quality_evaluation.sh --model gemini-2.5-pro   # custom model
bash test_quality_evaluation.sh --json                   # raw JSON output
```

Options:
- `--time_period` - Time range (e.g. `24h`, `7d`) or `all` for no time filter (default: `all`)
- `--model` - Model for evaluation (default: `gemini-2.5-flash`)
- `--json` - Output raw JSON instead of formatted report

## A2A Trace Correlation Gap

When the supervisor agent (`knowledge_supervisor`) calls a remote A2A agent (e.g. `pto_agent` on Cloud Run), the remote agent logs its events under a **different `session_id`**. The supervisor's trace only records `AGENT_STARTING` / `AGENT_COMPLETED` with `content: null` for the remote agent -- the actual response is lost from the supervisor's perspective.

### How it manifests

- `trace.final_response` (SDK) returns `None` or a `"call:..."` tool-call string for sessions handled by remote agents
- Sessions appear as "no response" even though the remote agent answered
- The SDK's categorical evaluator rates these sessions as "unhelpful" because it can't see the actual response

### How the scripts work around it

All scripts use **time-window matching**: they find the supervisor's `AGENT_STARTING`/`AGENT_COMPLETED` timestamps for the remote agent, then query for the remote agent's own `LLM_RESPONSE` events (logged under a different session) that fall within that time window.

A2A detection uses two strategies:
1. **Explicit**: looks for a `transfer_to_agent` tool call in the trace
2. **Fallback**: finds any agent with `AGENT_STARTING`/`COMPLETED` spans but no `LLM_RESPONSE` in the same trace

**`evaluate_quality.py`** goes further: after the SDK evaluation, it identifies A2A sessions that were rated "unhelpful", resolves their actual remote response, and re-evaluates them via the Gemini API. This can be disabled with `--no-a2a-fix` to verify when the upstream bug is fixed.

See `docs/GITHUB_ISSUE_A2A_TRACE_CORRELATION.md` for the full issue description and proposed upstream fixes.

## Project Structure

```
agents/observability_agent/
  agent.py                  # ADK agent definition (root_agent)
  config.py                 # Configuration from .env
  prompts.py                # Agent prompts/playbooks
  generate_report.py        # CLI entry point for report generation
  generate_report.sh        # Shell wrapper
  query_responses.py        # SDK-based Q&A viewer with A2A workaround
  query_responses.sh        # Pure SQL Q&A viewer with A2A workaround
  query_responses_sdk.sh    # Shell wrapper for query_responses.py
  evaluate_quality.py        # Response quality evaluation
  evaluate_quality.sh        # Shell wrapper
  test_quality_evaluation.py    # Standalone quality eval test
  test_quality_evaluation.sh    # Shell wrapper
  agent_tools/              # Tool implementations used by the agent
    report_generation/
      generate_report.py    # Report data fetching
      report_data.py        # BigQuery data queries
      quality_evaluation.py # Quality evaluation logic
```
