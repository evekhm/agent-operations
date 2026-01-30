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

LOCATION = os.getenv('LOCATION', "us")

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

def _load_config_data() -> dict:
    """
    Internal helper to read and cache configuration.
    Returns the parsed JSON dict (or empty dict on error).
    """
    try:
        # Check environment variable first
        config_path = os.getenv("LATENCY_ANALYSIS_CONFIG_FILE")
        
        # If not set, try default relative path
        if not config_path:
             # Default path relative to this file
             # agents/parallel_latency_analyzer/config.py
             # 3 levels up -> latency_analysis root
             base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
             config_path = os.path.join(base_dir, "autonomous_analysis_90d.json")
             logger.info(f"Config env var not set, using default path: {config_path}")
        else:
             logger.info(f"Using config from env var LATENCY_ANALYSIS_CONFIG_FILE: {config_path}")

        # Resolve absolute path if it is relative
        if not os.path.isabs(config_path):
            # Try relative to CWD first
            if os.path.exists(config_path):
                config_path = os.path.abspath(config_path)
            else:
                # Try relative to project root
                base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                candidate = os.path.join(base_dir, config_path)
                if os.path.exists(candidate):
                    config_path = candidate
             
        if not os.path.exists(config_path):
            logger.warning(f"Config file not found at {config_path}")
            return {}
            
        with open(config_path, 'r') as f:
            return json.load(f)
            
    except Exception as e:
        logger.error(f"Error reading config: {str(e)}")
        return {}

def load_analyst_config() -> dict:
    """
    Loads configuration for the Observability Analyst.
    Priority:
    1. Env var: LATENCY_ANALYSIS_CONFIG_FILE
    2. Local file: agents/analytics_agent/config.json
    3. Default: hardcoded fallback
    """
    # 1. Try Env Var
    env_path = os.getenv("LATENCY_ANALYSIS_CONFIG_FILE")
    if env_path and os.path.exists(env_path):
        try:
            with open(env_path, 'r') as f:
                logger.info(f"Loaded analyst config from {env_path}")
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load config from {env_path}: {e}")

    # 2. Try Local config.json (relative to this file)
    local_path = os.path.join(os.path.dirname(__file__), "config.json")
    if os.path.exists(local_path):
        try:
            with open(local_path, 'r') as f:
                logger.info(f"Loaded analyst config from {local_path}")
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load config from {local_path}: {e}")

    # 3. Default Fallback
    logger.warning("No config found, using defaults.")
    return {
        "kpis": {
            "agent": {
                "mean_latency_target_ms": 1000,
                "p95_latency_target_ms": 3000,
            },
            "llm": {
                "mean_latency_target_ms": 500,
                "p95_latency_target_ms": 1500,
            },
            "tool": {
                "mean_latency_target_ms": 200,
                "p95_latency_target_ms": 1000,
            }
        },
        "time_period": "7d"
    }

# Define DEFAULT_TIME_RANGE
# _config = _load_config_data()
DEFAULT_TIME_RANGE = "all" #TODO Convert to session specific period shared so it can be used for caching
