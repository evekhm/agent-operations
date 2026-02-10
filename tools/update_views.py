import os
import sys
import logging


project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

logging.basicConfig(level=logging.INFO)

from agents.observability_agent.utils.views import (
    ensure_llm_events_view_exists,
    ensure_tool_events_view_exists,
    ensure_invocation_events_view_exists,
    ensure_agent_events_view_exists
)

print("Updating Views...")
ensure_llm_events_view_exists()
ensure_tool_events_view_exists()
ensure_agent_events_view_exists()
ensure_invocation_events_view_exists()
print("Views Updated.")
