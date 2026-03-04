import logging
import os

try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider

except ImportError:
    pass # OpenTelemetry is optional

from google.adk.agents import Agent, SequentialAgent, ParallelAgent
from google.adk.sessions.session import Session
from google.adk.apps import App
from google.adk.plugins import LoggingPlugin
from google.adk.plugins.bigquery_agent_analytics_plugin import BigQueryLoggerConfig, BigQueryAgentAnalyticsPlugin
from google.adk.tools import ToolContext
from google.genai.types import HttpRetryOptions

# Define robust exponential backoff strategy for 429 RESOURCE_EXHAUSTED errors
# Max 5 attempts, starting at 2s, max 60s, base 2 multiplier.
api_retry_options = HttpRetryOptions(
    attempts=5,
    initial_delay=2.0,
    max_delay=60.0,
    exp_base=2.0,
    jitter=0.5,
    http_status_codes=[429, 500, 502, 503, 504]
)

from google.adk.models.google_llm import Gemini
from .agent_tools.analytics.llm_diagnostics import analyze_empty_llm_responses
from .agent_tools.analytics.concurrency import (
    analyze_trace_concurrency,
    # detect_sequential_bottlenecks
)
from .agent_tools.analytics.latency import (
    get_active_metadata,
    analyze_latency_grouped,
    get_llm_requests,
    get_agent_requests,
    get_tool_requests,
    get_invocation_requests,
    analyze_root_cause,
    batch_analyze_root_cause,
    analyze_latency_trend,
    analyze_latency_performance
)
from .agent_tools.analytics.sql import run_sql_query
from .config import MODEL_ID, AGENT_NAME, PROJECT_ID, AGENT_DATASET_ID, \
    AGENT_TABLE_ID, AGENT_VERSION, DATASET_ID, TABLE_ID
from .prompts import (INVOCATION_ANALYST_PROMPT, AGENT_ANALYST_PROMPT, LLM_ANALYST_PROMPT, TOOL_ANALYST_PROMPT,
                      REPORT_CREATOR_PROMPT)
from .utils.telemetry import setup_telemetry
from .utils.time import set_reference_time, parse_time_range
import json
from datetime import datetime, timezone, timedelta

log_level = os.getenv("LOG_LEVEL", "ERROR").upper()
logging.basicConfig(level=getattr(logging, log_level, logging.ERROR))
logger = logging.getLogger(__name__)

setup_telemetry()

# Initialize the exact tools the Observability Playbook Subagent needs
analyst_tools = [
    get_active_metadata,
    analyze_latency_grouped,
    get_llm_requests,
    get_agent_requests,
    get_tool_requests,
    get_invocation_requests,
    analyze_root_cause,
    batch_analyze_root_cause,
    analyze_trace_concurrency,
    analyze_latency_trend,
    # detect_sequential_bottlenecks,
    run_sql_query,
    analyze_latency_performance,
    analyze_empty_llm_responses
]

# Create specialized dimension analysts for Scatter-Gather parallel execution
invocation_analyst = Agent(
    name="invocation_analyst",
    model=Gemini(model=MODEL_ID, retry_options=api_retry_options),
    instruction=INVOCATION_ANALYST_PROMPT,
    description="Analyzes Root Agent performance, trace concurrency, and end-to-end metrics.",
    tools=analyst_tools,
    output_key="invocation_findings",
    disallow_transfer_to_peers=True
)

agent_analyst = Agent(
    name="agent_analyst",
    model=Gemini(model=MODEL_ID, retry_options=api_retry_options),
    instruction=AGENT_ANALYST_PROMPT,
    description="Analyzes Sub-Agent performance and detects sequential bottlenecks.",
    tools=analyst_tools,
    output_key="agent_findings",
    disallow_transfer_to_peers=True
)

llm_analyst = Agent(
    name="llm_analyst",
    model=Gemini(model=MODEL_ID, retry_options=api_retry_options),
    instruction=LLM_ANALYST_PROMPT,
    description="Analyzes LLM performance, token usage, LLM impact on performance, and empty responses.",
    tools=analyst_tools,
    output_key="llm_findings",
    disallow_transfer_to_peers=True
)

tool_analyst = Agent(
    name="tool_analyst",
    model=Gemini(model=MODEL_ID, retry_options=api_retry_options),
    instruction=TOOL_ANALYST_PROMPT,
    description="Analyzes Tool performance, errors, and error impact propagation.",
    tools=analyst_tools,
    output_key="tool_findings",
    disallow_transfer_to_peers=True
)

# Parallel Swarm
playbook_swarm = ParallelAgent(
    name="playbook_swarm",
    sub_agents=[invocation_analyst, agent_analyst, llm_analyst, tool_analyst],
    description="Concurrent swarm of specialists executing deep-dive observability playbooks."
)

