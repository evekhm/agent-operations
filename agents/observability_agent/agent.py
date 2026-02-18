import logging
import os

from google.adk.agents import Agent, SequentialAgent
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
    get_latest_queries,
    analyze_root_cause,
    batch_analyze_root_cause,
    analyze_latency_trend,
    get_llm_impact_analysis
)
from .agent_tools.analytics.sql import run_sql_query
from .config import MODEL_ID, AGENT_NAME, PROJECT_ID, DATASET_ID, AGENT_EVENTS_TABLE_ID
from .prompts import PLAYBOOK_INVESTIGATOR_PROMPT, REPORT_CREATOR_PROMPT

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
    get_latest_queries,
    analyze_root_cause,
    batch_analyze_root_cause,
    analyze_trace_concurrency,
    analyze_latency_trend,
    detect_sequential_bottlenecks,
    run_sql_query,
    get_llm_impact_analysis
]

# Create the deep-dive Playbook Investigator Agent
playbook_agent = Agent(
    name="playbook_agent",
    model=MODEL_ID,
    instruction=PLAYBOOK_INVESTIGATOR_PROMPT, # Will be hydrated dynamically
    description="Executes deep-dive observability playbooks (health, incident, overview, trend, latest) on the agent events and telemetry data inside BigQuery. Collects the raw findings.",
    tools=analyst_tools,
    output_key="playbook_findings",
    disallow_transfer_to_peers=True
)

# Create the Report Creator Agent that takes findings and structures them into markdown
report_creator_agent = Agent(
    name="report_creator_agent",
    model=MODEL_ID,
    instruction=REPORT_CREATOR_PROMPT, # Automatically injects {playbook_findings}
    description="Reads the raw analytical data collected by the playbook agent and formats it into a highly detailed, professional Markdown report.",
    tools=[],
    output_key="final_report",
    disallow_transfer_to_peers=True
)

# Group the investigator and report creator into a strict sequential pipeline
investigate_and_report_pipeline = SequentialAgent(
    name="investigation_workflow",
    sub_agents=[playbook_agent, report_creator_agent],
    description="Pipeline that first investigates the system and then generates a report."
)

def _format_kpis_for_prompt(kpis: dict) -> str:
    lines = ["**STATIC KPIs (SLOs)**"]
    for k, v in kpis.items():
        if k == "per_agent":
            lines.append("- Custom per-agent KPIs:")
            for agent_name, agent_kpis in v.items():
                lines.append(f"  - `{agent_name}`:")
                for ak, av in agent_kpis.items():
                    lines.append(f"    - {ak}: {av}s")
        else:
            lines.append(f"- {k}: {v}s")
    return "\n".join(lines)

def set_playbook_config(time_period: str, baseline_period: str, bucket_size: str, kpis: dict = None, num_slowest_queries: int = 20, config: dict = None):
    """Hydrates the PLAYBOOK_INVESTIGATOR_PROMPT with dynamic values and updates the playbook_agent."""
    if kpis is None:
        from .config import DEFAULT_KPIS
        kpis = DEFAULT_KPIS
    
    if config is None:
        config = {}
        
    kpis_string = _format_kpis_for_prompt(kpis)

    hydrated_investigator_prompt = PLAYBOOK_INVESTIGATOR_PROMPT.format(
        time_period=time_period,
        baseline_period=baseline_period,
        bucket_size=bucket_size,
        kpis_string=kpis_string,
        num_slowest_queries=num_slowest_queries
    )
    playbook_agent.instruction = hydrated_investigator_prompt

    # Format config for display
    import json
    config_str = json.dumps(config, indent=2, default=str)

    hydrated_report_prompt = REPORT_CREATOR_PROMPT.format(
        playbook_findings="{playbook_findings}",
        kpis_string=kpis_string,
        config_dump=config_str
    )
    report_creator_agent.instruction = hydrated_report_prompt

# Create the Orchestrating Root Agent
root_agent = Agent(
    name=AGENT_NAME,
    model=MODEL_ID,
    instruction="""
    You are the Observability Root Agent. 
    Your job is to understand the user's operational goal and delegate the analysis to your internal playbook subagent.
    
    If the user asks for a specific playbook (e.g., 'overview', 'health', 'incident', 'trend', or 'latest'), 
    you MUST delegate directly to the `investigation_workflow` pipeline. Pass the user's intent to it so it knows which playbook to execute.
    
    Do NOT attempt to analyze data or write reports yourself. You MUST ALWAYS delegate to your subordinate, the `investigation_workflow`.
    """,
    description="Entry point for the Observability Agent application. Understands user intent and delegates analysis to specialized subagents.",
    sub_agents=[investigate_and_report_pipeline],
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
