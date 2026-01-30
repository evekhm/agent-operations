import asyncio
import logging
import os
import sys
import datetime
from dotenv import load_dotenv

# Setup path to import agents
dir_path = os.path.dirname(__file__)
sys.path.append(os.path.join(dir_path, ".."))

from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.adk.plugins.bigquery_agent_analytics_plugin import BigQueryLoggerConfig, BigQueryAgentAnalyticsPlugin
from google.genai import types # Import types for Content
from agents.analytics_agent.prompts import OBSERVABILITY_ANALYST_PROMPT_TEMPLATE
from agents.analytics_agent.config import (
    load_analyst_config, 
    PROJECT_ID, 
    DATASET_ID, 
    AGENT_EVENTS_TABLE_ID
)
from agents.analytics_agent.agent_tools.analytics.latency import (
    get_active_metadata,
    analyze_latency_grouped,
    get_slowest_queries,
    analyze_root_cause
)

# Configure Logging
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

# Load Environment
load_dotenv(os.path.join(dir_path, "../.env"))

async def main():
    print("🤖 Initializing Observability Analyst Agent...")
    
    # Load dynamic config
    config = load_analyst_config()
    kpis = config.get("kpis", {})
    
    agent_kpis = kpis.get("agent", {})
    llm_kpis = kpis.get("llm", {})
    tool_kpis = kpis.get("tool", {})
    
    time_period = config.get("time_period", "24h")
    
    # Hydrate Prompt
    hydrated_prompt = OBSERVABILITY_ANALYST_PROMPT_TEMPLATE.format(
        time_period=time_period,
        agent_mean=agent_kpis.get("mean_latency_target_ms", 1000),
        agent_p95=agent_kpis.get("p95_latency_target_ms", 3000),
        agent_view=agent_kpis.get("view_id", "agent_events_view"),
        llm_mean=llm_kpis.get("mean_latency_target_ms", 500),
        llm_p95=llm_kpis.get("p95_latency_target_ms", 1500),
        llm_view=llm_kpis.get("view_id", "llm_events_view"),
        tool_mean=tool_kpis.get("mean_latency_target_ms", 200),
        tool_p95=tool_kpis.get("p95_latency_target_ms", 1000),
        tool_view=tool_kpis.get("view_id", "tool_events_view")
    )
    
    # Define the Agent
    analyst_agent = Agent(
        name="observability_analyst",
        model="gemini-2.5-pro", # Updated to 2.5 Pro as requested
        instruction=hydrated_prompt,
        tools=[
            get_active_metadata,
            analyze_latency_grouped,
            get_slowest_queries,
            analyze_root_cause
        ]
    )
    
    print("🚀 Starting Autonomous Health Check (24h)...")
    
    # Run the Agent using Runner
    try:
        print("   (Reasoning in progress...)\n")
        response_text = ""
        
        session_service = InMemorySessionService()
        
        # Explicitly create the session first with app_name
        await session_service.create_session(
            user_id="test_user", 
            session_id="test_session_001", 
            app_name="observability_analyst_app"
        )
        
        # Initialize BigQuery Plugin
        bq_config = BigQueryLoggerConfig(
            project_id=PROJECT_ID,
            dataset_id=DATASET_ID,
            table_id=AGENT_EVENTS_TABLE_ID
        )
        bq_plugin = BigQueryAgentAnalyticsPlugin(config=bq_config)
        
        runner = Runner(
            agent=analyst_agent, 
            session_service=session_service, 
            app_name="observability_analyst_app",
            plugins=[bq_plugin]
        )
        
        # Create Content object
        user_msg = types.Content(
            role="user",
            parts=[types.Part(text="Perform a system health check for the last 24h. Follow your workflow: Discover, Analyze, Investigate.")]
        )
        
        # Runner.run_async requires user_id and session_id
        async for event in runner.run_async(
            user_id="test_user", 
            session_id="test_session_001", 
            new_message=user_msg
        ):
            if event.content:
                # Handle Content object
                text_chunk = ""
                if hasattr(event.content, "parts"):
                    for part in event.content.parts:
                        if part.text:
                            text_chunk += part.text
                        elif part.function_call:
                            print(f"\n[Tool Call: {part.function_call.name}]", end="", flush=True)
                # Handle string (legacy fallback)
                elif isinstance(event.content, str):
                    text_chunk = event.content
                
                if text_chunk:
                    print(text_chunk, end="", flush=True)
                    response_text += text_chunk
        
        print("\n\n✅ **Analysis Complete**")
        
        # Save Report
        if response_text.strip():
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            report_path = os.path.join(dir_path, f"../reports/observability_report_{timestamp}.md")
            os.makedirs(os.path.dirname(report_path), exist_ok=True)
            
            with open(report_path, "w") as f:
                f.write(response_text)
            
            print(f"\n📄 Report saved to: {report_path}")
        else:
            print("\n⚠️ No report content generated.")
        
    except Exception as e:
        logger.error(f"Agent execution failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
