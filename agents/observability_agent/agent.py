import logging
import os

from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.plugins import LoggingPlugin
from google.adk.plugins.bigquery_agent_analytics_plugin import BigQueryLoggerConfig, BigQueryAgentAnalyticsPlugin

from .agent_tools.analytics.concurrency import (
    analyze_trace_concurrency,
    detect_sequential_bottlenecks
)
from .agent_tools.analytics.latency import (
    get_active_metadata,
    analyze_latency_grouped,
    get_slowest_queries,
    get_fastest_queries,
    get_failed_queries,
    get_baseline_performance_metrics,
    get_latest_queries,
    analyze_root_cause,
    analyze_latency_trend
)
from .config import MODEL_ID, AGENT_NAME, PROJECT_ID, DATASET_ID, AGENT_EVENTS_TABLE_ID
from .prompts import OBSERVABILITY_ANALYST_PROMPT_TEMPLATE

log_level = os.getenv("LOG_LEVEL", "ERROR").upper()
logging.basicConfig(level=getattr(logging, log_level, logging.ERROR))
logger = logging.getLogger(__name__)

# Initialize the exact tools the Observability Playbook Subagent needs
analyst_tools = [
    get_active_metadata,
    analyze_latency_grouped,
    get_slowest_queries,
    get_failed_queries,
    get_fastest_queries,
    get_baseline_performance_metrics,
    get_latest_queries,
    analyze_root_cause,
    analyze_trace_concurrency,
    analyze_latency_trend,
    detect_sequential_bottlenecks
]

# Create the deep-dive Playbook Subagent
playbook_agent = Agent(
    name="playbook_agent",
    model=MODEL_ID,
    instruction=OBSERVABILITY_ANALYST_PROMPT_TEMPLATE, # Will be hydrated dynamically
    description="Executes deep-dive observability playbooks (health, incident, overview, trend, latest) on the agent events and telemetry data inside BigQuery.",
    tools=analyst_tools
)

def set_playbook_config(time_period: str, baseline_period: str, bucket_size: str):
    """Hydrates the OBSERVABILITY_ANALYST_PROMPT_TEMPLATE with dynamic values and updates the playbook_agent."""
    hydrated_prompt = OBSERVABILITY_ANALYST_PROMPT_TEMPLATE.format(
        time_period=time_period,
        baseline_period=baseline_period,
        bucket_size=bucket_size
    )
    playbook_agent.instruction = hydrated_prompt

# Create the Orchestrating Root Agent
root_agent = Agent(
    name=AGENT_NAME,
    model=MODEL_ID,
    instruction="""
    You are the Observability Root Agent. 
    Your job is to understand the user's operational goal and delegate the analysis to your internal playbook subagent.
    
    If the user asks for a specific playbook (e.g., 'overview', 'health', 'incident', 'trend', or 'latest'), 
    you MUST delegate directly to the `observability_analyst` subagent. Pass the user's intent to it so it knows which playbook to execute.
    
    Do NOT attempt to analyze data or write reports yourself. You MUST ALWAYS delegate to your subordinate, the `playbook_agent`.
    """,
    description="Entry point for the Observability Agent application. Understands user intent and delegates analysis to specialized subagents.",
    sub_agents=[playbook_agent],
)

# Configure the BigQuery plugin for `adk run` and `adk web`
bq_config = BigQueryLoggerConfig(
    enabled=True,
    max_content_length=500 * 1024, # 500 KB limit for inline text
    batch_size=1, # Default is 1 for low latency, increase for high throughput
    shutdown_timeout=10.0
)

bq_logging_plugin = BigQueryAgentAnalyticsPlugin(
    project_id=PROJECT_ID,
    dataset_id=DATASET_ID,
    table_id=AGENT_EVENTS_TABLE_ID,
    config=bq_config,
    location="us"
)

# Export an App instance that includes the root_agent and the required plugins
observability_app = App(
    name="observability_analyst_app",
    root_agent=root_agent,
    plugins=[LoggingPlugin(), bq_logging_plugin]
)
