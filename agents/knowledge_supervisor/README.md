# knowledge-supervisor

Multi-agent supervisor that coordinates specialized sub-agents to answer user queries. Deployed as a Reasoning Engine on Vertex AI.

## Sub-Agents

| # | Agent | Description |
|---|-------|-------------|
| 1 | `pto_agent` | Remote A2A agent for PTO/sick leave balances, vacation planning, and working day calculations |
| 2 | `adk_documentation_agent` | Vertex AI Search datastore for ADK documentation |
| 3 | `bigquery_data_agent` | Queries BigQuery datasets using BigQuery toolset |
| 4 | `google_search_agent` | General web search via Google Search |
| 5 | `local_tools_agent` | Simulated DB lookups and numerical calculations |
| 6 | `parallel_db_lookup` | Parallel agent for multi-item DB lookups |
| 7 | `internal_docs_agent` | Company policy knowledge base (PTO, sick leave, hiring process, expenses, benefits, compliance, etc.) |
| 8 | `developer_docs_agent` | Google Developer Knowledge MCP server (GCP, Firebase, Android docs) - requires `DEVELOPER_KNOWLEDGE_API_KEY` |

## Project Structure

```
knowledge-supervisor/
├── app/
│   ├── agent.py               # Main supervisor + sub-agent definitions
│   ├── config.py              # Configuration and PTO agent URL discovery
│   └── app_utils/             # App utilities and helpers
├── deploy.sh                  # Deployment script (Agent Engine)
├── requirements.txt           # Python dependencies
└── tests/                     # Unit and integration tests
```

> 💡 **Tip:** Use [Gemini CLI](https://github.com/google-gemini/gemini-cli) for AI-assisted development - project context is pre-configured in `GEMINI.md`.

## Requirements

Before you begin, ensure you have:
- **uv**: Python package manager (used for all dependency management in this project) - [Install](https://docs.astral.sh/uv/getting-started/installation/) ([add packages](https://docs.astral.sh/uv/concepts/dependencies/) with `uv add <package>`)
- **Google Cloud SDK**: For GCP services - [Install](https://cloud.google.com/sdk/docs/install)
- **Terraform**: For infrastructure deployment - [Install](https://developer.hashicorp.com/terraform/downloads)
- **make**: Build automation tool - [Install](https://www.gnu.org/software/make/) (pre-installed on most Unix-based systems)


## Quick Start

Install required packages and launch the local development environment:

```bash
make install && make playground
```

## Commands

| Command              | Description                                                                                 |
| -------------------- | ------------------------------------------------------------------------------------------- |
| `make install`       | Install dependencies using uv                                                               |
| `make playground`    | Launch local development environment                                                        |
| `make lint`          | Run code quality checks                                                                     |
| `make test`          | Run unit and integration tests                                                              |
| `make deploy`        | Deploy agent to Agent Engine                                                                |
| `make register-gemini-enterprise` | Register deployed agent to Gemini Enterprise                                  |
| `make setup-dev-env` | Set up development environment resources using Terraform                                   |

For full command options and usage, refer to the [Makefile](Makefile).

## 🛠️ Project Management

| Command | What It Does |
|---------|--------------|
| `uvx agent-starter-pack setup-cicd` | One-command setup of entire CI/CD pipeline + infrastructure |
| `uvx agent-starter-pack upgrade` | Auto-upgrade to latest version while preserving customizations |
| `uvx agent-starter-pack extract` | Extract minimal, shareable version of your agent |

---

## Development

Edit your agent logic in `app/agent.py` and test with `make playground` - it auto-reloads on save.
Use notebooks in `notebooks/` for prototyping and Vertex AI Evaluation.
See the [development guide](https://googlecloudplatform.github.io/agent-starter-pack/guide/development-guide) for the full workflow.

## Environment Variables

Key environment variables (set in `.env` at project root):

| Variable | Description |
|----------|-------------|
| `PROJECT_ID` | GCP project ID |
| `SUPERVISOR_MODEL_ID` | Model for supervisor and sub-agents (default: `gemini-2.5-pro`) |
| `SUPERVISOR_REGION` | Deployment region (default: `us-central1`) |
| `PTO_AGENT_URL` | URL of deployed PTO agent (auto-discovered if not set) |
| `TEST_DATASTORE_ID` | Vertex AI Search datastore ID for ADK docs |
| `DEVELOPER_KNOWLEDGE_API_KEY` | API key for Google Developer Knowledge MCP server (optional) |

## Deployment

Deploy using the provided script:

```bash
./deploy.sh
```

This script discovers the PTO agent URL, stages files, resolves environment variables, grants IAM permissions, and deploys to Agent Engine as a Reasoning Engine.

## Observability

Built-in telemetry via `BigQueryAgentAnalyticsPlugin` exports to BigQuery for analysis by the observability agent.