def aggregate_parallel_results(agent: Agent = None, context: ToolContext = None, *args, **kwargs):
    """
    Callback to aggregate the results of the parallel swarm into a single string
    that the Report Creator can consume.
    """
    if not agent or not context:
        # Fallback for different call signatures
        if len(args) >= 2:
            agent, context = args[0], args[1]
        else:
             print(f"DEBUG: aggregate_parallel_results called with args={args} kwargs={kwargs}")
             return
             
    session = context.session
    # ParallelAgent results are typically stored in the session state under the agent's name
    # The structure is usually a list of results from sub-agents.

    # Check if we have results in the standard location
    swarm_results = session.state.get(agent.name, {}).get("result", [])

    if not swarm_results:
        # Fallback: check if they are in individual keys (less likely for ParallelAgent but good safety)
        pass

    # Merge them into a single string
    merged_findings = "\n\n".join([str(res) for res in swarm_results if res])

    # Store in the key expected by the prompt
    session.state["playbook_findings"] = merged_findings
    print(f"DEBUG: Aggregated {len(swarm_results)} findings into 'playbook_findings' ({len(merged_findings)} chars).")

    # Ensure all required keys exist to prevent Report Creator crash
    required_keys = ["invocation_findings", "playbook_findings", "llm_findings", "tool_findings"]
    for key in required_keys:
        if key not in session.state:
            session.state[key] = f"**[MISSING DATA]** {key} was not generated due to an analyst failure."
            print(f"DEBUG: Filled missing key '{key}' with fallback message.")

# Attach the callback
playbook_swarm.after_agent_callback = aggregate_parallel_results

