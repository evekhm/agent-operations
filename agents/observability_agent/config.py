import logging
import os

import google.auth
from dotenv import load_dotenv

# Load .env from project root
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../.env"), override=True)

# GCP
AGENT_LOCATION = os.getenv('AGENT_LOCATION', 'us-central1')
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
if AGENT_LOCATION:
    os.environ['GOOGLE_CLOUD_LOCATION'] = AGENT_LOCATION
os.environ['GOOGLE_GENAI_USE_VERTEXAI'] = 'True'


# BigQuery to be analyzed
PROJECT_ID = os.getenv('PROJECT_ID')
DATASET_ID = os.getenv('DATASET_ID')
DATASET_LOCATION = os.getenv('DATASET_LOCATION')
TABLE_ID = os.getenv('TABLE_ID')
assert PROJECT_ID, "PROJECT_ID is not set for the BigQuery Analytics Plugin"
assert DATASET_LOCATION, "DATASET_LOCATION is not set for the BigQuery Analytics Plugin"
assert TABLE_ID, "TABLE_ID is not set for the BigQuery Analytics Plugin"
assert DATASET_ID, "DATASET_ID is not set for the BigQuery Analytics Plugin"


# Agent BigQuery produced
AGENT_DATASET_ID = os.getenv('AGENT_DATASET_ID', DATASET_ID)
AGENT_DATASET_LOCATION = os.getenv('AGENT_DATASET_LOCATION', DATASET_LOCATION)
AGENT_TABLE_ID = os.getenv('AGENT_TABLE_ID', TABLE_ID)

# Agent
AGENT_VERSION = os.getenv('AGENT_VERSION', '0.0.3')


AGENT_NAME = os.getenv('AGENT_NAME', 'observability_analyst')
MODEL_ID=os.getenv('AGENT_MODEL_ID', 'gemini-2.5-pro')
assert MODEL_ID, "AGENT_MODEL_ID is not set"


# Agent Configurations
RCA_MAX_CONCURRENT_REQUESTS = os.getenv('RCA_MAX_CONCURRENT_REQUESTS', '5')
MAX_CHARS_PAYLOAD_SQL = os.getenv('MAX_CHARS_PAYLOAD_SQL', '1000') # max chars for the returned SQL payload to be
# truncated (e.g when using LLM)


# Internal Constants
AGENT_EVENTS_VIEW_ID = os.getenv('AGENT_EVENTS_VIEW_ID', 'agent_events_view')
LLM_EVENTS_VIEW_ID = os.getenv('LLM_EVENTS_VIEW_ID', 'llm_events_view')
TOOL_EVENTS_VIEW_ID = os.getenv('TOOL_EVENTS_VIEW_ID', 'tool_events_view')
INVOCATION_EVENTS_VIEW_ID = os.getenv('INVOCATION_EVENTS_VIEW_ID', 'invocation_events_view')
CONNECTION_ID = os.getenv('CONNECTION_ID', 'bqml_connection')
INVOCATION_TIMEOUT_MINUTES = int(os.getenv('INVOCATION_TIMEOUT_MINUTES', '5'))

TOOLS_TO_EXCLUDE = ["transfer_to_agent"]
TOOLS_TO_EXCLUDE_STR = ", ".join(f"'{tool}'" for tool in TOOLS_TO_EXCLUDE) if TOOLS_TO_EXCLUDE else None
DEBUG = str(os.getenv('DEBUG', 'False')).lower() in ('true', '1', 't')

# BQ Views
COMMON_COLUMNS = ["trace_id", "span_id", "session_id", "duration_ms", "agent_name", "root_agent_name",
                  "status", "timestamp", "error_message"]
TOOL_SPECIFIC_COLUMNS = ["tool_name", "tool_args", "tool_result", "parent_span_id"]
LLM_SPECIFIC_COLUMNS = ["model_name", "prompt_token_count", "candidates_token_count", "total_token_count",
                        "thoughts_token_count", "time_to_first_token_ms", "full_request",
                        "full_response", "llm_config", "parent_span_id", "response_text"]

