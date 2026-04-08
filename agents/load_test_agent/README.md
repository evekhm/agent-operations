# Load Test Agent

This directory contains the load testing framework for the knowledge supervisor agent.
It simulates load by sending concurrent requests to the deployed Reasoning Engine.

## Files

*   `load_generator.py`: The main script that generates load by calling the Reasoning Engine.
*   `deploy.sh`: Script to build the container image and deploy it as a Cloud Run Job.
*   `local_smoke_test.py`: Script to run a local smoke test against the remote Reasoning Engine.
*   `run_local_test.sh`: Script to run `load_generator.py` locally (requires proper environment setup).
*   `SKILL.md`: Documents the skills and rules for this agent.

## Configuration

The load generator relies on the following environment variables:

*   `TOPICS_CONFIG`: A comma-separated list of topic:count pairs. Example: `"pto and hiring:5,general knowledge:3"`.
*   `CONCURRENCY`: Number of concurrent requests to make (default: `1`).
*   `DURATION_MINUTES`: Duration of the load test in minutes (default: `1.0`).

### Default Configuration

Default values are stored in the `.env` file at the project root:

```env
TOPICS_CONFIG="pto and hiring:5"
CONCURRENCY=2
DURATION_MINUTES=5
```

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
