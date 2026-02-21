import logging
import os
import sys
import time
from pathlib import Path

import google.auth
from dotenv import load_dotenv
from google.adk.apps import App
from google.adk.plugins import LoggingPlugin
from google.adk.plugins.bigquery_agent_analytics_plugin import BigQueryLoggerConfig, BigQueryAgentAnalyticsPlugin

import google.auth
from google.adk.agents import Agent, LlmAgent, ParallelAgent
from google.adk.tools import google_search
from google.adk.tools.bigquery import BigQueryCredentialsConfig, BigQueryToolset
from google.adk.tools.vertex_ai_search_tool import VertexAiSearchTool
from google.genai import types


# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Set environment variables

_, project_id = google.auth.default()

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../.env"), override=True)

# --- Configuration ---
PROJECT_ID = os.environ.get("PROJECT_ID", project_id)

LOCATION = os.environ.get("LOCATION", "us-central1") # required for gemini-3 preview
MODEL_ID = os.environ.get("AGENT_MODEL_ID", "gemini-2.5-pro")

AGENT_EVENTS_TABLE_ID = os.environ.get("TABLE_ID")
DATASET_ID = os.environ.get("DATASET_ID")

# TODO Describe/Automate a manual step to create Vertex ai search corpus
SEARCH_APP_REGION = os.getenv("SEARCH_APP_REGION", "global")
DATASTORE_ID = os.getenv("WEB_DATASTORE_ID")

#SEARCH_APP = os.getenv("SEARCH_APP", "agentops_1769711212471")
# search_engine = (
#     f'projects/{PROJECT_ID}/locations/{SEARCH_APP_REGION}/collections/default_collection/engines/{SEARCH_APP}'
# )
# search_engine_tool = VertexAiSearchTool(search_engine_id=search_engine)

DATASTORE_PATH = f"projects/{PROJECT_ID}/locations/{SEARCH_APP_REGION}/collections/default_collection/dataStores/{DATASTORE_ID}"
search_data_tool = VertexAiSearchTool(data_store_id=DATASTORE_PATH)

print(f"DATASTORE_PATH={DATASTORE_PATH}")
if PROJECT_ID is None:
    raise ValueError("Project ID is not set. Please set GOOGLE_CLOUD_PROJECT "
                     "or ensure application default credentials include a project.")

# --- CRITICAL: Set environment variables BEFORE Gemini instantiation ---
os.environ['GOOGLE_CLOUD_PROJECT'] = PROJECT_ID
os.environ['GOOGLE_CLOUD_LOCATION'] = LOCATION
os.environ['GOOGLE_GENAI_USE_VERTEXAI'] = 'True'

# --- Initialize the Plugin with Config ---
bq_config = BigQueryLoggerConfig(
    enabled=True,
    # event_allowlist=["LLM_REQUEST", "LLM_RESPONSE"], # Only log these events
    max_content_length=500 * 1024, # 500 KB limit for inline text
    batch_size=1, # Default is 1 for low latency, increase for high throughput
    shutdown_timeout=10.0
)

bq_logging_plugin = BigQueryAgentAnalyticsPlugin(
    project_id=PROJECT_ID,
    dataset_id=DATASET_ID,
    table_id=AGENT_EVENTS_TABLE_ID,
    config=bq_config,
    location="us"
)

logger.info("Starting Agent")
# Add` shared library to path if we are running locally
# This is necessary for adk web or direct execution to find the shared module
CURRENT_DIR = Path(__file__).resolve().parent
SHARED_DIR = CURRENT_DIR.parent.parent.parent / "shared" / "py" / "src"
if SHARED_DIR.exists() and str(SHARED_DIR) not in sys.path:
    sys.path.append(str(SHARED_DIR))


NOK_CANDIDATE_COUNT=5
OK_CANDIDATE_COUNT=1
NOK_MAX_OUTPUT_TOKENS=100000
OK_MAX_OUTPUT_TOKENS=65000
LITTLE_MAX_OUTPUT_TOKENS=5000

WRONG_CONFIG1=types.GenerateContentConfig(
    top_k=5,
    top_p=0.1,
    candidate_count=NOK_CANDIDATE_COUNT,
    max_output_tokens=65000,
    presence_penalty=0.1,
    labels={"config_setting": "wrong_config1"},
)

WRONG_CONFIG2=types.GenerateContentConfig(
    top_k=5,
    top_p=0.1,
    candidate_count=OK_CANDIDATE_COUNT,
    max_output_tokens=NOK_MAX_OUTPUT_TOKENS,
    presence_penalty=0.1,
    labels={"config_setting": "wrong_config2"},
)

OK_CONFIG1=types.GenerateContentConfig(
    top_k=5,
    top_p=0.1,
    candidate_count=OK_CANDIDATE_COUNT,
    max_output_tokens=OK_MAX_OUTPUT_TOKENS,
    presence_penalty=0.1,
    labels={"config_setting": "ok_config1"},
)

OK_CONFIG2=types.GenerateContentConfig(
    top_k=5,
    top_p=0.1,
    candidate_count=OK_CANDIDATE_COUNT,
    max_output_tokens=LITTLE_MAX_OUTPUT_TOKENS,
    presence_penalty=0.1,
    labels={"config_setting": "ok_config2"},
)


