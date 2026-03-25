import logging
import os

import google.auth
from dotenv import load_dotenv

# Load .env from project root
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../.env"), override=True)

# GCP
CA_LOCATION = os.getenv('CA_LOCATION', 'global')
AGENT_PROJECT_ID = os.getenv('AGENT_PROJECT_ID')
if not AGENT_PROJECT_ID:
    try:
        # Only call default() if PROJECT_ID is missing from env
        _, project = google.auth.default()
        AGENT_PROJECT_ID = project
    except Exception:
        AGENT_PROJECT_ID = None

if AGENT_PROJECT_ID:
    os.environ['GOOGLE_CLOUD_PROJECT'] = AGENT_PROJECT_ID
os.environ['GOOGLE_GENAI_USE_VERTEXAI'] = 'True'


# BigQuery to be analyzed
PROJECT_ID = os.getenv('PROJECT_ID')
CA_AGENT_ID = os.getenv('CA_AGENT_ID')
CA_CONVERSATION_ID = os.getenv('CA_CONVERSATION_ID')
CA_LOCATION = os.getenv('CA_LOCATION', 'global')
DATASET_ID = os.getenv('DATASET_ID', "agent_ops_demo")
DATASET_LOCATION = os.getenv('DATASET_LOCATION')
TABLE_ID = os.getenv('TABLE_ID', "agent_events")
LOCATION = "us-central1"  # @param {type:"string"}

CONNECTION_ID = f"{LOCATION}.bqml_connection"  # @param {type:"string"} Cloud Resource Connection for Gemini SQL functions

AGENT_EVENTS_VIEW = os.getenv('AGENT_EVENTS_VIEW_ID', 'agent_events_view')
INVOCATION_EVENTS_VIEW = os.getenv('INVOCATION_EVENTS_VIEW_ID', 'invocation_events_view')
LLM_EVENTS_VIEW = os.getenv('LLM_EVENTS_VIEW_ID', 'llm_events_view')
TOOL_EVENTS_VIEW = os.getenv('TOOL_EVENTS_VIEW_ID', 'tool_events_view')

# Ensure environment variables are set for ADK/Vertex AI
os.environ["GOOGLE_CLOUD_PROJECT"] = PROJECT_ID
os.environ["GOOGLE_CLOUD_LOCATION"] = (
    "us-central1"  # Do not use US or EU since they are not compatible with Vertex AI endpoint
)
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = (
    "True"  # Make sure you have Vertex AI API enabled
)