# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models import Gemini
from google.adk.tools import LongRunningFunctionTool
from google.genai import types
from google.adk.plugins import LoggingPlugin
from google.adk.plugins.bigquery_agent_analytics_plugin import BigQueryLoggerConfig, BigQueryAgentAnalyticsPlugin
import os
import google.auth
import subprocess

from dotenv import load_dotenv

# Load .env from project root
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../.env"), override=True)

_, project_id = google.auth.default()
os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
os.environ["GOOGLE_CLOUD_LOCATION"] = "global"
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"

DATASET_ID = os.getenv('DATASET_ID', "agent_ops_demo")
DATASET_LOCATION = os.getenv('DATASET_LOCATION', "us-central1")
TABLE_ID = os.getenv('TABLE_ID', "agent_events")

def request_user_input(message: str) -> dict:
    """Request additional input from the user.

    Use this tool when you need more information from the user to complete a task.
    Calling this tool will pause execution until the user responds.

    Args:
        message: The question or clarification request to show the user.
    """
    return {"status": "pending", "message": message}


from google.adk.agents.remote_a2a_agent import RemoteA2aAgent
from google.adk.tools.agent_tool import AgentTool

def discover_agent2_server_url() -> str:
    """Discovers the agent2-server URL using .env fallback to Cloud Run."""
    # 1. Check .env first
    env_url = os.getenv("AGENT2_SERVER_URL")
    if env_url:
        return env_url

    # 2. Fallback to Cloud Run discovery
    project_id = os.getenv("PROJECT_ID")
    region = os.getenv("DATASET_LOCATION", "us-central1")
    if not project_id:
        return "http://localhost:8001" # No project ID, assume local

    cmd = [
        "gcloud", "run", "services", "describe", "agent2-server",
        f"--project={project_id}",
        f"--region={region}",
        "--format=value(status.url)"
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        discovered_url = result.stdout.strip()
        if discovered_url:
            return discovered_url
    except Exception:
        pass # Ignore errors and move to final fallback

    # 3. Final fallback to local
    return "http://localhost:8001"

server_url = discover_agent2_server_url()
agent_card_path = f"{server_url}/a2a/app/.well-known/agent-card.json"

agent2_server = RemoteA2aAgent(
    name="agent2_server",
    description="A remote agent that provides weather and current time information for cities.",
    agent_card=agent_card_path
)

root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model="gemini-3-flash-preview",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    description="A general-purpose assistant that delegates weather and time queries to a remote agent.",
    instruction=(
        "You are a helpful AI assistant. "
        "You do NOT have any knowledge about weather or current time. "
        "For any weather or time-related questions, you MUST delegate to agent2_server. "
        "Do not attempt to answer weather or time questions yourself."
    ),
    # sub_agents=[agent2_server],
    tools=[
        AgentTool(agent=agent2_server),
        LongRunningFunctionTool(func=request_user_input),
    ],
)

bq_config = BigQueryLoggerConfig(
    enabled=True,
    max_content_length=500 * 1024,
    batch_size=1,
    shutdown_timeout=10.0
)
bq_logging_plugin = BigQueryAgentAnalyticsPlugin(
    project_id=project_id,
    dataset_id=DATASET_ID,
    table_id=TABLE_ID,
    config=bq_config,
    location="us-central1"
)

app = App(
    root_agent=root_agent,
    name="app",
    plugins=[bq_logging_plugin, LoggingPlugin()]
)
