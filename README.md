# Agent Operations

## Prerequisites

* GCP project (Note down Project ID)
* Python 3.12 


## Installation 
for the Local machine Execution
* Install uv

* Activate Python virtual environment in home directory:

```bash
python -m venv .venv
source .venv/bin/activate
```

* Install libraries:
```bash
uv pip install -r requirements.txt
```

* Install ADK in the Python virtual environment:

```bash
uv pip install google-adk
```

* Set Project ID and authenticate:
```shell
export PROJECT_ID="..."
```

```shell
gcloud config set project $PROJECT_ID
gcloud auth application-default set-quota-project $PROJECT_ID
```

```shell
gcloud auth login
gcloud auth application-default login    
```

* Update environment variables inside [.env](.env)  file:
```text
PROJECT_ID=...
```
  
* When integrating with existing environment and agent using [BigQuery Agent Analytics plugin](https://google.github.io/adk-docs/integrations/bigquery-agent-analytics/), make sure to point to the corresponding resources and update `.env` file accordingly:

```text
# BigQuery Analytics Plugin
DATASET_ID="logging"
DATASET_LOCATION="us-central1"
TABLE_ID="agent_events_v2"
```

* Alternatively, if you do not have an existing environment and want to quickly create resources and use a sample agent to generate some load, follow the steps below: 
  * Create required GCP resources, such as BigQuery, DATASET, Datastore for Vertex AI search (sample Agent)

      ```shell
      ./setup.sh
      ```
  * Data Generation using sample `starter-agent` of the `my_test_app`

    ```bash
    ./agents/my_test_app/run_stress_test_suite.sh
    ```

    >> Advanced:
    To run with concurrency (e.g. 10 users):
    >>```bash
    >>./agents/my_test_app/run_stress_test_suite.sh 10
    >>```

## Generate Observability Reports

You can generate comprehensive performance and latency intelligence reports using the Observability Analyst Agent using a number of Playbooks

### Playbook: overview (Default System Overview)
By default, the agent executes the `overview` playbook, which provides a straightforward aggregation of latency and error metrics for the specified `--time_period` without attempting to mathematically compare it to a historical baseline.
```shell
tools/run_observability_analyst.sh --time_period 24h
```

### Playbook: health (Healthcheck)
By default, the agent evaluates the **last 24 hours (Current Reality)** against a sturdy **7-day Historical Baseline**.
*(Note: You can explicitly force the agent into any Playbook using `--playbook overview`, `--playbook health`, `--playbook incident`, `--playbook trend`, or `--playbook latest`)*
```shell
tools/run_observability_analyst.sh --playbook health
```

### Playbook: incident (Incident Review)
The `incident` playbook is designed for investigating isolated events, sudden latency spikes, or validating recent hotfixes within a tight, custom time window.

```shell
tools/run_observability_analyst.sh --playbook incident --time_period 6h --baseline_period 6h
```
**How it works**:
1. **Time-Shifted Baselines**: By specifying identical `time_period` and `baseline_period` (e.g. 6h), the LLM will automatically perform a "Time Shift." It will explicitly calculate non-overlapping bounds to evaluate the current 6-hour incident window against the 6 hours *immediately preceding* the incident.
2. **Deep Concurrency Investigation**: During an incident, the agent is proactively instructed to utilize `analyze_trace_concurrency` and `detect_sequential_bottlenecks` on the slowest anomalous traces. This mathematically proves if your multi-agent architecture is suffering from blocking execution or deadlocks during load.
3. **Hotfix Verification**: It utilizes the `get_latest_queries` tool to fetch the absolute most recent requests *inside* your defined incident window to verify if recent iterations or deployments are actively improving the situation.

### Playbook: latest (Single Trace Deep Dive)
The `latest` playbook acts as a microscope, giving you an end-to-end "X-Ray" of the single most recent root agent execution trace. It extracts exact tool sequential timing, concurrency proof, backwards compatibility with baselines, and root cause analysis.
```shell
tools/run_observability_analyst.sh --playbook latest
```

### Playbook: trend (Trend Analysis)
To evaluate long term structural degradation or improvement, you can pass a large timeframe and split it into chronological buckets. The agent will calculate slopes and trends over time:
```shell
# Analyzes the last 30 days of data, grouped into daily buckets
tools/run_observability_analyst.sh --playbook trend --time_period 30d --bucket_size 1d
```
**How it works**: The `trend` playbook explicitly uses the `--time_period` (e.g. `30d`) to establish the overall boundary of the time-series array, and `--bucket_size` (e.g. `1d`) to chop that boundary into discrete chronological steps. The LLM iterates over those 30 distinct daily buckets to mathematically calculate if the p95 slope is rising (degrading) or falling (improving) over the course of the month.
*(Note: Unlike the `incident` playbook, `trend` does **not** perform any time-shifting. It evaluates the exact historical block of data as specified by the `--time_period`).*
