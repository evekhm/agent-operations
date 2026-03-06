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
    # Add project root to sys.path to import app_utils
    _root_dir = Path(__file__).resolve().parent.parent.parent
    if str(_root_dir) not in sys.path:
        sys.path.insert(0, str(_root_dir))
    
    from app_utils.telemetry import setup_telemetry
    setup_telemetry()
except ImportError as e:
    logging.warning(f"OpenTelemetry is optional, could not import: {e}")

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Load Default Env ---
_, default_project_id = google.auth.default()
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../.env"), override=False)

# --- Add shared library to path ---
CURRENT_DIR = Path(__file__).resolve().parent
SHARED_DIR = CURRENT_DIR.parent.parent.parent / "shared" / "py" / "src"
if SHARED_DIR.exists() and str(SHARED_DIR) not in sys.path:
    sys.path.append(str(SHARED_DIR))

# --- Generation Configs (Stateless) ---
NORMAL_CONFIG = types.GenerateContentConfig(
    max_output_tokens=8192,
    labels={"config_setting": "normal"},
)
OVER_PROVISIONED_CONFIG = types.GenerateContentConfig(
    max_output_tokens=65000,
    labels={"config_setting": "over_provisioned"},
)
HIGH_TEMP_CONFIG = types.GenerateContentConfig(
    temperature=0.9,
    top_k=50,
    max_output_tokens=8192,
    labels={"config_setting": "high_temp"},
)

WRONG_MAX_TOKENS = types.GenerateContentConfig(
    top_k=5,
    top_p=0.1,
    candidate_count=1,
    max_output_tokens=65538,
    presence_penalty=0.1,
    labels={"config_setting": "wrong_max_output_tokens_count"},
)

WRONG_CANDIDATES = types.GenerateContentConfig(
    top_k=5,
    top_p=0.1,
    candidate_count=5,
    max_output_tokens=8192,
    presence_penalty=0.1,
    labels={"config_setting": "wrong_candidate_count"},
)

def get_agent_config(config_name: str) -> types.GenerateContentConfig:
    configs = {
        "NORMAL": NORMAL_CONFIG,
        "OVER_PROVISIONED": OVER_PROVISIONED_CONFIG,
        "HIGH_TEMP": HIGH_TEMP_CONFIG,
        "WRONG_MAX_TOKENS": WRONG_MAX_TOKENS,
        "WRONG_CANDIDATES": WRONG_CANDIDATES,
    }
    return configs.get(config_name, NORMAL_CONFIG)

# --- Tools (Stateless) ---
credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
bigquery_toolset = BigQueryToolset(
    credentials_config=BigQueryCredentialsConfig(credentials=credentials)
)

def flaky_tool_simulation(query: str, tool_name: str = "unreliable_tool") -> str:
    """Simulates a tool that sometimes fails or is slow."""
    logger.info(f"Performing flaky {tool_name} for: {query}")
    rand_val = random.random()
    if rand_val < 0.08:
        logger.error(f"Flaky {tool_name}: TIMEOUT")
        time.sleep(random.uniform(5, 10))
        raise TimeoutError(f"{tool_name} timed out for query: {query}")
    if rand_val < 0.16:
        logger.error(f"Flaky {tool_name}: QUOTA ERROR")
        raise RuntimeError(f"Quota exceeded for {tool_name} for query: {query}")

    if "very_slow_topic" in query:
        time.sleep(random.uniform(4, 8))
    else:
        time.sleep(random.uniform(0.5, 2))

    return f"Simulated {tool_name} results for: {query}. More details can be found by searching for specific aspects."

def simulated_db_lookup(item_id: str) -> str:
    """Simulates a database lookup with variable latency."""
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


