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
    description="A remote agent that calculates PTO balances, sick leave balances, working days for specific date ranges, and remaining work days in a month/quarter/year.",
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
    """Searches the internal company documentation knowledge base for policies, procedures, and guidelines.

    Args:
        query: The search query about company policies, HR procedures, or guidelines.

    Returns:
        Matching company policy documents and guidelines.
    """
    delay = random.uniform(0.1, 0.3)
    logger.info(f"Searching internal docs for: {query}")
    time.sleep(delay)
    query_lower = query.lower()

    # Company policy knowledge base
    policies = {
        "pto": (
            "**PTO Policy (Updated 2026)**\n"
            "- All full-time employees receive 20 PTO days per year, accrued monthly (1.67 days/month).\n"
            "- PTO requests must be submitted at least 2 weeks in advance for periods > 3 days.\n"
            "- Unused PTO carries over up to 5 days into the next year.\n"
            "- PTO blackout periods: Last 2 weeks of fiscal quarter-end for Finance team."
        ),
        "sick": (
            "**Sick Leave Policy**\n"
            "- All employees receive 10 sick days per year, accrued monthly (0.83 days/month).\n"
            "- Sick leave can be used for personal illness, medical appointments, or caring for a sick family member.\n"
            "- A doctor's note is required for absences exceeding 3 consecutive days.\n"
            "- Unused sick leave carries over fully to the next year, up to a maximum of 30 days."
        ),
        "onboarding": (
            "**Onboarding Process**\n"
            "- Week 1: IT setup, security training, HR orientation, team introductions.\n"
            "- Week 2: Product overview, codebase walkthrough, buddy system assignment.\n"
            "- Week 3-4: First project assignment, 30-day check-in with manager.\n"
            "- Required trainings: Security Awareness, Code of Conduct, Data Privacy (complete within 30 days).\n"
            "- All new hires receive a welcome kit and access to the employee handbook on the intranet."
        ),
        "expense": (
            "**Expense Report Policy**\n"
            "- Expense reports must be submitted within 30 days of the expense.\n"
            "- Receipts required for all expenses over $25.\n"
            "- Travel: Economy class for flights under 6 hours. Hotel cap: $250/night (domestic), $350/night (international).\n"
            "- Meals: $75/day domestic, $100/day international.\n"
            "- Manager approval required for expenses over $500. VP approval for over $5,000.\n"
            "- Submit via the Concur expense management system."
        ),
        "remote": (
            "**Remote Work Policy**\n"
            "- Hybrid model: minimum 3 days in-office per week (Tue, Wed, Thu recommended).\n"
            "- Fully remote positions available with VP approval.\n"
            "- Remote workers must maintain a dedicated workspace and reliable internet.\n"
            "- Equipment stipend: $1,500 one-time for home office setup.\n"
            "- Monthly internet reimbursement: up to $75."
        ),
        "performance": (
            "**Performance Review Process**\n"
            "- Annual performance reviews conducted in Q4 (October-November).\n"
            "- Mid-year check-ins in Q2 (April-May).\n"
            "- Rating scale: Exceeds Expectations, Meets Expectations, Needs Improvement.\n"
            "- Self-assessment due 2 weeks before review meeting.\n"
            "- 360-degree feedback collected from peers, direct reports, and cross-functional partners.\n"
            "- Compensation adjustments effective January 1 following review cycle."
        ),
        "hiring": (
            "**Hiring Process & Policy**\n"
            "- All open positions must be posted on the internal job board for 5 business days before external posting.\n"
            "- Standard interview process: Phone screen -> Technical/Skills assessment -> On-site/Virtual panel -> Final round with hiring manager.\n"
            "- Hiring committee approval required for all offers.\n"
            "- Background checks conducted after verbal offer acceptance.\n"
            "- Referral bonus: $5,000 for engineering roles, $3,000 for non-engineering roles, paid after 90 days.\n"
            "- For specific candidate status or real-time hiring pipeline updates, please check the ATS (Greenhouse) or contact the recruiting team."
        ),
        "compliance": (
            "**Compliance & Ethics Guidelines**\n"
            "- Annual compliance training required for all employees (due by March 31).\n"
            "- Conflicts of interest must be disclosed to Legal within 30 days.\n"
            "- Gift policy: Employees may not accept gifts valued over $100 from vendors or clients.\n"
            "- Whistleblower hotline: Available 24/7 for anonymous reporting.\n"
            "- Data handling: All customer data classified as Confidential. PII requires encryption at rest and in transit."
        ),
        "benefits": (
            "**Employee Benefits Summary**\n"
            "- Health insurance: Medical, dental, vision (company covers 90% of premiums).\n"
            "- 401(k): Company matches 50% up to 6% of salary.\n"
            "- Life insurance: 2x annual salary at no cost.\n"
            "- Parental leave: 16 weeks paid for primary caregiver, 8 weeks for secondary.\n"
            "- Education reimbursement: Up to $5,250/year for job-related courses.\n"
            "- Wellness stipend: $100/month for gym, mental health apps, etc."
        ),
    }

    results = []
    for key, content in policies.items():
        if key in query_lower or any(word in query_lower for word in key.split()):
            results.append(content)

    # Broader keyword matching
    keyword_map = {
        "vacation": "pto", "time off": "pto", "leave": "pto", "day off": "pto",
        "medical": "sick", "illness": "sick", "doctor": "sick",
        "new hire": "onboarding", "orientation": "onboarding", "first day": "onboarding",
        "travel": "expense", "reimbursement": "expense", "receipt": "expense", "concur": "expense",
        "work from home": "remote", "wfh": "remote", "hybrid": "remote", "telecommute": "remote",
        "review": "performance", "promotion": "performance", "rating": "performance", "raise": "performance",
        "interview": "hiring", "recruit": "hiring", "candidate": "hiring", "job posting": "hiring", "offer": "hiring",
        "ethics": "compliance", "training": "compliance", "data privacy": "compliance",
        "health": "benefits", "insurance": "benefits", "401k": "benefits", "parental": "benefits", "wellness": "benefits",
    }
    for keyword, policy_key in keyword_map.items():
        if keyword in query_lower and policies[policy_key] not in results:
            results.append(policies[policy_key])

    if results:
        return "\n\n---\n\n".join(results)

    # Default: return a general overview
    return (
        "**Company Policy Overview**\n"
        "Available policy topics: PTO & Leave, Sick Leave, Onboarding, Expense Reports, "
        "Remote Work, Performance Reviews, Hiring Process, Compliance & Ethics, Employee Benefits.\n"
        "Please refine your query to one of these topics for detailed information.\n\n"
        "For real-time information about specific candidates, hiring pipeline status, or "
        "individual employee records, please contact HR or check the appropriate system (Greenhouse for recruiting, Workday for HR)."
    )

