import asyncio
import datetime
import logging
import os
import sys

from dotenv import load_dotenv

# Setup path to import agents
dir_path = os.path.dirname(__file__)
sys.path.append(os.path.join(dir_path, ".."))

from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.adk.plugins.bigquery_agent_analytics_plugin import BigQueryLoggerConfig, BigQueryAgentAnalyticsPlugin
from google.genai import types # Import types for Content
from agents.observability_agent.prompts import OBSERVABILITY_ANALYST_PROMPT_TEMPLATE
from agents.observability_agent.config import (
    load_analyst_config, 
    PROJECT_ID, 
    DATASET_ID, 
    AGENT_EVENTS_TABLE_ID
)
from agents.observability_agent.agent_tools.analytics.latency import (
    get_active_metadata,
    analyze_latency_grouped,
    get_slowest_queries,
    get_fastest_queries,
    get_failed_queries,
    get_baseline_performance_metrics,
    get_latest_queries,
    analyze_root_cause
)
from agents.observability_agent.agent_tools.analytics.concurrency import (
    analyze_trace_concurrency,
    detect_sequential_bottlenecks
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
    time_period = config.get("time_period", "all")
    
    # Hydrate Prompt
    hydrated_prompt = OBSERVABILITY_ANALYST_PROMPT_TEMPLATE.format(
        time_period=time_period
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
            get_failed_queries,
            get_fastest_queries,
            get_baseline_performance_metrics,
            get_latest_queries,
            analyze_root_cause,
            analyze_trace_concurrency,
            detect_sequential_bottlenecks
        ]
    )
    
    print("🚀 Starting Autonomous Health Check...")
    
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

        bq_config = BigQueryLoggerConfig(
            enabled=True,
            # event_allowlist=["LLM_REQUEST", "LLM_RESPONSE"], # Only log these events
            max_content_length=500 * 1024, # 500 KB limit for inline text
            batch_size=1, # Default is 1 for low latency, increase for high throughput
            shutdown_timeout=10.0
        )


        bq_logging_plugin = BigQueryAgentAnalyticsPlugin(
            project_id=PROJECT_ID,
            dataset_id=DATASET_ID,
            table_id=AGENT_EVENTS_TABLE_ID, # default table name is agent_events_v2
            config=bq_config,
            location="us"
        )
        
        runner = Runner(
            agent=analyst_agent, 
            session_service=session_service, 
            app_name="observability_analyst_app",
            plugins=[bq_logging_plugin]
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
