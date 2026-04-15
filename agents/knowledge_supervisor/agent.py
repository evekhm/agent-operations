# Re-export root_agent for `adk web` discovery.
# Agent Engine deployment uses app.agent directly via --adk_app flag.
from .app.agent import root_agent
