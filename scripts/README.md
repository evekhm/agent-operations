# Scripts

Utility and testing scripts for the Agent Operations project.

## Local Testing (No Deployment Required)

These scripts run the PTO agent and knowledge supervisor locally using `adk api_server`, then generate load against them via HTTP. No cloud deployments needed.

### Quick Start

```bash
# Full end-to-end: starts both agents, runs 5-min load test, cleans up on Ctrl+C
./scripts/local_test_all.sh

# Quick smoke test
CONCURRENCY=1 DURATION_MINUTES=1 ./scripts/local_test_all.sh

# Start agents only, then test manually via curl or the ADK web UI
./scripts/local_test_all.sh --interactive
```

### Running Each Piece Separately

Use three separate terminals:

| Terminal | Script | What it does |
|----------|--------|--------------|
| 1 | `./scripts/local_test_start_pto.sh` | Starts PTO agent on port 8001 with A2A enabled |
| 2 | `./scripts/local_test_start_supervisor.sh` | Starts knowledge supervisor on port 8000 (waits for PTO agent) |
| 3 | `./scripts/local_test_load.sh` | Generates load against the local supervisor |

### Architecture

```
                          +-----------------+
                          | Load Generator  |
                          | (HTTP client)   |
                          +--------+--------+
                                   |
                                   v
                          +--------+--------+
                          | Knowledge       |
                          | Supervisor      |
                          | :8000           |
                          +--------+--------+
                                   |
       +----------+--------+------+------+--------+-----------+
       |          |        |      |      |        |           |
       v          v        v      v      v        v           v
  +----+---+ +---+---+ +--+--+ +-+-+ +--+--+ +---+----+ +---+-------+
  |  PTO   | |  BQ   | |Int. | |ADK| |Local| |Google  | |Developer  |
  | Agent  | | Data  | |Docs | |Doc| |Tools| |Search  | |Docs (MCP) |
  | (A2A)  | | Agent | |     | |   | |     | |        | |           |
  +--------+ +-------+ +-----+ +---+ +-----+ +--------+ +-----------+
```

### Configuration

All scripts source `.env` from the project root. Override via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `PTO_PORT` | `8001` | Port for the local PTO agent |
| `SUPERVISOR_PORT` | `8000` | Port for the local knowledge supervisor |
| `TOPICS_CONFIG` | `pto and sick leave balances:3,...` | Topic:count pairs for question generation |
| `CONCURRENCY` | `3` | Number of concurrent requests |
| `DURATION_MINUTES` | `5` | How long the load test runs |

### Logs

When using `local_test_all.sh`, agent logs are written to:
- `/tmp/pto_agent.log`
- `/tmp/knowledge_supervisor.log`

### Files

| File | Description |
|------|-------------|
| `local_test_all.sh` | All-in-one script: starts both agents, runs load test, cleans up |
| `local_test_start_pto.sh` | Starts PTO agent standalone (port 8001, A2A) |
| `local_test_start_supervisor.sh` | Starts knowledge supervisor standalone (port 8000) |
| `local_test_load.sh` | Runs load generator against a running local supervisor |
| `local_load_generator.py` | Python load generator that calls the ADK API server over HTTP |

## Other Scripts

| File | Description |
|------|-------------|
| `demo_a2a_extraction_gap.sh` | Demonstrates A2A trace extraction gap workaround |
