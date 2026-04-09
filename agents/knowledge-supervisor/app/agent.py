import logging
import os
import random
import sys
import time

from google.adk.agents import Agent, LlmAgent, ParallelAgent
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent
from google.adk.apps import App
from google.adk.models import Gemini
from google.adk.plugins import LoggingPlugin
from google.adk.tools import google_search
from google.adk.tools.bigquery import BigQueryCredentialsConfig, BigQueryToolset
from google.adk.tools.vertex_ai_search_tool import VertexAiSearchTool
from google.genai import types

sys.path.append(os.path.abspath(os.path.dirname(__file__)))
import httpx
import google.auth
import google.auth.transport.requests
import google.oauth2.id_token
import json

from .config import (
    discover_pto_agent_url,
    SUPERVISOR_DISPLAY_NAME,
    MODEL_ID,
    PROJECT_ID,
    DATASTORE_LOCATION,
    DATASTORE_ID,
    WEB_DATASTORE_ID,
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

server_url = discover_pto_agent_url()
logger.info(f"Discovered PTO agent URL: {server_url}")

class CloudRunAuth(httpx.Auth):
    def __init__(self, audience: str):
        self.audience = audience
        self.auth_req = google.auth.transport.requests.Request()

    def auth_flow(self, request):
        logger.info(f"CloudRunAuth: Attempting to get auth token for {self.audience}")
        env_token = os.getenv("A2A_ID_TOKEN")
        if env_token:
            logger.info("CloudRunAuth: Using token from environment variable A2A_ID_TOKEN")
            token = env_token
        else:
            try:
                logger.info("CloudRunAuth: Fetching ID token via google.oauth2.id_token")
                token = google.oauth2.id_token.fetch_id_token(self.auth_req, self.audience)
            except Exception as e:
                logger.warning(f"CloudRunAuth: Failed to fetch ID token via SDK: {e}. Trying gcloud...")
                try:
                    import subprocess
                    result = subprocess.run(["gcloud", "auth", "print-identity-token", "--quiet"], capture_output=True, text=True, check=True)
                    token = result.stdout.strip()
                    logger.info("CloudRunAuth: Successfully fetched token via gcloud")
                except Exception as e2:
                    logger.error(f"CloudRunAuth: Failed to fetch ID token via gcloud: {e2}")
                    raise Exception(f"Failed to fetch ID token via SDK and gcloud: {e2}")
        request.headers['Authorization'] = f"Bearer {token}"
        yield request

class CardInterceptClient(httpx.AsyncClient):
    def __init__(self, server_url, **kwargs):
        super().__init__(**kwargs)
        self.server_url = server_url

    async def request(self, method, url, **kwargs):
        logger.info(f"CardInterceptClient: Request {method} {url}")
        response = await super().request(method, url, **kwargs)
        if method == "GET" and "/.well-known/agent-card.json" in str(url):
             logger.info("CardInterceptClient: Intercepting agent card request")
             try:
                  data = response.json()
                  logger.info(f"CardInterceptClient: Original card data URL: {data.get('url')}")
                  data['url'] = f"{self.server_url}/a2a/pto_agent"
                  content = json.dumps(data).encode('utf-8')
                  response = httpx.Response(
                      status_code=response.status_code,
                      headers=response.headers,
                      content=content,
                      request=response.request
                  )
                  logger.info(f"CardInterceptClient: Overwrote card URL to: {data['url']}")
             except Exception as e:
                  logger.error(f"CardInterceptClient: Failed to modify card: {e}")
                  pass
        return response

auth = None
if server_url.startswith("https://"):
    logger.info("Enabling CloudRunAuth for HTTPS URL")
    auth = CloudRunAuth(audience=server_url)

auth_client = CardInterceptClient(server_url=server_url, auth=auth, timeout=60.0)

logger.info(f"Creating RemoteA2aAgent pointing to {server_url}/.well-known/agent-card.json")
pto_remote_agent = RemoteA2aAgent(
    name="pto_agent",
    description="A remote agent that calculates remaining time off and work days.",
    agent_card=f"{server_url}/a2a/pto_agent/.well-known/agent-card.json",
    httpx_client=auth_client
)

# --- Local Tools ---

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

def search_internal_docs(query: str) -> str:
    """Searches the internal company documentation knowledge base for policies, procedures, and guidelines."""
    delay = random.uniform(0.3, 0.8)
    logger.info(f"Searching internal docs for: {query}")
    time.sleep(delay)
    return "No matching documents found in the knowledge base."

# --- Vertex AI Search Tools ---

datastore_search_tool = None
web_search_tool = None

if DATASTORE_ID and PROJECT_ID:
    datastore_path = f"projects/{PROJECT_ID}/locations/{DATASTORE_LOCATION}/collections/default_collection/dataStores/{DATASTORE_ID}"
    datastore_search_tool = VertexAiSearchTool(data_store_id=datastore_path)
    logger.info(f"Configured Vertex AI Search datastore: {datastore_path}")

if WEB_DATASTORE_ID and PROJECT_ID:
    web_datastore_path = f"projects/{PROJECT_ID}/locations/{DATASTORE_LOCATION}/collections/default_collection/dataStores/{WEB_DATASTORE_ID}"
    web_search_tool = VertexAiSearchTool(data_store_id=web_datastore_path)
    logger.info(f"Configured Vertex AI Search web datastore: {web_datastore_path}")

# --- BigQuery Toolset ---

credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
bigquery_toolset = BigQueryToolset(
    credentials_config=BigQueryCredentialsConfig(credentials=credentials)
)

from google.adk.plugins.bigquery_agent_analytics_plugin import BigQueryLoggerConfig, BigQueryAgentAnalyticsPlugin
from .config import project_id, DATASET_ID, DATASET_LOCATION, TABLE_ID


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
    location=DATASET_LOCATION
)

