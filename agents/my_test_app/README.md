# my_test_app

This directory contains `my_test_app`, an ADK (Agent Development Kit) based application designed for testing agent orchestration, tool execution, observability, and BigQuery analytics logging.


### Stress Testing
The application includes a `test_suit.py` script to simulate concurrent user load. This is highly useful for testing the throughput of the BigQuery logging plugin and the LLM API quota limits. 

The stress test script is orchestrated using `generate_data.sh`, which passes pipe-delimited scenarios (like `test_scenarios.txt`) to the multi-process Python script. 

**To run the stress test (e.g., executing the default scenarios):**
```bash
./agents/my_test_app/generate_data.sh
```
The underlying `generate_data.py` natively parses these scenarios and assigns them to an isolated `ProcessPoolExecutor` worker pool to properly test scenarios in parallel.
    
### Testing Alternate Configurations

The `my_test_app` agent supports dynamic configuration testing, which is orchestrated automatically when running test scenarios. The configuration variant, model ID, and region are specified directly within each pipe-delimited line in the test scenario file.

For example, a scenario targeting `WRONG_CONFIG1` against the `gemini-2.5-pro` model in the `us-east1` region would be formatted as:
`VALID_ALL|gemini-2.5-pro|WRONG_CONFIG1|us-east1|What is Agent Observability?`

`generate_data.py` parses these fields directly and seamlessly injects them into isolated environment variables (`AGENT_CONFIG`, `MODEL_ID`, `GCP_LOCATION`) for each specific worker process before running the tests in parallel.
Available pre-defined configurations for `AGENT_CONFIG` include:
- `NORMAL` (default)
- `OVER_PROVISIONED`
- `HIGH_TEMP`
- `WRONG_MAX_TOKENS`
- `WRONG_CANDIDATES`

### Automated Configuration Matrix Testing
A wrapper script is provided to automatically run the stress test across multiple configurations and models for benchmarking.

To run the suite with the default configurations :
```bash
./agents/my_test_app/generate_data.sh
```

**Available Arguments:**
- `-n`: Number of active users for load test (default: `1`).
- `-f`: Output file, an optional text file containing pipe-separated configurations/questions (default: `test_scenarios.txt`).

This script will pass the scenario file to `generate_data.py`, which natively processes all distinct scenarios in parallel using isolated multiprocessing workers.

### Unreliable Tool Simulation
The root agent includes an `unreliable_tool_agent` designed to simulate system failures, timeouts, and flaky behavior. By explicitly requesting actions like "simulate a flaky action", "timeout", or test a failure using an "unreliable tool" in the prompt, the root agent will accurately route to this specialized test case scenario.

### Generating Dynamic Scenarios
If you want to test the agent orchestration against a massive volume of randomized and highly-varied test payloads, use the Python script:

```bash
python agents/my_test_app/generate_test_scenarios.py
```

This built-in script dynamically generates pipe-delimited test case lines via `gemini-2.5-flash`. To overcome typical LLM generation limits while maximizing API performance, it utilizes parallel execution (`asyncio.gather`), sending chunks of concurrent requests to rapidly fetch the requested number of tests. 

* By default, the script generates `15` lines to `test_scenarios.txt` for quick testing.

Alternatively, you can provide CLI arguments to dynamically overwrite these parameters. For example, to generate a large volume (1600 lines) of test scenarios with a specific distribution:

```bash
python agents/my_test_app/generate_test_scenarios.py \
  --total-lines 60 \
  --output-file "test_scenarios_large.txt" \
  --max-questions 4 \
  --adk-pct 20 \
  --obs-pct 20
```

**Available Arguments:**
- `--total-lines`: Total number of test scenario lines to generate (default: `15`). The script optimizes generation in batches of 400 lines simultaneously.
- `--output-file`: The path where the generated scenarios will be saved (default: `test_scenarios_v15.txt`).
- `--max-questions`: Maximum number of sub-questions inside a single scenario line (default: `3`).
- `--adk-pct`: Percentage weight for ADK datastore knowledge questions (default: `15`).
- `--obs-pct`: Percentage weight for Observability datastore knowledge questions (default: `15`).
- `--bq-pct`: Percentage weight for BigQuery knowledge questions (default: `15`).
- `--google-search-pct`: Percentage weight for standard Google Search questions (default: `15`).
- `--unreliable-pct`: Percentage weight for questions testing the unreliable tool simulation (default: `5`).
- `--parallel-pct`: Percentage weight for questions testing parallel execution (default: `10`).
- `--config-test-pct`: Percentage weight for configuration benchmarking questions (default: `15`).
- `--complex-pct`: Percentage weight for complex, multi-step orchestration questions (default: `10`).

Once your output file is generated, you can feed this input directly to the stress test suite alongside the concurrency limit:

```bash
./agents/my_test_app/generate_data.sh -f agents/my_test_app/test_scenarios_large.txt
```
The testing suite will automatically parse each pip-delimited line from the input file and execute the parallel stress tests for each scenario configuration!