import logging
import os
import sys

from google.adk.agents import Agent
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent
from google.adk.apps import App
from google.adk.models import Gemini
from google.adk.plugins import LoggingPlugin
from google.adk.tools.agent_tool import AgentTool
from google.genai import types

sys.path.append(os.path.abspath(os.path.dirname(__file__)))
import httpx
import google.auth.transport.requests
import google.oauth2.id_token
import json

from .config import (
    discover_pto_agent_url,
    SUPERVISOR_DISPLAY_NAME,
    SUPERVISOR_MODEL_ID
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

auth_client = CardInterceptClient(server_url=server_url, auth=auth)

logger.info(f"Creating RemoteA2aAgent pointing to {server_url}/.well-known/agent-card.json")
pto_remote_agent = RemoteA2aAgent(
    name="pto_agent",
    description="A remote agent that calculates remaining time off and work days.",
    agent_card=f"{server_url}/a2a/pto_agent/.well-known/agent-card.json",
    httpx_client=auth_client
)

def request_user_input(message: str) -> dict:
    """Request additional input from the user."""
    return {"status": "pending", "message": message}

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

root_agent = Agent(
    name="root_agent", # Keeping original name
    model=Gemini(
        model=SUPERVISOR_MODEL_ID,
        retry_options=types.HttpRetryOptions(attempts=5),
    ),
    description="A supervisor agent that coordinates other agents to answer user queries.",
    instruction="You are a supervisor agent that coordinates other agents to answer user queries."
                " You have access to a tool that calculates PTO details (pto_agent)."
                " Use them appropriately. Note: The pto_agent does not require any user identification, call it directly.",
    tools=[
        AgentTool(agent=pto_remote_agent),
    ],
)

class ReasoningEngineApp(App):
    def query(self, query: str) -> str:
        import asyncio
        import nest_asyncio
        nest_asyncio.apply()
        return asyncio.run(self.async_query(query))


    async def async_query(self, query: str, session_id: str = "uid", user_id: str = "suerid") -> str:
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
    root_agent=root_agent,
    name=SUPERVISOR_DISPLAY_NAME,
    plugins=[bq_logging_plugin, LoggingPlugin()]
)

adk_app = app
