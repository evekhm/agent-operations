# agent1-client

ReAct agent with A2A protocol [experimental]
Agent generated with [`googleCloudPlatform/agent-starter-pack`](https://github.com/GoogleCloudPlatform/agent-starter-pack) version `0.39.6`

## Project Structure

```
agent1-client/
├── app/         # Core agent code
│   ├── agent.py               # Main agent logic
│   ├── agent_engine_app.py    # Agent Engine application logic
│   └── app_utils/             # App utilities and helpers
├── tests/                     # Unit, integration, and load tests
├── GEMINI.md                  # AI-assisted development guide
├── Makefile                   # Development commands
└── pyproject.toml             # Project dependencies
```

> 💡 **Tip:** Use [Gemini CLI](https://github.com/google-gemini/gemini-cli) for AI-assisted development - project context is pre-configured in `GEMINI.md`.

## Requirements

Before you begin, ensure you have:
- **uv**: Python package manager (used for all dependency management in this project) - [Install](https://docs.astral.sh/uv/getting-started/installation/) ([add packages](https://docs.astral.sh/uv/concepts/dependencies/) with `uv add <package>`)
- **Google Cloud SDK**: For GCP services - [Install](https://cloud.google.com/sdk/docs/install)
- **make**: Build automation tool - [Install](https://www.gnu.org/software/make/) (pre-installed on most Unix-based systems)


## Quick Start


### Local A2A Testing
To test the A2A communication locally, you need to run both agents in separate terminals.

**1. Start the Server (`agent2-server`)**
```bash
cd ../agent2-server
uv run adk api_server --port 8001 --a2a
```

**2. Start the Client (`agent1-client`)**
```bash
cd ../agent1-client
AGENT2_SERVER_URL="http://localhost:8001" uv run adk run app

```
Then type: 
`What is the weather in San Francisco?`
### Production GCP Deployment
1. Authenticate with Google Cloud:
   ```bash
   gcloud auth login --update-adc
   gcloud config set project <YOUR_PROJECT_ID>
   ```
2. Deploy the Server:
   ```bash
   cd ../agent2-server
   make deploy
   ```
   *Note the deployed Service URL output.*
3. Reconfigure and Deploy the Client:
   * Update `app/agent.py` in `agent1-client` to replace the `localhost:8081` URL with the production URL of `agent2-server`.
   ```bash
   cd ../agent1-client
   make deploy
   ```
4. Test the production interaction using the provided Agent Engine Playground link.

---

## Development

Edit your agent logic in `app/agent.py` and test with `make playground` - it auto-reloads on save.
See the [development guide](https://googlecloudplatform.github.io/agent-starter-pack/guide/development-guide) for the full workflow.

## Deployment

```bash
gcloud config set project <your-project-id>
make deploy
```

To add CI/CD and Terraform, run `uvx agent-starter-pack enhance`.
To set up your production infrastructure, run `uvx agent-starter-pack setup-cicd`.
See the [deployment guide](https://googlecloudplatform.github.io/agent-starter-pack/guide/deployment) for details.

## Observability

Built-in telemetry exports to Cloud Trace, BigQuery, and Cloud Logging.
See the [observability guide](https://googlecloudplatform.github.io/agent-starter-pack/guide/observability) for queries and dashboards.

## A2A Inspector

This agent supports the [A2A Protocol](https://a2a-protocol.org/). Use `make inspector` to test interoperability.
See the [A2A Inspector docs](https://github.com/a2aproject/a2a-inspector) for details.
