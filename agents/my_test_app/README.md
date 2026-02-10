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