# --- Developer Knowledge MCP Tools ---

DEVELOPER_KNOWLEDGE_API_KEY = os.getenv('DEVELOPER_KNOWLEDGE_API_KEY', '')
MCP_URL = "https://developerknowledge.googleapis.com/mcp"

def search_developer_docs(query: str) -> str:
    """Searches Google Developer documentation (Cloud, Firebase, Android, Maps, etc.) for technical guides, code snippets, and best practices.

    Args:
        query: The search query about Google developer technologies.

    Returns:
        Relevant documentation snippets and references.
    """
    import requests as req
    if not DEVELOPER_KNOWLEDGE_API_KEY:
        return "Developer Knowledge API key not configured. Please set DEVELOPER_KNOWLEDGE_API_KEY environment variable."

    headers = {
        "X-Goog-Api-Key": DEVELOPER_KNOWLEDGE_API_KEY,
        "Content-Type": "application/json"
    }
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "search_documents",
            "arguments": {"query": query}
        }
    }
    try:
        response = req.post(MCP_URL, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        if "result" in data and "content" in data["result"]:
            content = data["result"]["content"]
            if isinstance(content, list) and len(content) > 0:
                first_block = content[0]
                if isinstance(first_block, dict) and "text" in first_block:
                    text = first_block["text"]
                    if text.startswith("```json"):
                        text = text.strip("```json").strip("```")
                    try:
                        inner_data = json.loads(text)
                        if isinstance(inner_data, dict) and "results" in inner_data:
                            results = inner_data["results"]
                            formatted = []
                            for r in results:
                                formatted.append(f"Source: {r.get('parent')}\nContent: {r.get('content')}\n---")
                            return "\n".join(formatted)
                    except (json.JSONDecodeError, ValueError):
                        return text
        return f"No results found for: {query}"
    except Exception as e:
        logger.warning(f"Developer Knowledge MCP error: {e}")
        return f"Error searching developer docs: {e}"

# --- Vertex AI Search Tools ---

datastore_search_tool = None

if DATASTORE_ID and PROJECT_ID:
    datastore_path = f"projects/{PROJECT_ID}/locations/{DATASTORE_LOCATION}/collections/default_collection/dataStores/{DATASTORE_ID}"
    datastore_search_tool = VertexAiSearchTool(data_store_id=datastore_path)
    logger.info(f"Configured Vertex AI Search datastore: {datastore_path}")

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

# 3. BigQuery Data Agent
bigquery_data_agent = LlmAgent(
    name="bigquery_data_agent",
    model=MODEL_ID,
    description="Analyzes data in BigQuery datasets. Use this for questions about querying data, tables, records, data analysis, or reporting from BigQuery.",
    instruction=(
        f"You are a data analyst. Use the BigQuery tools to answer questions about data.\n"
        f"IMPORTANT: The default project ID is '{PROJECT_ID}'. Always use this project when querying.\n"
        f"Start by using `list_dataset_ids` for project '{PROJECT_ID}' to discover available datasets, "
        f"then use `list_tables` to find tables within datasets.\n"
        f"CRITICAL: The timestamp column is 'timestamp', not 'event_time'.\n"
        f"You can query JSON columns using JSON_EXTRACT_SCALAR().\n"
        f"Avoid casting JSON directly to STRING or comparing JSON directly to strings.\n"
        f"When asked about data analysis, reports, or metrics, always attempt to query the available "
        f"data and provide a substantive answer based on what you find."
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

# 8. Internal Docs Agent
internal_docs_agent = LlmAgent(
    name="internal_docs_agent",
    model=MODEL_ID,
    description=(
        "Answers questions about internal company policies, HR procedures, onboarding, expense reports, "
        "remote work policy, performance reviews, hiring process policies, compliance guidelines, "
        "employee benefits, sick leave policy, and PTO policy documentation."
    ),
    instruction=(
        "You are a company knowledge assistant specializing in company policies and procedures. "
        "Use the search_internal_docs tool to find relevant policies, procedures, and guidelines.\n\n"
        "You CAN answer questions about:\n"
        "- Company policies (PTO, sick leave, remote work, expenses, benefits)\n"
        "- HR procedures (onboarding, performance reviews, hiring process)\n"
        "- Compliance and ethics guidelines\n"
        "- General information about how processes work at the company\n\n"
        "For questions about specific candidate statuses, real-time hiring pipeline data, "
        "or individual employee records, explain that this information is available in the "
        "company's ATS (Greenhouse) or HRIS (Workday), and provide the relevant policy context instead.\n\n"
        "Always search first using the tool, then provide a comprehensive response based on what you find."
    ),
    tools=[search_internal_docs],
    disallow_transfer_to_parent=True,
    disallow_transfer_to_peers=True,
)
sub_agents.append(internal_docs_agent)

# 9. Google Developer Knowledge Agent (MCP-powered)
if DEVELOPER_KNOWLEDGE_API_KEY:
    developer_docs_agent = LlmAgent(
        name="developer_docs_agent",
        model=MODEL_ID,
        description=(
            "Searches Google Developer documentation (GCP, Firebase, Android, Maps, etc.) "
            "for technical guides, code snippets, API references, and best practices."
        ),
        instruction=(
            "You are a Google Developer documentation expert. Use the search_developer_docs tool "
            "to find relevant technical documentation from Google's developer knowledge base.\n"
            "This covers: Google Cloud Platform, Firebase, Android, Google Maps, and other Google developer products.\n"
            "Always search first, then provide a comprehensive answer based on the documentation found."
        ),
        tools=[search_developer_docs],
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
    )
    sub_agents.append(developer_docs_agent)
    logger.info("Added developer_docs_agent with MCP-powered Google Developer Knowledge")
else:
    logger.info("DEVELOPER_KNOWLEDGE_API_KEY not set, skipping developer_docs_agent")

# --- Build routing instruction dynamically ---
routing_rules = [
    "1. **PTO, vacation, time off, sick leave, working days, leave balance** -> route to 'pto_agent'. This agent can calculate PTO balances, sick leave balances, working days for specific date ranges, and remaining working days in a month/quarter/year.",
]
rule_num = 2
if datastore_search_tool:
    routing_rules.append(f"{rule_num}. **ADK documentation, ADK tools, ADK application structure, Agent Development Kit** -> route to 'adk_documentation_agent'.")
    rule_num += 1
routing_rules.extend([
    f"{rule_num}. **BigQuery datasets, tables, records, data analysis, SQL queries, data reports** -> route to 'bigquery_data_agent'. This agent has access to project '{PROJECT_ID}'.",
    f"{rule_num+1}. **Item lookups by ID, database lookups, numerical calculations** -> route to 'local_tools_agent'.",
    f"{rule_num+2}. **Multiple items to retrieve in parallel** -> route to 'parallel_db_lookup'.",
    f"{rule_num+3}. **Company policies, HR procedures, onboarding, expense reports, compliance, benefits, remote work policy, performance reviews, hiring PROCESS/POLICY questions** -> route to 'internal_docs_agent'. Note: this agent handles policy questions, not real-time candidate tracking.",
])
if DEVELOPER_KNOWLEDGE_API_KEY:
    routing_rules.append(f"{rule_num+4}. **Google Cloud documentation, GCP services, Firebase, Android development, Google APIs, Google developer best practices** -> route to 'developer_docs_agent'.")
    routing_rules.append(f"{rule_num+5}. **General knowledge, current events, other technology questions, factual lookups** -> route to 'google_search_agent'.")
else:
    routing_rules.append(f"{rule_num+4}. **General knowledge, current events, technology questions, factual lookups** -> route to 'google_search_agent'.")

supervisor_instruction = (
    "You are a supervisor agent that coordinates specialized sub-agents to answer user queries.\n\n"
    "ROUTING RULES (follow strictly):\n"
    + "\n".join(routing_rules)
    + "\n\nIMPORTANT ROUTING NOTES:\n"
    "- The pto_agent does not require any user identification, call it directly.\n"
    "- For questions about PTO balances, sick leave balances, or working days in specific periods, ALWAYS use pto_agent.\n"
    "- For company policy questions (how hiring works, what the PTO policy is, expense rules, etc.), use internal_docs_agent.\n"
    "- If a question doesn't clearly match any specific agent, use google_search_agent as the fallback.\n"
    "- Always route to exactly one agent. Do not ask the user to clarify which agent to use."
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

# Export for `adk web` (needs a root_agent at module level)
root_agent = supervisor_agent
