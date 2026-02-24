import logging
import os
import random
import sys
import time
from pathlib import Path

import google.auth
from dotenv import load_dotenv
from google.adk.agents import Agent, LlmAgent, ParallelAgent
from google.adk.apps import App
from google.adk.plugins import LoggingPlugin
from google.adk.plugins.bigquery_agent_analytics_plugin import BigQueryLoggerConfig, BigQueryAgentAnalyticsPlugin
from google.adk.tools import google_search
from google.adk.tools.bigquery import BigQueryCredentialsConfig, BigQueryToolset
from google.adk.tools.vertex_ai_search_tool import VertexAiSearchTool
from google.genai import types

try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    trace.set_tracer_provider(TracerProvider())
except ImportError:
    pass # OpenTelemetry is optional

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Configuration ---
_, project_id = google.auth.default()

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../.env"), override=False)

# --- Configuration ---
PROJECT_ID = os.environ.get("PROJECT_ID", project_id)

LOCATION = os.environ.get("LOCATION", "us-central1")
MODEL_ID = os.environ.get("MODEL_ID", "gemini-2.5-pro")

TABLE_ID = os.environ.get("TABLE_ID", "agent_events")
DATASET_ID = os.environ.get("DATASET_ID", "agent_analytics")

SEARCH_APP_REGION = os.getenv("SEARCH_APP_REGION", "global")
DATASTORE_ID = os.getenv("DATASTORE_ID")
WEB_DATASTORE_ID = os.getenv("WEB_DATASTORE_ID")

assert DATASTORE_ID, "DATASTORE_ID is not set"
assert WEB_DATASTORE_ID, "WEB_DATASTORE_ID is not set"
assert PROJECT_ID, "PROJECT_ID is not set"

DATASTORE_PATH = f"projects/{PROJECT_ID}/locations/{SEARCH_APP_REGION}/collections/default_collection/dataStores/{DATASTORE_ID}"
search_data_tool = VertexAiSearchTool(data_store_id=DATASTORE_PATH)

WEB_DATASTORE_PATH = f"projects/{PROJECT_ID}/locations/{SEARCH_APP_REGION}/collections/default_collection/dataStores/{WEB_DATASTORE_ID}"
search_web_data_tool = VertexAiSearchTool(data_store_id=WEB_DATASTORE_PATH)

print(f"DATASTORE_PATH={DATASTORE_PATH}")
print(f"WEB_DATASTORE_PATH={WEB_DATASTORE_PATH}")
print(f"MODEL_ID={MODEL_ID}")

os.environ['GOOGLE_CLOUD_PROJECT'] = PROJECT_ID
os.environ['GOOGLE_CLOUD_LOCATION'] = LOCATION
os.environ['GOOGLE_GENAI_USE_VERTEXAI'] = 'True'

# --- BigQuery Plugin Config ---
bq_config = BigQueryLoggerConfig(
    enabled=True,
    max_content_length=500 * 1024,
    batch_size=1,
    shutdown_timeout=10.0
)
bq_logging_plugin = BigQueryAgentAnalyticsPlugin(
    project_id=PROJECT_ID,
    dataset_id=DATASET_ID,
    table_id=TABLE_ID,
    config=bq_config,
    location="us"
)

# --- Add shared library to path ---
CURRENT_DIR = Path(__file__).resolve().parent
SHARED_DIR = CURRENT_DIR.parent.parent.parent / "shared" / "py" / "src"
if SHARED_DIR.exists() and str(SHARED_DIR) not in sys.path:
    sys.path.append(str(SHARED_DIR))

# --- Generation Configs for Testing Hypotheses ---
NORMAL_CONFIG = types.GenerateContentConfig(
    max_output_tokens=8192,
    labels={"config_setting": "normal"},
)
OVER_PROVISIONED_CONFIG = types.GenerateContentConfig( # For H2
    max_output_tokens=65000,
    labels={"config_setting": "over_provisioned"},
)
HIGH_TEMP_CONFIG = types.GenerateContentConfig( # For H13
    temperature=0.9,
    top_k=50,
    max_output_tokens=8192,
    labels={"config_setting": "high_temp"},
)

WRONG_MAX_OUTPUT_TOKENS_COUNT_CONFIG=types.GenerateContentConfig(
    top_k=5,
    top_p=0.1,
    candidate_count=1,
    max_output_tokens=100000, #NOK
    presence_penalty=0.1,
    labels={"config_setting": "wrong_max_output_tokens_count"},
)

WRONG_CANDIDATE_COUNT_CONFIG=types.GenerateContentConfig(
    top_k=5,
    top_p=0.1,
    candidate_count=5, #NOK
    max_output_tokens=8192,
    presence_penalty=0.1,
    labels={"config_setting": "wrong_candidate_count"},
)