def get_agent_config() -> types.GenerateContentConfig:
    config_name = os.environ.get("AGENT_CONFIG", "OK_CONFIG2")
    configs = {
        "WRONG_CONFIG1": WRONG_CONFIG1,
        "WRONG_CONFIG2": WRONG_CONFIG2,
        "OK_CONFIG1": OK_CONFIG1,
        "OK_CONFIG2": OK_CONFIG2,
    }
    logger.info(f"Using agent config: {config_name}")
    return configs.get(config_name, OK_CONFIG2)


# --- Initialize Tools and Model ---
credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
bigquery_toolset = BigQueryToolset(
    credentials_config=BigQueryCredentialsConfig(credentials=credentials)
)


def hello_tool(name: str) -> str:
    """
    A simple tool that returns a greeting.
    
    Args:
        name: The name of the person to greet.
    """
    return f"Hello, {name}!"


def raise_exception() -> str:
    """Throws a runtime exception for testing purposes."""
    logger.error("Throwing tool exception")
    # Raise directly so the framework catches it and triggers on_tool_error_callback
    raise RuntimeError("This is a test exception for Tool Error verification.")


def sleep(seconds: int) -> None:
    """Sleeps for one minute."""
    """Pauses the execution for a specified number of seconds.

    Args:
        seconds: The number of seconds to sleep.
    """
    logger.info(f"Going to sleep for {seconds} seconds...")
    time.sleep(seconds)
    logger.info("Finished sleeping")


def build_parallel_team(agent_index: int) -> LlmAgent:
    """Creates a dedicated analysis team for a specific latency dimension."""
    # 1. Primer Agent
    primer = LlmAgent(
        name=f"sleep_sub_agent_{agent_index}",
        model=MODEL_ID,
        description="A simple agent that can sleep.",
        instruction="You are a helpful assistant. If asked to sleep, use the sleep_one_minute tool. If user does not mention units, always assume those are seconds. SLeep 1 means sleep one second.",
        generate_content_config=types.GenerateContentConfig(
            temperature=0,
            labels={"llm.agent.name": f"sleep_sub_agent_{agent_index}"}
        ),

        tools=[sleep]
    )
    return primer

def create_agent() -> Agent:
    """
    Factory function to create the ADK Agent instance.
    """

    exception_agent = LlmAgent(
        name="raise_exception_agent",
        model=MODEL_ID,
        description="An agent that throws exceptions.",
        instruction="You are a simplified agent. When asked to crash or throw error, call the raise_exception tool.",
        tools=[raise_exception],
        generate_content_config=types.GenerateContentConfig(
            temperature=1,
            max_output_tokens=65000,
        ),
    )

    bigquery_agent = Agent(
        model=MODEL_ID,
        name="bigquery_agent",
        description=(
            "Agent to answer questions about BigQuery data and models and execute"
            " SQL queries."
        ),
        instruction=f"""\
            You are a data science agent with access to several BigQuery tools.
            You have access to the dataset `{PROJECT_ID}.{DATASET_ID}`.
            The main table containing agent events is `{AGENT_EVENTS_TABLE_ID}`.
            Use `list_tables` to see other available tables if needed.
            Make use of those tools to answer the user's questions.
        """,
        tools=[bigquery_toolset],
    )

    google_search_agent = Agent(
        name="google_search_agent",
        model="gemini-2.0-flash",
        description="Agent to answer questions using Google Search.",
        instruction="I can answer your questions by searching the internet. Just ask me anything!",
        tools=[google_search],
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
    )

    vertexai_search_agent = LlmAgent(
        name="vertexai_search_adk_web",
        model="gemini-2.0-flash",
        description="Answers questions about the Python Agent Development Kit (ADK) by querying a dedicated Vertex AI Search datastore containing content from google.github.io/adk-docs/.",
        instruction=(
            f"You are an expert assistant specializing in the Agent Development Kit (ADK) for Python. "
            f"Your knowledge is strictly limited to the information within the Vertex AI Search datastore: {DATASTORE_PATH}, "
            "which contains documentation from www.google.github.io/adk-docs/. "
            "ALWAYS use the 'search_data_tool' to query this datastore to answer questions about ADK Python features, development, and best practices. "
            "Base your answers solely on the search results from the tool. "
            "If the answer cannot be found within the datastore after a thorough search, respond with: "
            "'I could not find information on this topic in the ADK Python documentation.' "
            "Do not use any other knowledge or make assumptions."
        ),
        tools=[search_data_tool],
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
    )

    sleep_team = ParallelAgent(
        name="sleep_sub_agent",
        description="Runs multiple agents in parallel to execute sleep action by the user.",
        sub_agents=[build_parallel_team(ix) for ix in range(1, 4)])

    agent = LlmAgent(
        name="my_test_agent",
        model=MODEL_ID,
        description="A helpful agent to generate some user interactions.",
        instruction=(
            "You are a helpful assistant. "
            "Use the hello_tool to greet the user if they provide a name. "
            "Otherwise, introduce yourself as the Test Agent and use sub agents to delegate the task."
            "Use sub-agents to delegate tasks that you are not equipped to perform. If user asks to crash, call exception_agent "
        ),
        sub_agents=[vertexai_search_agent, google_search_agent, bigquery_agent, exception_agent, sleep_team],
        tools=[hello_tool, sleep],
        generate_content_config=get_agent_config(),
    )

    
    return agent

# Perform the instantiation for ADK to find
root_agent = create_agent()

app = App(root_agent=root_agent, name="my_test_app",
          plugins=[bq_logging_plugin, LoggingPlugin()], )