AGENT_SPECIFIC_COLUMNS = ["instruction", "parent_span_id"]
INVOCATION_SPECIFIC_COLUMNS = ["content_text", "content_text_summary", "invocation_id"]

OBSERVABILITY_APP_NAME = os.getenv('OBSERVABILITY_APP_NAME', "observability_analyst_app")
MAX_RAW_RECORDS_LIMIT = int(os.getenv("MAX_RAW_RECORDS_LIMIT", 100000))

# KPI Defaults (Fallback if no config file)=========================================
# =========================================
# VISUAL CONFIGURATION
# =========================================
CHART_TITLE_SIZE = int(os.getenv('CHART_TITLE_SIZE', 10))
CHART_LABEL_SIZE = int(os.getenv('CHART_LABEL_SIZE', 8))
SHOW_CHART_TITLES = str(os.getenv('SHOW_CHART_TITLES', 'False')).lower() in ('true', '1', 't')

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
DEFAULT_TIME_RANGE = "24h"
CACHE_TTL = int(os.getenv('CACHE_TTL', 3600))

# =========================================
# STATIC KPIs (SLOs)
# =========================================
DEFAULT_KPIS = {
    "end_to_end": {
        "latency_target": 10.0,
        "percentile_target": 95.5,
        "error_target": 5.0
    },
    "agent": {
        "latency_target": 8.0,
        "percentile_target": 95.5,
        "error_target": 5.0
    },
    "llm": {
        "latency_target": 5.0,
        "percentile_target": 95.5,
        "error_target": 5.0
    },
    "tool": {
        "latency_target": 3.0,
        "percentile_target": 95.5,
        "error_target": 5.0
    }
}

print(
    "Configuration loaded:\n"
    f"  PROJECT_ID: {PROJECT_ID}\n"
    f"  DATASET_ID: {DATASET_ID}\n"
    f"  DATASET_LOCATION: {DATASET_LOCATION}\n"
    f"  TABLE_ID: {TABLE_ID}\n"
    f"  AGENT_EVENTS_VIEW_ID: {AGENT_EVENTS_VIEW_ID}\n"
    f"  LLM_EVENTS_VIEW_ID: {LLM_EVENTS_VIEW_ID}\n"
    f"  TOOL_EVENTS_VIEW_ID: {TOOL_EVENTS_VIEW_ID}\n"
    f"  INVOCATION_EVENTS_VIEW_ID: {INVOCATION_EVENTS_VIEW_ID}\n"
    f"  CONNECTION_ID: {CONNECTION_ID}\n"
    f"  AGENT_NAME: {AGENT_NAME}\n"
    f"  AGENT_VERSION: {AGENT_VERSION}\n"
    f"  DEBUG: {DEBUG}\n"
    f"  AGENT_PROJECT_ID: {AGENT_PROJECT_ID}\n"
    f"  AGENT_DATASET_ID: {AGENT_DATASET_ID}\n"
    f"  AGENT_TABLE_ID: {AGENT_TABLE_ID}\n"
    f"  AGENT_LOCATION: {AGENT_LOCATION}\n"
    f"  RCA_MAX_CONCURRENT_REQUESTS: {RCA_MAX_CONCURRENT_REQUESTS}\n"
    f"  MAX_CHARS_PAYLOAD_SQL: {MAX_CHARS_PAYLOAD_SQL}\n"
    f"  MODEL_ID: {MODEL_ID}\n"
    f"  OBSERVABILITY_APP_NAME: {OBSERVABILITY_APP_NAME}\n"
    f"  MAX_RAW_RECORDS_LIMIT: {MAX_RAW_RECORDS_LIMIT}\n"
    f"  CHART_TITLE_SIZE: {CHART_TITLE_SIZE}\n"
    f"  CHART_LABEL_SIZE: {CHART_LABEL_SIZE}\n"
    f"  SHOW_CHART_TITLES: {SHOW_CHART_TITLES}\n"
    f"  CACHE_TTL: {CACHE_TTL}"
)