def get_agent_config(config_name: str) -> types.GenerateContentConfig:
    configs = {
        "NORMAL": NORMAL_CONFIG,
        "OVER_PROVISIONED": OVER_PROVISIONED_CONFIG,
        "HIGH_TEMP": HIGH_TEMP_CONFIG,
        "WRONG_MAX_OUTPUT_TOKENS_COUNT_CONFIG": WRONG_MAX_OUTPUT_TOKENS_COUNT_CONFIG,
        "WRONG_CANDIDATE_COUNT_CONFIG": WRONG_CANDIDATE_COUNT_CONFIG,
    }
    return configs.get(config_name, NORMAL_CONFIG)

# --- Tools ---
credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
bigquery_toolset = BigQueryToolset(
    credentials_config=BigQueryCredentialsConfig(credentials=credentials)
)

def flaky_tool_simulation(query: str, tool_name: str = "unreliable_tool") -> str:
    """Simulates a tool that sometimes fails or is slow (H8, H9)."""
    logger.info(f"Performing flaky {tool_name} for: {query}")
    rand_val = random.random()
    if rand_val < 0.08: # 8% chance of timeout
        logger.error(f"Flaky {tool_name}: TIMEOUT")
        time.sleep(random.uniform(5, 10))
        raise TimeoutError(f"{tool_name} timed out for query: {query}")
    if rand_val < 0.16: # 8% chance of quota error
        logger.error(f"Flaky {tool_name}: QUOTA ERROR")
        raise RuntimeError(f"Quota exceeded for {tool_name} for query: {query}")

    if "very_slow_topic" in query: # H6 simulation
        time.sleep(random.uniform(4, 8))
    else:
        time.sleep(random.uniform(0.5, 2))

    return f"Simulated {tool_name} results for: {query}. More details can be found by searching for specific aspects."

def simulated_db_lookup(item_id: str) -> str:
    """Simulates a database lookup with variable latency (H6)."""
    delay = random.uniform(0.2, 1.0)
    if "large_record" in item_id:
        delay += random.uniform(2, 4)
    logger.info(f"DB Lookup for {item_id}, delaying for {delay:.2f}s")
    time.sleep(delay)
    return f"Data for item: {item_id}"

def complex_calculation(data: str) -> str:
    """Simulates a tool that does some complex processing."""
    delay = random.uniform(1, 3)
    logger.info(f"Performing complex calculation on {data}, delaying for {delay:.2f}s")
    time.sleep(delay)
    return f"Calculation result for {data}: {random.randint(100, 1000)}"

# --- Sub-Agents ---

def log_after_model(**kwargs):
    logger.info(f"*** AFTER MODEL CALLBACK ***")
    response = kwargs.get('response', None) or kwargs.get('llm_response', None)
    if response:
        logger.info(f"Raw Response object: {response}")

def log_after_tool(**kwargs):
    logger.info(f"*** AFTER TOOL CALLBACK ***")
    logger.info(f"Result: {kwargs.get('result', None)}")

def create_documentation_agent():
    return LlmAgent(
        name="adk_documentation_agent",
        model=MODEL_ID,
        description="Answers questions about the Python Agent Development Kit (ADK) by querying a dedicated Vertex AI Search datastore containing content from google.github.io/adk-docs/.",
        instruction=(
            "You are an expert assistant specializing in the Agent Development Kit (ADK) for Python. "
            f"Use the Vertex AI Search datastore at {DATASTORE_PATH} via the 'search_data_tool' to answer questions. "
            "Always search first, and then formulate a helpful, professional response based on what you find."
        ),
        tools=[search_data_tool],
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
    )

def create_observability_agent():
    return LlmAgent(
        name="ai_observability_agent",
        model=MODEL_ID,
        description="Answers questions about AI Agent Observability, Tracing, and Langfuse by searching the Vertex AI Search Web Datastore.",
        instruction=(
            "You are an expert assistant specializing in AI Observability. "
            f"Use the Vertex AI Search datastore at {WEB_DATASTORE_PATH} via the 'search_web_data_tool' to extract information to answer questions. "
            "Always search first, and then formulate a helpful, professional response based on what you find."
        ),
        tools=[search_web_data_tool],
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
    )

def create_bigquery_agent():
    return LlmAgent(
        name="bigquery_data_agent",
        model=MODEL_ID,
        description="Analyzes data in BigQuery datasets.",
        instruction=(
            f"You are a data analyst. Use the BigQuery tools to answer questions about data in `{PROJECT_ID}.{DATASET_ID}`. "
            f"The main table for events is `{TABLE_ID}`. Use `list_tables` if needed."
        ),
        tools=[bigquery_toolset],
        generate_content_config=get_agent_config(os.environ.get("BQ_AGENT_CONFIG", "NORMAL")),

    )

def create_google_search_agent():
    return LlmAgent(
        name="google_search_agent",
        model=MODEL_ID,
        description="Performs general web searches using Google Search.",
        instruction="Use the google_search tool to find information from the web.",
        tools=[google_search],
        generate_content_config=get_agent_config(os.environ.get("SEARCH_AGENT_CONFIG", "NORMAL")),
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True
    )

