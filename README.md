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
python3 tools/run_observability_analyst.py
```

### Playbook B: Custom KPI Performance (Time-Bound)
To explicitly bound the analysis to a specific event (e.g., investigating a 6-hour production incident yesterday), simply limit the scope:
```shell
python3 tools/run_observability_analyst.py --time_period 6h --baseline_period 6h
```

### Playbook C: Temporal Trend Analysis
To evaluate long term structural degradation or improvement, you can pass a large timeframe and split it into chronological buckets. The agent will calculate slopes and trends over time:
```shell
# Analyzes the last 30 days of data, grouped into daily buckets
python3 tools/run_observability_analyst.py --time_period 30d --baseline_period 30d --bucket_size 1d
```