class AgentFactory:
    """Factory to cleanly build the ADK Agent application injecting variables safely."""
    
    def __init__(self, env_config=None):
        self.env = env_config if env_config is not None else os.environ
        
        self.project_id = self.env.get("TEST_PROJECT_ID", default_project_id)
        self.location = self.env.get("TEST_AGENT_LOCATION", "us-central1")
        self.model_id = self.env.get("TEST_AGENT_MODEL_ID", "gemini-2.5-pro")

        self.table_id = self.env.get("TEST_TABLE_ID", "agent_events")
        self.dataset_id = self.env.get("TEST_DATASET_ID", "agent_analytics")
        self.location = self.env.get("TEST_AGENT_LOCATION", "us-central1")
        self.bq_location = self.env.get("TEST_BQ_LOCATION", "us")

        self.search_app_region = self.env.get("TEST_DATASTORE_LOCATION", "global")
        self.datastore_id = self.env.get("TEST_DATASTORE_ID")
        self.web_datastore_id = self.env.get("TEST_WEB_DATASTORE_ID")

        assert self.datastore_id, "TEST_DATASTORE_ID is not set"
        assert self.web_datastore_id, "TEST_WEB_DATASTORE_ID is not set"
        assert self.project_id, "TEST_PROJECT_ID is not set"

        # Apply environment overrides required by ADK core
        os.environ['GOOGLE_CLOUD_PROJECT'] = self.project_id
        os.environ['GOOGLE_CLOUD_LOCATION'] = self.location
        os.environ['GOOGLE_GENAI_USE_VERTEXAI'] = 'True'
        
        # Datastore tools
        self.datastore_path = f"projects/{self.project_id}/locations/{self.search_app_region}/collections/default_collection/dataStores/{self.datastore_id}"
        self.search_data_tool = VertexAiSearchTool(data_store_id=self.datastore_path)

        self.web_datastore_path = f"projects/{self.project_id}/locations/{self.search_app_region}/collections/default_collection/dataStores/{self.web_datastore_id}"
        self.search_web_data_tool = VertexAiSearchTool(data_store_id=self.web_datastore_path)

    def create_bq_plugin(self):
        bq_config = BigQueryLoggerConfig(
            enabled=True,
            max_content_length=500 * 1024,
            batch_size=1,
            shutdown_timeout=10.0
        )
        return BigQueryAgentAnalyticsPlugin(
            project_id=self.project_id,
            dataset_id=self.dataset_id,
            table_id=self.table_id,
            config=bq_config,
            location=self.bq_location
        )
        
    def create_documentation_agent(self):
        return LlmAgent(
            name="adk_documentation_agent",
            model=self.model_id,
            description="Answers questions about the Python Agent Development Kit (ADK) by querying a dedicated Vertex AI Search datastore containing content from google.github.io/adk-docs/.",
            instruction=(
                "You are an expert assistant specializing in the Agent Development Kit (ADK) for Python. "
                f"Use the Vertex AI Search datastore at {self.datastore_path} via the 'search_data_tool' to answer questions. "
                "Always search first, and then formulate a helpful, professional response based on what you find."
            ),
            tools=[self.search_data_tool],
            disallow_transfer_to_parent=True,
            disallow_transfer_to_peers=True,
        )

    def create_observability_agent(self):
        return LlmAgent(
            name="ai_observability_agent",
            model=self.model_id,
            description="Answers questions about AI Agent Observability, Tracing, and Langfuse by searching the Vertex AI Search Web Datastore.",
            instruction=(
                "You are an expert assistant specializing in AI Observability. "
                f"Use the Vertex AI Search datastore at {self.web_datastore_path} via the 'search_web_data_tool' to extract information to answer questions. "
                "Always search first, and then formulate a helpful, professional response based on what you find."
            ),
            tools=[self.search_web_data_tool],
            disallow_transfer_to_parent=True,
            disallow_transfer_to_peers=True,
        )

    def create_bigquery_agent(self):
        return LlmAgent(
            name="bigquery_data_agent",
            model=self.model_id,
            description="Analyzes data in BigQuery datasets.",
            instruction=(
                f"You are a data analyst. Use the BigQuery tools to answer questions about data in `{self.project_id}.{self.dataset_id}`. "
                f"The main table for events is `{self.table_id}`. Use `list_tables` if needed."
            ),
            tools=[bigquery_toolset],
            generate_content_config=get_agent_config(self.env.get("BQ_AGENT_CONFIG", "NORMAL")),
        )

    def create_google_search_agent(self):
        return LlmAgent(
            name="google_search_agent",
            model=self.model_id,
            description="Performs general web searches using Google Search.",
            instruction="Use the google_search tool to find information from the web.",
            tools=[google_search],
            generate_content_config=get_agent_config(self.env.get("SEARCH_AGENT_CONFIG", "NORMAL")),
            disallow_transfer_to_parent=True,
            disallow_transfer_to_peers=True
        )

    def create_unreliable_tool_agent(self):
        return LlmAgent(
            name="unreliable_tool_agent",
            model=self.model_id,
            description="Uses a simulated tool that is potentially slow or prone to failures. Use this agent when asked to simulate a slow response, failure, timeout, or flaky behavior for a request.",
            instruction="Use the flaky_tool_simulation tool to perform the action. Be prepared for potential delays or errors. If it fails, report the failure.",
            tools=[flaky_tool_simulation],
            generate_content_config=get_agent_config(self.env.get("UNRELIABLE_AGENT_CONFIG", "NORMAL")),
        )

    def create_parallel_lookup_agent(self):
        sub_agents = []
        for i in range(3):
            agent = LlmAgent(
                name=f"lookup_worker_{i+1}",
                model=self.model_id,
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

    def create_config_test_agent(self, config_name: str):
        return LlmAgent(
            name=f"config_test_agent_{config_name.lower()}",
            model=self.model_id,
            description=f"Handles ANY user request that specifically mentions using the '{config_name}' configuration. If the prompt contains '{config_name}', you MUST route to this agent.",
            instruction=f"Respond to the user's query. You are operating under the {config_name} configuration.",
            tools=[complex_calculation],
            generate_content_config=get_agent_config(config_name),
        )

    def create_root_agent(self) -> Agent:
        doc_agent = self.create_documentation_agent()
        obs_agent = self.create_observability_agent()
        bq_agent = self.create_bigquery_agent()
        search_agent = self.create_google_search_agent()
        unreliable_agent = self.create_unreliable_tool_agent()
        parallel_agent = self.create_parallel_lookup_agent()
        config_normal_agent = self.create_config_test_agent("NORMAL")
        config_over_provisioned_agent = self.create_config_test_agent("OVER_PROVISIONED")
        config_high_temp_agent = self.create_config_test_agent("HIGH_TEMP")
        config_wrong_max_tokens_agent = self.create_config_test_agent("WRONG_MAX_TOKENS")
        config_wrong_candidate_agent = self.create_config_test_agent("WRONG_CANDIDATES")
        config_invalid_model_agent = self.create_config_test_agent("INVALID_MODEL_CONFIG")

        return LlmAgent(
            name="knowledge_qa_supervisor",
            model=self.model_id,
            description="Answers questions by delegating to specialized sub-agents.",
            instruction=(
                "You are a strict router. Your ONLY job is to route the user's input to the correct sub-agent based on these EXACT rules:\n"
                "1. If the input contains a _CONFIG keyword (e.g., 'WRONG_MAX_TOKENS', 'INVALID_MODEL_CONFIG', 'NORMAL', 'OVER_PROVISIONED', 'HIGH_TEMP'), you MUST route it to the corresponding 'config_test_agent_...'.\n"
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

# Instantiate the Default App for standard ADK CLI execution!
_default_factory = AgentFactory(os.environ)
root_agent = _default_factory.create_root_agent()
bq_logging_plugin = _default_factory.create_bq_plugin()

app = App(
    root_agent=root_agent, 
    name="my_test_app", 
    plugins=[bq_logging_plugin, LoggingPlugin()]
)
