import os
from dotenv import load_dotenv
import google.auth
import json
import logging

# Load .env from project root
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../.env"))

# Get ADC creds and project ID.
PROJECT_ID = os.getenv('PROJECT_ID')
if not PROJECT_ID:
    try:
        # Only call default() if PROJECT_ID is missing from env
        _, project = google.auth.default()
        PROJECT_ID = project
    except Exception:
        PROJECT_ID = None

DATASET_ID = os.getenv('DATASET_ID')
TABLE_ID = os.getenv('AGENT_TABLE_ID')

AGENT_EVENTS_VIEW_ID = os.getenv('AGENT_EVENTS_VIEW_ID', 'agent_events_view')
LLM_EVENTS_VIEW_ID = os.getenv('LLM_EVENTS_VIEW_ID', 'llm_events_view')
TOOL_EVENTS_VIEW_ID = os.getenv('TOOL_EVENTS_VIEW_ID', 'tool_events_view')
INVOCATION_EVENTS_VIEW_ID = os.getenv('INVOCATION_EVENTS_VIEW_ID', 'invocation_events_view')

AGENT_EVENTS_TABLE_ID = os.getenv('AGENT_EVENTS_TABLE_ID', 'agent_events_v2')
CONNECTION_ID = os.getenv('CONNECTION_ID', 'bqml_connection')
LOCATION = os.getenv('LOCATION', "us")

MODEL_ID=os.getenv('AGENT_MODEL_ID', 'gemini-2.5-pro')
assert MODEL_ID, "AGENT_MODEL_ID is not set"

# Set env vars for Google generic libs
if PROJECT_ID:
    os.environ['GOOGLE_CLOUD_PROJECT'] = PROJECT_ID
if LOCATION:
    os.environ['GOOGLE_CLOUD_LOCATION'] = LOCATION
os.environ['GOOGLE_GENAI_USE_VERTEXAI'] = 'True'


AGENT_VERSION = "0.0.1"

def get_table_list() -> list[str]:
    """
    Parse TABLE_ID environment variable as comma-separated list.
    
    Returns:
        List of table names with whitespace stripped
    """
    if not TABLE_ID:
        return []
    tables = [table.strip() for table in TABLE_ID.split(',')]
    return [t for t in tables if t]  # Filter out empty strings

# =========================================
# LATENCY DIMENSIONS
# =========================================
CURRENT_DIMENSION_LIST = [
    "System Health & KPIs",           # H2, H3: Overall KPIs, error rates by type
    "Tool Reliability",               # H11: tool success rates, latency per tool
    "Agent Performance",              # H9, H2: agent-model matrix, orchestration overhead
    "LLM Efficiency",                 # H1, H7, H8, H10: tokens, thinking, config
    "Conversation Analytics",         # H12:session turns, context growth
    "Orchestration & Traces",         # H6, H14: E2E latency, agent call graphs
    "Error & Anomaly Detection",      # H13: error classification, retry patterns
    "Cost & Efficiency Analysis",     # H10: Config impact (token efficiency, not $)
    "Token Usage & Correlation",      # H1: Token correlation + H7: Thinking overhead
    "Slow Query Deep Dive",           # H5: Outliers + H8: Anomalous inefficiency
]



logger = logging.getLogger(__name__)

# Define DEFAULT_TIME_RANGE
# _config = _load_config_data()
DEFAULT_TIME_RANGE = "all" #TODO Convert to session specific period shared so it can be used for caching
