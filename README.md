# Agent Operations

## Installation

* Install uv

* Activate Python virtual environment in home directory

```bash
python -m venv .venv
  source .venv/bin/activate
```

* Install libraries
```bash
uv pip install -r requirements.txt
```

* Install ADK in the Python virtual environment

```bash
  uv pip install google-adk
```

* Create new GCP project
* Set your GCP Project ID into environment variable below:
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
* Update `.env` file with your `PROJECT_ID` 
  
* TODO: Steps to create Vertex AI datastore


## Data Generation

The core purpose of the `stress_test.py` script is to simulate concurrent user load for the `my_test_app` agent. 
This rapidly populates BigQuery with realistic, varied agent execution data. By running the stress test with different configurations (models, regions, and settings), you generate the rich dataset necessary for the Observability Analyst Agent to detect regressions, bottlenecks, and anomalies.

The stress test expects a `replay_test.json` file in the `agents/my_test_app/` directory, which contains an array of `queries` and an initial conversational `state`.

To run the suite (e.g., using 2 concurrent users per combination):
```bash
./agents/my_test_app/run_stress_test_suite.sh 2
```

This script bypasses the standard API server and instantiates the `Runner` and plugins per-process to ensure thread safety during high-concurrency testing.


## Generate Observability Reports

You can generate comprehensive performance and latency intelligence reports using the Observability Analyst Agent:

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
