import logging
import os
from .config import CACHE_TTL
import math

try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider

except ImportError:
    pass # OpenTelemetry is optional

from typing import Optional
from typing_extensions import override
from google.adk.agents import Agent, SequentialAgent
from google.adk.apps import App
from google.adk.plugins import BasePlugin, LoggingPlugin
from google.adk.plugins.bigquery_agent_analytics_plugin import BigQueryLoggerConfig, BigQueryAgentAnalyticsPlugin
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.agents.callback_context import CallbackContext
from google.genai.types import HttpRetryOptions, GenerateContentConfig

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
from .agent_tools.analytics.latency import (
    get_llm_requests,
    get_agent_requests,
    get_tool_requests,
    get_invocation_requests
)

from .config import MODEL_ID, AGENT_NAME, PROJECT_ID, AGENT_DATASET_ID, \
    AGENT_TABLE_ID, OBSERVABILITY_APP_NAME, AGENT_DATASET_LOCATION
from .prompts import (BASE_REPORT_AGENT_PROMPT, FINALIZER_AGENT_PROMPT, ROOT_AGENT_PROMPT, 
                      AUGMENTATION_PROMPT, HOLISTIC_ASSESSMENT_PROMPT)
from .utils.telemetry import setup_telemetry
from .utils.time import set_reference_time, parse_time_range
import json
from datetime import datetime, timezone, timedelta

log_level = os.getenv("LOG_LEVEL", "ERROR").upper()
logger = logging.getLogger(__name__)

setup_telemetry()

from .agent_tools.report_generation.tools import generate_base_report, inject_and_save_report

base_report_agent = Agent(
    name="base_report_agent",
    model=Gemini(model=MODEL_ID, retry_options=api_retry_options),
    instruction=BASE_REPORT_AGENT_PROMPT,
    tools=[generate_base_report],
    output_key="raw_report_data"
)

augmentor_agent = Agent(
    name="augmentor_agent",
    model=Gemini(model=MODEL_ID, retry_options=api_retry_options), # stream=True would interleave
    generate_content_config=GenerateContentConfig(response_mime_type="application/json"),
    instruction=AUGMENTATION_PROMPT,
    tools=[],
    output_key="insights_json_str",
    disallow_transfer_to_peers=True
)

holistic_agent = Agent(
    name="holistic_report_analyst",
    model=Gemini(model=MODEL_ID, retry_options=api_retry_options),
    instruction=HOLISTIC_ASSESSMENT_PROMPT,
    description="A specialized observability analyst equipped with BQ tools to review the entire observability report.",
    tools=[get_llm_requests, get_agent_requests, get_tool_requests, get_invocation_requests],
    output_key="holistic_analysis",
    disallow_transfer_to_peers=True
)

augmentor_and_holistic_swarm = SequentialAgent(
    name="augmentor_and_holistic_swarm",
    sub_agents=[holistic_agent, augmentor_agent],
    description="Analyzes the base report sequentially. First, it generates holistic architecture markup, then uses that to generate JSON insights for the executive summary."
)

finalizer_agent = Agent(
    name="finalizer_agent",
    model=Gemini(model=MODEL_ID, retry_options=api_retry_options),
    instruction=FINALIZER_AGENT_PROMPT,
    tools=[inject_and_save_report]
)