# Create the Report Creator Agent that takes findings and structures them into markdown
report_creator_agent = Agent(
    name="report_creator_agent",
    model=Gemini(model=MODEL_ID, retry_options=api_retry_options),
    instruction=lambda: REPORT_CREATOR_PROMPT.replace("<timestamp>", datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')).format(agent_version=AGENT_VERSION, datastore_id=DATASET_ID, table_id=TABLE_ID), # Automatically injects {playbook_findings} and {agent_version}
    description="Reads the raw analytical data collected by the playbook agent and formats it into a highly detailed, professional Markdown report.",
    tools=[],
    output_key="final_report",
    disallow_transfer_to_peers=True
)

# Group the investigator swarm and report creator into a strict sequential pipeline
investigate_and_report_pipeline = SequentialAgent(
    name="investigation_workflow",
    sub_agents=[playbook_swarm, report_creator_agent],
    description="Pipeline that first investigates the system constraints concurrently, ensures data integrity, and then generates a merged report."
)

def _format_kpis_for_prompt(kpis: dict) -> str:
    lines = ["**STATIC KPIs (SLOs)**"]
    for k, v in kpis.items():
        if k == "per_agent":
            lines.append("- Custom per-agent KPIs:")
            for agent_name, agent_kpis in v.items():
                lines.append(f"  - `{agent_name}`:")
                for ak, av in agent_kpis.items():
                    if ak == "latency_target":
                       lines.append(f"    - Target: < {av}s")
                    elif ak == "percentile_target":
                       lines.append(f"    - Level: {av}%")
                    elif ak == "mean_latency_target": # Fallback for old configs
                       lines.append(f"    - Mean Target: {av}s")
                    else:
                       lines.append(f"    - {ak}: {av}")
        else:
            # Handle top-level category KPIs (end_to_end, agent, llm, tool)
            lines.append(f"- {k.upper()} KPIs:")
            if isinstance(v, dict):
                for sub_k, sub_v in v.items():
                    if sub_k == "latency_target":
                        lines.append(f"  - Target: < {sub_v}s")
                    elif sub_k == "percentile_target":
                        lines.append(f"  - Level: {sub_v}%")
                    else:
                        lines.append(f"  - {sub_k}: {sub_v}")
            else:
                 lines.append(f"  - {v}")
    return "\n".join(lines)

def set_playbook_config(time_period: str, baseline_period: str, bucket_size: str, kpis: dict = None,
                        num_slowest_queries: int = 20, num_error_records: int = 10,
                        num_queries_to_analyze_rca: int = 5, config: dict = None):
    """Hydrates the PLAYBOOK_INVESTIGATOR_PROMPT with dynamic values and updates the playbook_agent."""
    if kpis is None:
        from .config import DEFAULT_KPIS
        kpis = DEFAULT_KPIS
    
    if config is None:
        config = {}
        
    # Set a rounded reference time to ensure BigQuery caching works
    # Rounding UP to the next hour to include recently generated data
    now = datetime.now(timezone.utc)
    rounded_now = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    set_reference_time(rounded_now)
    
    # Evaluate time periods into strict 'start to end' strings so they're explicitly documented in the prompt and report
    def evaluate_period(period_str: str) -> str:
        if not period_str:
            return period_str
        try:
            parsed = json.loads(parse_time_range(period_str))
            return f"{parsed['start_date']} to {parsed['end_date']}"
        except Exception:
            return period_str
            
    time_period_fixed = evaluate_period(time_period)
    baseline_period_fixed = evaluate_period(baseline_period)
        
    kpis_string = _format_kpis_for_prompt(kpis)

    
    # Extract global percentile for tool arguments (default to 95.0 if not found)
    kpi_percentile = 95.0
    if "end_to_end" in kpis and isinstance(kpis["end_to_end"], dict):
        kpi_percentile = kpis["end_to_end"].get("percentile_target", 95.0)

    hydrated_invocation_prompt = INVOCATION_ANALYST_PROMPT.format(
        time_period=time_period_fixed,
        baseline_period=baseline_period_fixed,
        bucket_size=bucket_size,
        kpis_string=kpis_string,
        num_slowest_queries=num_slowest_queries,
        num_error_records=num_error_records,
        num_queries_to_analyze_rca=num_queries_to_analyze_rca,
        kpi_percentile=kpi_percentile
    )
    invocation_analyst.instruction = hydrated_invocation_prompt

    hydrated_agent_prompt = AGENT_ANALYST_PROMPT.format(
        time_period=time_period_fixed,
        baseline_period=baseline_period_fixed,
        bucket_size=bucket_size,
        kpis_string=kpis_string,
        num_slowest_queries=num_slowest_queries,
        num_error_records=num_error_records,
        num_queries_to_analyze_rca=num_queries_to_analyze_rca,
        kpi_percentile=kpi_percentile
    )
    agent_analyst.instruction = hydrated_agent_prompt

    hydrated_llm_prompt = LLM_ANALYST_PROMPT.format(
        time_period=time_period_fixed,
        baseline_period=baseline_period_fixed,
        bucket_size=bucket_size,
        kpis_string=kpis_string,
        num_slowest_queries=num_slowest_queries,
        num_error_records=num_error_records,
        num_queries_to_analyze_rca=num_queries_to_analyze_rca,
        kpi_percentile=kpi_percentile
    )
    llm_analyst.instruction = hydrated_llm_prompt

    hydrated_tool_prompt = TOOL_ANALYST_PROMPT.format(
        time_period=time_period_fixed,
        baseline_period=baseline_period_fixed,
        bucket_size=bucket_size,
        kpis_string=kpis_string,
        num_slowest_queries=num_slowest_queries,
        num_error_records=num_error_records,
        num_queries_to_analyze_rca=num_queries_to_analyze_rca,
        kpi_percentile=kpi_percentile
    )
    tool_analyst.instruction = hydrated_tool_prompt

    # Format config for display
    config_str = json.dumps(config, indent=2, default=str)
    
    current_timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')

    hydrated_report_prompt = REPORT_CREATOR_PROMPT.replace("<timestamp>", current_timestamp).replace("<time_range>", time_period_fixed).format(
        playbook_findings="{invocation_findings}\\n\\n{agent_findings}\\n\\n{llm_findings}\\n\\n{tool_findings}",
        kpis_string=kpis_string,
        config_dump=config_str,
        time_period=time_period_fixed,
        agent_version=AGENT_VERSION,
        project_id=PROJECT_ID,
        datastore_id=DATASET_ID,
        table_id=TABLE_ID,
        Level=str(kpi_percentile),
        error_target=str(kpis.get("end_to_end", {}).get("error_target", 5.0))
    )
    report_creator_agent.instruction = hydrated_report_prompt

# Create the Orchestrating Root Agent
root_agent = Agent(
    name=AGENT_NAME,
    model=Gemini(model=MODEL_ID, retry_options=api_retry_options),
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

print(f"AGENT_DATASET_ID={AGENT_DATASET_ID}")
print(f"AGENT_TABLE_ID={AGENT_TABLE_ID}")

bq_logging_plugin = BigQueryAgentAnalyticsPlugin(
    project_id=PROJECT_ID,
    dataset_id=AGENT_DATASET_ID,
    table_id=AGENT_TABLE_ID,
    config=bq_config,
    location="us"
)

# Export an App instance that includes the root_agent and the required plugins
observability_app = App(
    name="observability_analyst_app",
    root_agent=root_agent,
    plugins=[LoggingPlugin(), bq_logging_plugin]
)

def create_augmentor_agent() -> Agent:
    """Creates a specialized agent for augmenting deterministic reports."""
    from .prompts import AUGMENTATION_PROMPT
    
    return Agent(
        name="augmentor_agent",
        model=Gemini(model=MODEL_ID, retry_options=api_retry_options),
        instruction=AUGMENTATION_PROMPT,
        description="Augments existing reports with summaries and recommendations. Can use tools to dig deeper into specific findings.",
        tools=analyst_tools,
        output_key="augmentation_result",
        disallow_transfer_to_peers=True
    )
