import os
from google.adk.agents import Agent
from google.adk.models.google_llm import Gemini
from google.genai.types import HttpRetryOptions

from agents.observability_agent.config import MODEL_ID
from agents.observability_agent.agent_tools.analytics.latency import (
    get_llm_requests,
    get_agent_requests,
    get_tool_requests,
    get_invocation_requests
)
from agents.whole_report_agent.prompts import HOLISTIC_ASSESSMENT_PROMPT

api_retry_options = HttpRetryOptions(
    attempts=5,
    initial_delay=2.0,
    max_delay=60.0,
    exp_base=2.0,
    jitter=0.5,
    http_status_codes=[429, 500, 502, 503, 504]
)

analyst_tools = [
    get_llm_requests,
    get_agent_requests,
    get_tool_requests,
    get_invocation_requests
]

def create_holistic_agent() -> Agent:
    return Agent(
        name="holistic_report_analyst",
        model=Gemini(model=MODEL_ID, retry_options=api_retry_options),
        instruction=HOLISTIC_ASSESSMENT_PROMPT,
        description="A specialized observability analyst equipped with BQ tools to review the entire observability report.",
        tools=analyst_tools,
    )
