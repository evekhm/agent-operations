import asyncio
import datetime
import logging
import os
import sys
import time
import argparse
import json

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
    PROJECT_ID, 
    DATASET_ID, 
    AGENT_EVENTS_TABLE_ID,
    MODEL_ID,
    AGENT_NAME
)
from agents.observability_agent.agent_tools.analytics.latency import (
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
from agents.observability_agent.agent_tools.analytics.concurrency import (
    analyze_trace_concurrency,
    detect_sequential_bottlenecks
)

# Load Environment
load_dotenv(os.path.join(dir_path, "../.env"), override=True)

# Configure Logging
log_level = os.getenv("LOG_LEVEL", "ERROR").upper()
logging.basicConfig(level=getattr(logging, log_level, logging.ERROR))
logger = logging.getLogger(__name__)

def load_analyst_config() -> dict:
    """
    Loads configuration for the Observability Analyst.
    Priority:
    1. CLI Arguments
    2. Env var: LATENCY_ANALYSIS_CONFIG_FILE
    3. Local file: agents/observability_agent/config.json
    4. Default: hardcoded fallback
    """
    config_dict = {}

    # 1. CLI Arguments
    parser = argparse.ArgumentParser(description="Observability Analyst CLI")
    parser.add_argument("--time_period", type=str, help="Time range for Current Reality")
    parser.add_argument("--baseline_period", type=str, help="Time range for Historical Baseline")
    parser.add_argument("--bucket_size", type=str, help="Bucket size for Playbook C")
    parser.add_argument("--playbook", type=str, choices=["overview", "health", "incident", "trend", "latest"], help="Force explicitly route to Playbook overview, health, incident, trend, or latest")
    
    # Parse known args so it doesn't crash if imported elsewhere
    args, _ = parser.parse_known_args(sys.argv[1:])
    if args.time_period: config_dict["time_period"] = args.time_period
    if args.baseline_period: config_dict["baseline_period"] = args.baseline_period
    if args.bucket_size: config_dict["bucket_size"] = args.bucket_size
    if args.playbook: config_dict["playbook"] = args.playbook

    if config_dict:
        return config_dict

    # 2. Try Env Var
    env_path = os.getenv("LATENCY_ANALYSIS_CONFIG_FILE")
    if env_path and os.path.exists(env_path):
        try:
            with open(env_path, 'r') as f:
                logger.info(f"Loaded analyst config from {env_path}")
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load config from {env_path}: {e}")

    # 3. Try Local config.json (relative to this file)
    local_path = os.path.join(os.path.dirname(__file__), "config.json")
    if os.path.exists(local_path):
        try:
            with open(local_path, 'r') as f:
                logger.info(f"Loaded analyst config from {local_path}")
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load config from {local_path}: {e}")

    # 4. Default Fallback
    logger.warning("No config found, using defaults.")
    return {
        "time_period": "7d"
    }


async def main():
    print("🤖 Initializing Observability Analyst Agent...")
    
    # Load dynamic config
    config = load_analyst_config()
    time_period = config.get("time_period", "all")
    baseline_period = config.get("baseline_period", "7d")
    bucket_size = config.get("bucket_size", "1d")
    
    # Hydrate Prompt
    hydrated_prompt = OBSERVABILITY_ANALYST_PROMPT_TEMPLATE.format(
        time_period=time_period,
        baseline_period=baseline_period,
        bucket_size=bucket_size
    )
    
    # Define the Agent
    analyst_agent = Agent(
        name=AGENT_NAME,
        model=MODEL_ID,
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
            analyze_latency_trend,
            detect_sequential_bottlenecks
        ]
    )
    
    print("🚀 Starting Autonomous Health Check...")
    
    # Run the Agent using Runner
    try:
        start_time = time.time()
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
        
        # Inject explicit routing if requested
        playbook = config.get("playbook", "overview")
        if playbook == "overview":
            prompt_injection = "Execute Playbook: overview."
        elif playbook == "health":
            prompt_injection = "Execute Playbook: health."
        elif playbook == "incident":
            prompt_injection = "Execute Playbook: incident."
        elif playbook == "trend":
            prompt_injection = "Execute Playbook: trend."
        elif playbook == "latest":
            prompt_injection = "Execute Playbook: latest."
        else:
            prompt_injection = "Evaluate the current system state. Choose the appropriate Playbook autonomously based on my configured parameters."

        print(f"🎯 Explicit Routing: {prompt_injection}")

        # Create Content object
        user_msg = types.Content(
            role="user",
            parts=[types.Part(text=f"Instructions: {prompt_injection}")]
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
        
        end_time = time.time()
        execution_time = end_time - start_time
        print(f"\n\n✅ **Analysis Complete** (Execution Time: {execution_time:.2f} seconds)")
        
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