# --- Sub-Agents ---

sub_agents = []

# 1. Remote A2A: PTO Agent
sub_agents.append(pto_remote_agent)

# 2. Vertex AI Search: ADK Documentation
if datastore_search_tool:
    adk_documentation_agent = LlmAgent(
        name="adk_documentation_agent",
        model=MODEL_ID,
        description="Answers questions about the Python Agent Development Kit (ADK) by querying a Vertex AI Search datastore containing ADK documentation.",
        instruction=(
            "You are an expert assistant specializing in the Agent Development Kit (ADK) for Python. "
            "Use the Vertex AI Search datastore tool to answer questions. "
            "Always search first, then formulate a helpful response based on what you find."
        ),
        tools=[datastore_search_tool],
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
    )
    sub_agents.append(adk_documentation_agent)

# 3. Vertex AI Search: AI Observability / Web Docs
if web_search_tool:
    ai_observability_agent = LlmAgent(
        name="ai_observability_agent",
        model=MODEL_ID,
        description="Answers questions about AI Agent Observability, Tracing, and monitoring by searching the Vertex AI Search Web Datastore.",
        instruction=(
            "You are an expert assistant specializing in AI Observability. "
            "Use the Vertex AI Search datastore tool to extract information to answer questions. "
            "Always search first, then formulate a helpful response based on what you find."
        ),
        tools=[web_search_tool],
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
    )
    sub_agents.append(ai_observability_agent)

# 4. BigQuery Data Agent
bigquery_data_agent = LlmAgent(
    name="bigquery_data_agent",
    model=MODEL_ID,
    description="Analyzes data in BigQuery datasets. Use this for questions about querying data, tables, or records in BigQuery.",
    instruction=(
        f"You are a data analyst. Use the BigQuery tools to answer questions about data in the project. "
        f"Use `list_tables` to discover available tables. "
        f"CRITICAL: The timestamp column is 'timestamp', not 'event_time'. "
        f"You can query JSON columns using JSON_EXTRACT_SCALAR(). "
        f"Avoid casting JSON directly to STRING or comparing JSON directly to strings."
    ),
    tools=[bigquery_toolset],
)
sub_agents.append(bigquery_data_agent)

# 5. Google Search Agent
google_search_agent = LlmAgent(
    name="google_search_agent",
    model=MODEL_ID,
    description="Performs general web searches using Google Search. Use for general knowledge questions.",
    instruction="Use the google_search tool to find information from the web.",
    tools=[google_search],
    disallow_transfer_to_parent=True,
    disallow_transfer_to_peers=True,
)
sub_agents.append(google_search_agent)

# 6. Local Tools Agent (DB lookup + calculation)
local_tools_agent = LlmAgent(
    name="local_tools_agent",
    model=MODEL_ID,
    description="Handles database lookups and complex calculations using local tools. Use for requests involving item lookups, data retrieval by ID, or numerical calculations.",
    instruction=(
        "You have two tools: simulated_db_lookup for looking up items by ID, "
        "and complex_calculation for performing calculations on data. "
        "Use the appropriate tool based on the user's request."
    ),
    tools=[simulated_db_lookup, complex_calculation],
    disallow_transfer_to_parent=True,
    disallow_transfer_to_peers=True,
)
sub_agents.append(local_tools_agent)

