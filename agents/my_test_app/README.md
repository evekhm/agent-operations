# my_test_app

This directory contains `my_test_app`, an ADK (Agent Development Kit) based application designed for testing agent orchestration, tool execution, observability, and BigQuery analytics logging.


### Stress Testing
The application includes a `stress_test.py` script to simulate concurrent user load. This is highly useful for testing the throughput of the BigQuery logging plugin and the LLM API quota limits. 

The stress test expects a `replay_test.json` file in the same directory, which contains an array of `queries` and an initial conversational `state`.

**To run the stress test (e.g., 10 concurrent users):**
```bash
python agents/my_test_app/stress_test.py 10
```
This script bypasses the standard API server and instantiates the `Runner` and plugins per-process to ensure thread safety during high-concurrency testing.
    
### Testing Alternate Configurations

The `my_test_app` agent supports dynamic configuration via environment variables, which can easily be combined with `stress_test.py` to compare performance between different LLM settings, models, or regions.

For example, to run the stress test using `WRONG_CONFIG1` against the `gemini-2.5-pro` model in the `us-east1` region:

```bash
AGENT_CONFIG="WRONG_CONFIG1" MODEL_ID="gemini-2.5-pro" GCP_LOCATION="us-east1" python agents/my_test_app/stress_test.py 10
```

Available pre-defined configurations for `AGENT_CONFIG` include:
- `NORMAL` (default)
- `OVER_PROVISIONED`
- `HIGH_TEMP`
- `WRONG_MAX_OUTPUT_TOKENS_COUNT_CONFIG`
- `WRONG_CANDIDATE_COUNT_CONFIG`

### Automated Configuration Matrix Testing
A wrapper script is provided to automatically run the stress test across multiple configurations and models for benchmarking.

To run the suite with the default configurations (e.g., using 2 concurrent users per combination):
```bash
./agents/my_test_app/run_stress_test_suite.sh 2
```
This script will iterate through the models (`gemini-3.0-pro`, `gemini-2.5-pro`) and `AGENT_CONFIG` variants, invoking the `stress_test.py` script automatically.

### Unreliable Tool Simulation
The root agent includes an `unreliable_tool_agent` designed to simulate system failures, timeouts, and flaky behavior. By explicitly requesting actions like "simulate a flaky action", "timeout", or test a failure using an "unreliable tool" in the prompt, the root agent will accurately route to this specialized test case scenario.

### Generating Dynamic Scenarios
If you want to test the agent orchestration against a massive volume of randomized and highly-varied test payloads, use the Python script:

```bash
python agents/my_test_app/generate_test_scenarios.py
```

This built-in script dynamically generates pipe-delimited test case lines via `gemini-2.5-flash`. To overcome typical LLM generation limits while maximizing API performance, it utilizes parallel execution (`asyncio.gather`), sending chunks of concurrent requests to rapidly fetch the requested number of tests. 

* The `total_lines` defaults to `1600` inside the script's entry point, generating in optimized batches of `400` lines simultaneously. 

Once your output file (`test_scenario.txt`) is generated, you can feed this input directly to the stress test suite alongside the concurrency limit:

```bash
./agents/my_test_app/run_stress_test_suite.sh 10 agents/my_test_app/test_scenarios.txt
```
The testing suite will automatically parse each pip-delimited line from the input file and execute the parallel stress tests for each scenario configuration!