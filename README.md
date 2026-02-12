# Agent Operations

## Installation

```bash
uv pip install -r requirements.txt
```

## Stress test
```shell
./agents/my_test_app/run_stress_test_suite.sh 2
```

## Generate Observability Reports

You can generate comprehensive performance and latency intelligence reports using the Observability Analyst Agent:

### Playbook A: Daily Health Check (Pulse Check)
By default, the agent evaluates the **last 24 hours (Current Reality)** against a sturdy **7-day Historical Baseline**.
```shell
tools/run_observability_analyst.sh
```

### Playbook B: Custom KPI Performance (Time-Bound)
To explicitly bound the analysis to a specific event (e.g., investigating a 6-hour production incident), simply limit the scope:
```shell
tools/run_observability_analyst.sh --time_period 6h --baseline_period 6h
```
**How it works**: By specifying identical time and baseline periods, the LLM will automatically perform a "Time Shift." It will evaluate your `time_period` (the last 6 hours) against a mathematically offset historical window that immediately *precedes* it (the 6 hours before that). This ensures accurate delta analysis immediately before and during an incident.

### Playbook C: Temporal Trend Analysis
To evaluate long term structural degradation or improvement, you can pass a large timeframe and split it into chronological buckets. The agent will calculate slopes and trends over time:
```shell
# Analyzes the last 30 days of data, grouped into daily buckets
tools/run_observability_analyst.sh --time_period 30d --baseline_period 30d --bucket_size 1d
```
**How it works**: Playbook C explicitly uses the `--baseline_period` (e.g. `30d`) to establish the overall boundary of the time-series array, and `--bucket_size` (e.g. `1d`) to chop that boundary into discrete chronological steps. The LLM iterates over those 30 distinct daily buckets to mathematically calculate if the p95 slope is rising (degrading) or falling (improving) over the course of the month.
*(Note: Unlike Playbook B, Playbook C does **not** perform any time-shifting. It evaluates the exact historical block of data as specified by the `--baseline_period`).*