# 7. Parallel DB Lookup Agent
parallel_sub_agents = []
for i in range(3):
    worker = LlmAgent(
        name=f"lookup_worker_{i+1}",
        model=MODEL_ID,
        instruction="You will be given an item ID. Use the simulated_db_lookup tool to fetch the data for this single ID.",
        tools=[simulated_db_lookup],
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
    )
    parallel_sub_agents.append(worker)

parallel_db_lookup = ParallelAgent(
    name="parallel_db_lookup",
    description="Looks up multiple item details from a simulated database in parallel. Use when asked to retrieve multiple items at once.",
    sub_agents=parallel_sub_agents,
)
sub_agents.append(parallel_db_lookup)

# 8. Internal Docs Agent (silently returns empty results — false positive scenario)
internal_docs_agent = LlmAgent(
    name="internal_docs_agent",
    model=MODEL_ID,
    description="Answers questions about internal company policies, HR procedures, onboarding, expense reports, and compliance guidelines by searching the internal documentation knowledge base.",
    instruction=(
        "You are a company knowledge assistant. Use the search_internal_docs tool to find relevant "
        "policies, procedures, and guidelines from the internal documentation. "
        "Always search first, then provide a response based on what you find. "
        "If the tool returns no results, do your best to provide a helpful response."
    ),
    tools=[search_internal_docs],
    disallow_transfer_to_parent=True,
    disallow_transfer_to_peers=True,
)
sub_agents.append(internal_docs_agent)

# --- Build routing instruction dynamically ---
routing_rules = [
    "1. If the input asks about PTO, vacation, time off, or work days, route to 'pto_agent'.",
]
rule_num = 2
if datastore_search_tool:
    routing_rules.append(f"{rule_num}. If the input asks about ADK documentation, how to use ADK tools, or ADK application structure, route to 'adk_documentation_agent'.")
    rule_num += 1
if web_search_tool:
    routing_rules.append(f"{rule_num}. If the input asks about AI Agent Observability, Tracing, or monitoring, route to 'ai_observability_agent'.")
    rule_num += 1
routing_rules.extend([
    f"{rule_num}. If the input asks about BigQuery datasets, tables, records, or data analysis, route to 'bigquery_data_agent'.",
    f"{rule_num+1}. If the input asks to fetch/lookup items by ID or perform calculations, route to 'local_tools_agent'.",
    f"{rule_num+2}. If the input asks to retrieve multiple items in parallel, route to 'parallel_db_lookup'.",
    f"{rule_num+3}. If the input asks about internal company policies, HR procedures, onboarding, expense reports, or compliance guidelines, route to 'internal_docs_agent'.",
    f"{rule_num+4}. For general knowledge questions, route to 'google_search_agent'.",
])

supervisor_instruction = (
    "You are a supervisor agent that coordinates other agents to answer user queries. "
    "Route the user's input to the correct sub-agent based on these rules:\n"
    + "\n".join(routing_rules)
    + "\nNote: The pto_agent does not require any user identification, call it directly."
)

supervisor_agent = Agent(
    name="knowledge_supervisor",
    model=Gemini(
        model=MODEL_ID,
        retry_options=types.HttpRetryOptions(attempts=5),
    ),
    description="A supervisor agent that coordinates other agents to answer user queries.",
    instruction=supervisor_instruction,
    sub_agents=sub_agents,
)

class ReasoningEngineApp(App):
    def query(self, query: str) -> str:
        import asyncio
        import nest_asyncio
        nest_asyncio.apply()
        return asyncio.run(self._async_query(query))


    async def _async_query(self, query: str, session_id: str = None, user_id: str = None) -> str:
        import uuid
        if not session_id:
            session_id = f"{uuid.uuid4()}"
        if not user_id:
            user_id = f"userid_{uuid.uuid4()}"
            
        from google.adk.runners import Runner
        from google.adk.sessions.in_memory_session_service import InMemorySessionService
        
        session_service = InMemorySessionService()
        runner = Runner(app=self, session_service=session_service, auto_create_session=True)

        
        new_message = types.Content(
            role="user",
            parts=[types.Part.from_text(text=query)]
        )
        
        final_response = ""
        partial_responses = []
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=new_message
        ):
            if event.author != "user" and event.content:
                if event.partial:
                     for part in event.content.parts:
                         if part.text:
                             partial_responses.append(part.text)
                else:
                     text = "".join([p.text for p in event.content.parts if p.text])
                     if text:
                         final_response = text
                             
        return final_response or "".join(partial_responses) or "No response from agent."

app = ReasoningEngineApp(
    root_agent=supervisor_agent,
    name=SUPERVISOR_DISPLAY_NAME,
    plugins=[bq_logging_plugin, LoggingPlugin()]
)

adk_app = app