report_generation_workflow = SequentialAgent(
    name="report_generation_workflow",
    sub_agents=[base_report_agent, augmentor_and_holistic_swarm, finalizer_agent],
    description="Full workflow that compiles baseline telemetry data, generates charts, analyzes it concurrently with AI, and saves the final markdown report."
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
    assert kpis, "kpis are not set, config.json is corrupt"

    # Set a rounded reference time to ensure BigQuery caching works
    # Rounding UP to the next multiple of CACHE_TTL ensures identical cacheable strings across executions.
    now = datetime.now(timezone.utc)
    rounded_timestamp = math.ceil(now.timestamp() / CACHE_TTL) * CACHE_TTL
    rounded_now = datetime.fromtimestamp(rounded_timestamp, tz=timezone.utc)
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
        
    kpis_string = _format_kpis_for_prompt(kpis)
    
    hydrated_augmentation_prompt = AUGMENTATION_PROMPT.format(
        time_period=time_period_fixed,
        kpis_string=kpis_string,
        project_id=PROJECT_ID,
        base_report_markdown="{base_report_markdown}", # Keep placeholder for tools.py
        raw_data_json="{raw_data_json}" # Keep placeholder for tools.py
    )
    augmentor_agent.instruction = hydrated_augmentation_prompt
    
    hydrated_holistic_prompt = HOLISTIC_ASSESSMENT_PROMPT.format(
        time_period=time_period_fixed,
        project_id=PROJECT_ID,
        base_report_markdown="{base_report_markdown}", # Keep placeholder for tools.py
        raw_data_json="{raw_data_json}" # Keep placeholder for tools.py
    )
    holistic_agent.instruction = hydrated_holistic_prompt


# Create the Orchestrating Root Agent
root_agent = Agent(
    name=AGENT_NAME,
    model=Gemini(model=MODEL_ID, retry_options=api_retry_options),
    instruction=ROOT_AGENT_PROMPT,
    description="Entry point for the Observability Agent application. "
                "Understands user intent and delegates analysis to specialized subagents.",
    sub_agents=[report_generation_workflow],
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
    dataset_id=AGENT_DATASET_ID,
    table_id=AGENT_TABLE_ID,
    config=bq_config,
    location=AGENT_DATASET_LOCATION
)

class TokenSizeLoggerPlugin(BasePlugin):
    """Custom plugin to log token counts and warnings for large inputs."""

    def __init__(self, name: str = "token_size_logger", threshold_chars: int = 100000):
        super().__init__(name)
        self.threshold_chars = threshold_chars

    def _get_input_size(self, llm_request: LlmRequest) -> int:
        """Estimate input size by counting characters in the prompt."""
        if not llm_request.contents:
             return 0
        total_chars = 0
        for content in llm_request.contents:
            if content.parts:
                for part in content.parts:
                    if part.text:
                        total_chars += len(part.text)
        return total_chars

    @override
    async def before_model_callback(
        self, *, callback_context: CallbackContext, llm_request: LlmRequest
    ) -> Optional[LlmResponse]:
        input_chars = self._get_input_size(llm_request)
        agent_name = callback_context.agent_name
        
        # Log the input size
        self._log(f"🧠 LLM REQUEST (Estimated Input) - Agent: {agent_name}, Chars: {input_chars}")
        
        if input_chars > self.threshold_chars:
            self._log(f"⚠️  WARNING - Large input detected for agent '{agent_name}': {input_chars} chars (> {self.threshold_chars})")
        
        return None

    @override
    async def after_model_callback(
        self, *, callback_context: CallbackContext, llm_response: LlmResponse
    ) -> Optional[LlmResponse]:
        agent_name = callback_context.agent_name
        if llm_response.usage_metadata:
             self._log(f"🧠 LLM RESPONSE (Success) - Agent: {agent_name}")
             self._log(f"   Token Usage - Input: {llm_response.usage_metadata.prompt_token_count}, Output: {llm_response.usage_metadata.candidates_token_count}")
        return None

    @override
    async def on_model_error_callback(
        self,
        *,
        callback_context: CallbackContext,
        llm_request: LlmRequest,
        error: Exception,
    ) -> Optional[LlmResponse]:
        agent_name = callback_context.agent_name
        input_chars = self._get_input_size(llm_request)
        
        self._log(f"🧠 LLM ERROR - Agent: {agent_name}")
        self._log(f"   Error: {error}")
        self._log(f"   Input Size (Estimated Chars): {input_chars}")
        
        if input_chars > self.threshold_chars:
             self._log(f"⚠️  WARNING - Large input during error for agent '{agent_name}': {input_chars} chars (> {self.threshold_chars})")
        
        return None

    def _log(self, message: str) -> None:
        """Internal method to format and print log messages."""
        formatted_message: str = f"\033[93m[{self.name}] {message}\033[0m" # Yellow for warnings/logs
        print(formatted_message)

# Export an App instance that includes the root_agent and the required plugins
observability_app = App(
    name=OBSERVABILITY_APP_NAME,
    root_agent=root_agent,
    plugins=[LoggingPlugin(), bq_logging_plugin]
)
