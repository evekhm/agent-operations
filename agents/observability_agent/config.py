import logging
import os

import google.auth
from dotenv import load_dotenv

# Load .env from project root
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../.env"), override=True)

# Get ADC creds and project ID.
PROJECT_ID = os.getenv('PROJECT_ID')
if not PROJECT_ID:
    try:
        # Only call default() if PROJECT_ID is missing from env
        _, project = google.auth.default()
        PROJECT_ID = project
    except Exception:
        PROJECT_ID = None

# BigQuery
DATASET_ID = os.getenv('DATASET_ID')
AGENT_EVENTS_TABLE_ID = os.getenv('TABLE_ID')
AGENT_EVENTS_VIEW_ID = os.getenv('AGENT_EVENTS_VIEW_ID', 'agent_events_view')
LLM_EVENTS_VIEW_ID = os.getenv('LLM_EVENTS_VIEW_ID', 'llm_events_view')
TOOL_EVENTS_VIEW_ID = os.getenv('TOOL_EVENTS_VIEW_ID', 'tool_events_view')
INVOCATION_EVENTS_VIEW_ID = os.getenv('INVOCATION_EVENTS_VIEW_ID', 'invocation_events_view')
DATASET_LOCATION = os.getenv('DATASET_LOCATION', 'us-central1')
CONNECTION_ID = os.getenv('CONNECTION_ID', 'bqml_connection')


AGENT_NAME = os.getenv('AGENT_NAME', 'observability_analyst')
DEBUG = str(os.getenv('DEBUG', 'False')).lower() in ('true', '1', 't')
LOCATION = os.getenv('LOCATION', "us")

MODEL_ID=os.getenv('AGENT_MODEL_ID', 'gemini-2.5-pro')
assert MODEL_ID, "AGENT_MODEL_ID is not set"
assert AGENT_EVENTS_TABLE_ID, "TABLE_ID is not set for the BigQuery Analytics Plugin"
assert DATASET_ID, "DATASET_ID is not set for the BigQuery Analytics Plugin"

# Set env vars for Google generic libs
if PROJECT_ID:
    os.environ['GOOGLE_CLOUD_PROJECT'] = PROJECT_ID
if LOCATION:
    os.environ['GOOGLE_CLOUD_LOCATION'] = LOCATION
os.environ['GOOGLE_GENAI_USE_VERTEXAI'] = 'True'


AGENT_VERSION = "0.0.1"

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

# =========================================
# STATIC KPIs (SLOs)
# =========================================
DEFAULT_KPIS = {
    "llm_mean_latency_target": 2.0,
    "llm_p95_latency_target": 3.0,
    "e2e_mean_latency_target": 5.0,
    "e2e_p95_latency_target": 10.0,
    "agent_mean_latency_target": 3.0,
    "agent_p95_latency_target": 5.0,
    "tool_mean_latency_target": 2.0,
    "tool_p95_latency_target": 3.0,
    "per_agent": {}
}