def create_unreliable_tool_agent():
    return LlmAgent(
        name="unreliable_tool_agent",
        model=MODEL_ID,
        description="Uses a simulated tool that is potentially slow or prone to failures. Use this agent when asked to simulate a slow response, failure, timeout, or flaky behavior for a request.",
        instruction="Use the flaky_tool_simulation tool to perform the action. Be prepared for potential delays or errors. If it fails, report the failure.",
        tools=[flaky_tool_simulation],
        generate_content_config=get_agent_config(os.environ.get("UNRELIABLE_AGENT_CONFIG", "NORMAL")),
    )

def create_parallel_lookup_agent():
    """Agent to test H4 and H7."""
    sub_agents = []
    for i in range(3): # Simulate 3 parallel workers
        agent = LlmAgent(
            name=f"lookup_worker_{i+1}",
            model=MODEL_ID,
            instruction="You will be given an item ID. Use the simulated_db_lookup tool to fetch the data for this single ID.",
            tools=[simulated_db_lookup],
            generate_content_config=types.GenerateContentConfig(labels={"config_setting": "lookup_worker"}),
            disallow_transfer_to_parent=True,
            disallow_transfer_to_peers=True,
        )
        sub_agents.append(agent)
    return ParallelAgent(
        name="parallel_db_lookup",
        description="Looks up multiple item details from a simulated database in parallel.",
        sub_agents=sub_agents,
    )

def create_config_test_agent(config_name: str):
    return LlmAgent(
        name=f"config_test_agent_{config_name.lower()}",
        model=MODEL_ID,
        description=f"Handles ANY user request that specifically mentions using the '{config_name}' configuration. If the prompt contains '{config_name}', you MUST route to this agent.",
        instruction=f"Respond to the user's query. You are operating under the {config_name} configuration.",
        tools=[complex_calculation], # Give it a tool to make it do something
        generate_content_config=get_agent_config(config_name),
    )

# --- Root Agent ---
def create_agent() -> Agent:
    doc_agent = create_documentation_agent()
    obs_agent = create_observability_agent()
    bq_agent = create_bigquery_agent()
    search_agent = create_google_search_agent()
    unreliable_agent = create_unreliable_tool_agent()
    parallel_agent = create_parallel_lookup_agent()
    config_normal_agent = create_config_test_agent("NORMAL")
    config_over_provisioned_agent = create_config_test_agent("OVER_PROVISIONED")
    config_high_temp_agent = create_config_test_agent("HIGH_TEMP")
    config_wrong_max_tokens_agent = create_config_test_agent("WRONG_MAX_OUTPUT_TOKENS_COUNT_CONFIG")
    config_wrong_candidate_agent = create_config_test_agent("WRONG_CANDIDATE_COUNT_CONFIG")
    config_invalid_model_agent = create_config_test_agent("INVALID_MODEL_CONFIG")

    root_agent = LlmAgent(
        name="knowledge_qa_supervisor",
        model=MODEL_ID,
        description="Answers questions by delegating to specialized sub-agents.",
        instruction=(
            "You are a strict router. Your ONLY job is to route the user's input to the correct sub-agent based on these EXACT rules:\n"
            "1. If the input contains a _CONFIG keyword (e.g., 'WRONG_MAX_OUTPUT_TOKENS_COUNT_CONFIG', 'INVALID_MODEL_CONFIG', 'NORMAL', 'OVER_PROVISIONED', 'HIGH_TEMP'), you MUST route it to the corresponding 'config_test_agent_...'.\n"
            "2. If the input mentions 'unreliable tool', 'flaky action', 'timeout', 'simulate', or asks to test a failure or a slow response, you MUST route it to 'unreliable_tool_agent'.\n"
            "3. If the input asks to fetch/lookup multiple items in parallel (e.g., 'parallel lookup', 'Retrieve ... in parallel'), you MUST route it to 'parallel_db_lookup'.\n"
            "4. If the input asks about BigQuery datasets, tables, or records (e.g., '`agent_events_test`', '`prod_events`'), you MUST route it to 'bigquery_data_agent'.\n"
            "5. If the input asks about ADK documentation, how to use ADK tools, or ADK Application structure, you MUST route it to 'adk_documentation_agent'.\n"
            "6. If the input asks about AI Agent Observability, Tracing, Data Models, or Langfuse, you MUST route it to 'ai_observability_agent'.\n"
            "7. For general knowledge questions (e.g., 'Who is the CEO...', 'weather in...'), you MUST route it to 'google_search_agent'.\n"
            "Failure to follow these exact deterministic routing rules is unacceptable."
        ),
        sub_agents=[
            doc_agent, obs_agent, bq_agent, search_agent, unreliable_agent, parallel_agent,
            config_normal_agent, config_over_provisioned_agent, config_high_temp_agent,
            config_wrong_max_tokens_agent, config_wrong_candidate_agent, config_invalid_model_agent
        ],
        generate_content_config=types.GenerateContentConfig(labels={"config_setting": "root_agent"})
    )
    return root_agent

# Perform the instantiation for ADK to find
root_agent = create_agent()
app = App(root_agent=root_agent, name="my_test_app", plugins=[bq_logging_plugin, LoggingPlugin()])
