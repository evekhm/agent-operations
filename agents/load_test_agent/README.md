# Load Test Agent

This directory contains the load testing framework for the knowledge supervisor agent.
It generates realistic questions using Gemini and sends concurrent requests to the deployed Reasoning Engine.

## How It Works

1. Reads topic configuration (`TOPICS_CONFIG`)
2. Uses Gemini to generate realistic questions for each topic, constrained to what the agents can actually answer
3. Discovers the deployed `knowledge-supervisor` Reasoning Engine
4. Sends questions concurrently (controlled by `CONCURRENCY` semaphore)
5. Repeats batches until `DURATION_MINUTES` expires

Each topic is mapped to a capability description so the question generator only produces answerable questions.

## Files

*   `load_generator.py`: Main script with question generation and load execution.
*   `deploy.sh`: Builds container image and deploys as a Cloud Run Job.
*   `run_job.sh`: Executes the deployed Cloud Run Job with full topic configuration.
*   `run_local_test.sh`: Runs `load_generator.py` locally.
*   `local_smoke_test.py`: Quick smoke test against the remote Reasoning Engine.

## Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `TOPICS_CONFIG` | Comma-separated `topic:count` pairs | `pto and sick leave balances:3,...` |
| `CONCURRENCY` | Number of concurrent requests | `1` |
| `DURATION_MINUTES` | Test duration in minutes | `1.0` |

### Supported Topics

Topics are mapped to agent capabilities for accurate question generation:

| Topic keyword | Routed to | Example questions |
|---------------|-----------|-------------------|
| `pto`, `sick leave`, `vacation` | `pto_agent` | PTO balance, sick leave, date range calculations |
| `company policies`, `hr` | `internal_docs_agent` | PTO policy, expense rules, hiring process |
| `adk`, `documentation` | `adk_documentation_agent` | ADK tools, agent creation |
| `bigquery`, `data analysis` | `bigquery_data_agent` | SQL queries, data reports |
| `gcp`, `google cloud`, `firebase` | `developer_docs_agent` | Google Cloud docs, best practices |
| `general`, `knowledge` | `google_search_agent` | Technology, factual lookups |
| `database`, `lookup` | `local_tools_agent` | Item lookups, calculations |

## How to Trigger the Job

### 1. Using Defaults

To run the job with the default parameters configured during deployment:

```bash
gcloud run jobs execute knowledge-supervisor-test \
  --project=$PROJECT_ID \
  --region=$REGION
```

### 2. Overwriting Parameters on the Fly

You can override any configuration parameter when executing the job by using the `--update-env-vars` flag:

```bash
gcloud run jobs execute knowledge-supervisor-test \
  --project=$PROJECT_ID \
  --region=$REGION \
  --update-env-vars="CONCURRENCY=5,DURATION_MINUTES=10,TOPICS_CONFIG=\"general knowledge:10\""
```

Note: The `TOPICS_CONFIG` now uses a simple `topic:count` format separated by commas, making it much easier to pass without complex JSON escaping.
