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

# BigQuery to be analyzed
DATASET_ID = os.getenv('DATASET_ID')
DATASET_LOCATION = os.getenv('DATASET_LOCATION', 'us-central1')
TABLE_ID = os.getenv('TABLE_ID')

AGENT_EVENTS_VIEW_ID = os.getenv('AGENT_EVENTS_VIEW_ID', 'agent_events_view')
LLM_EVENTS_VIEW_ID = os.getenv('LLM_EVENTS_VIEW_ID', 'llm_events_view')
TOOL_EVENTS_VIEW_ID = os.getenv('TOOL_EVENTS_VIEW_ID', 'tool_events_view')
INVOCATION_EVENTS_VIEW_ID = os.getenv('INVOCATION_EVENTS_VIEW_ID', 'invocation_events_view')
CONNECTION_ID = os.getenv('CONNECTION_ID', 'bqml_connection')

TOOLS_TO_EXCLUDE = ["transfer_to_agent"]
TOOLS_TO_EXCLUDE_STR = ", ".join(f"'{tool}'" for tool in TOOLS_TO_EXCLUDE) if TOOLS_TO_EXCLUDE else None

AGENT_NAME = os.getenv('AGENT_NAME', 'observability_analyst')
DEBUG = str(os.getenv('DEBUG', 'False')).lower() in ('true', '1', 't')
LOCATION = os.getenv('LOCATION', "us")

#Agent produced BQ Analytics
AGENT_DATASET_ID = os.getenv('AGENT_DATASET_ID', DATASET_ID)
AGENT_TABLE_ID = os.getenv('AGENT_TABLE_ID', TABLE_ID)

MAX_CHARS_PAYLOAD_SQL = os.getenv('MAX_CHARS_PAYLOAD_SQL', '1000') # max chars for the returned SQL payload to be
# truncated (e.g when using LLM)

COMMON_COLUMNS = ["trace_id", "span_id", "session_id", "duration_ms", "agent_name", "root_agent_name",
                  "status", "timestamp", "error_message"]

TOOL_SPECIFIC_COLUMNS = ["tool_name", "tool_args", "tool_result", "parent_span_id"]
LLM_SPECIFIC_COLUMNS = ["model_name", "prompt_token_count", "candidates_token_count", "total_token_count",
                        "thoughts_token_count", "time_to_first_token_ms", "full_request",
                        "full_response", "llm_config", "parent_span_id"]

AGENT_SPECIFIC_COLUMNS = ["instruction", "parent_span_id"]
INVOCATION_SPECIFIC_COLUMNS = ["content_text", "content_text_summary", "invocation_id"]


MODEL_ID=os.getenv('AGENT_MODEL_ID', 'gemini-2.5-pro')
assert MODEL_ID, "AGENT_MODEL_ID is not set"
assert TABLE_ID, "TABLE_ID is not set for the BigQuery Analytics Plugin"
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
CACHE_TTL = int(os.getenv('CACHE_TTL', 3600))

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
