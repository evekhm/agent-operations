import argparse
import asyncio
import datetime
import json
import logging
import os
import sys
import time
import uuid

from dotenv import load_dotenv

# Setup path to import agents
dir_path = os.path.dirname(__file__)
sys.path.append(os.path.join(dir_path, ".."))

from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.adk.plugins import LoggingPlugin
from google.adk.plugins.bigquery_agent_analytics_plugin import BigQueryLoggerConfig, BigQueryAgentAnalyticsPlugin
from google.genai import types # Import types for Content
from agents.observability_agent.config import (
    PROJECT_ID, 
    DATASET_ID,
    AGENT_TABLE_ID,
    DEFAULT_KPIS
)
# Import the newly refactored root agent and config setter
from agents.observability_agent.agent import root_agent, set_playbook_config

# Load Environment
load_dotenv(os.path.join(dir_path, "../.env"), override=True)

# Configure Logging
log_level = os.getenv("LOG_LEVEL", "ERROR").upper()
logging.basicConfig(level=getattr(logging, log_level, logging.ERROR))
logger = logging.getLogger(__name__)

def load_analyst_config() -> dict:
    """
    Loads configuration for the Observability Analyst.
    Priority (Lowest to Highest):
    1. Default: hardcoded fallback
    2. Local file: agents/observability_agent/config.json
    3. Try Env Var: LATENCY_ANALYSIS_CONFIG_FILE
    4. CLI Arguments
    """
    config = {
        "time_period": "7d",
        "kpis": DEFAULT_KPIS
    }

    # 2. Try Local config.json (relative to this file -> ../agents/observability_agent/config.json)
    # This is the canonical config location for the agent.
    agent_config_path = os.path.join(os.path.dirname(__file__), "../agents/observability_agent/config.json")
    if os.path.exists(agent_config_path):
        try:
            with open(agent_config_path, 'r') as f:
                logger.info(f"Loaded analyst config from {agent_config_path}")
                loaded = json.load(f)
                config.update(loaded)
        except Exception as e:
            logger.error(f"Failed to load config from {agent_config_path}: {e}")

    env_path = os.getenv("LATENCY_ANALYSIS_CONFIG_FILE")
    if env_path and os.path.exists(env_path):
        try:
            with open(env_path, 'r') as f:
                logger.info(f"Loaded analyst config from {env_path}")
                loaded = json.load(f)
                config.update(loaded)
        except Exception as e:
            logger.error(f"Failed to load config from {env_path}: {e}")

    # 4. CLI Arguments
    parser = argparse.ArgumentParser(description="Observability Analyst CLI")
    parser.add_argument("--time_period", type=str, help="Time range for Current Reality")
    parser.add_argument("--baseline_period", type=str, help="Time range for Historical Baseline")
    parser.add_argument("--bucket_size", type=str, help="Bucket size for Playbook C")
    parser.add_argument("--playbook", type=str, choices=["overview", "health", "incident", "trend", "latest"], help="Force explicitly route to Playbook overview, health, incident, trend, or latest")
    
    # Parse known args so it doesn't crash if imported elsewhere
    args, _ = parser.parse_known_args(sys.argv[1:])
    
    if args.time_period: config["time_period"] = args.time_period
    if args.baseline_period: config["baseline_period"] = args.baseline_period
    if args.bucket_size: config["bucket_size"] = args.bucket_size
    if args.playbook: config["playbook"] = args.playbook

    return config


async def main():
    print("🤖 Initializing Observability Analyst Agent...")
    
    # Load dynamic config
    config = load_analyst_config()
    # Support wrapper objects (e.g. nested under "config" block or top-level)
    if "config" in config:
        config = config["config"]

    # LOG THE FINAL CONFIG
    print(f"🔧 Loaded Analyst Config: {json.dumps(config, indent=2, default=str)}")

    time_period = config.get("time_period", "all")
    baseline_period = config.get("baseline_period", "7d")
    bucket_size = config.get("bucket_size", "1d")
    
    # Load KPIs and merge with defaults
    custom_kpis = config.get("kpis", {})
    kpis = DEFAULT_KPIS.copy()
    if isinstance(custom_kpis, dict):
        # Deep merge for per_agent
        if "per_agent" in custom_kpis and "per_agent" in kpis:
            kpis["per_agent"].update(custom_kpis.pop("per_agent"))
        kpis.update(custom_kpis)

    # Hydrate Prompt for the subagent
    set_playbook_config(
        time_period=time_period,
        baseline_period=baseline_period,
        bucket_size=bucket_size,
        kpis=kpis,
        num_slowest_queries=config.get("num_slowest_queries", 5),
        num_error_records=config.get("num_error_queries", 5),
        num_queries_to_analyze_rca=config.get("num_queries_to_analyze_rca", 5),
        config=config
    )
    
    print("🚀 Starting Autonomous Health Check...")
    
    # Run the Agent using Runner
    try:
        start_time = time.time()
        print("   (Reasoning in progress...)\n")
        response_text = ""
        
        session_id = f"session_{uuid.uuid4().hex[:8]}"
        user_id = f"user_{uuid.uuid4().hex[:8]}"
        
        session_service = InMemorySessionService()
        
        initial_state = {
            "playbook_findings": "Error: The playbook investigator agent aborted or failed before it could produce findings."
        }

        # Explicitly create the session first with app_name and initial state
        session = await session_service.create_session(
            user_id=user_id, 
            session_id=session_id, 
            app_name="observability_analyst_app",
            state=initial_state
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
            table_id=AGENT_TABLE_ID,
            config=bq_config,
            location="us"
        )
        
        runner = Runner(
            agent=root_agent, 
            session_service=session_service, 
            app_name="observability_analyst_app",
            plugins=[LoggingPlugin(), bq_logging_plugin]
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
        try:
            async for event in runner.run_async(
                user_id=user_id, 
                session_id=session_id, 
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
        except Exception as e:
            print(f"\n\n⚠️ Playbook execution encountered an error: {e}")
            print("🚀 Generating report from partial findings...")
            from agents.observability_agent.agent import report_creator_agent
            
            report_runner = Runner(
                agent=report_creator_agent,
                session_service=session_service,
                app_name="observability_analyst_app"
            )
            
            # Manually ensure findings keys exist if the swarm crashed
            required_keys = ["invocation_findings", "agent_findings", "llm_findings", "tool_findings"]
            for key in required_keys:
                if key not in session.state:
                    session.state[key] = f"**[ERROR]** {key} could not be generated due to a critical failure in the analysis phase: {e}"
            
            report_msg = types.Content(role="user", parts=[types.Part(text="Generate the final report from the findings gathered so far.")])
            
            async for event in report_runner.run_async(
                user_id=user_id,
                session_id=session_id,
                new_message=report_msg
            ):
                if event.content:
                    text_chunk = ""
                    if hasattr(event.content, "parts"):
                        for part in event.content.parts:
                            if part.text: text_chunk += part.text
                    elif isinstance(event.content, str):
                        text_chunk = event.content
                    if text_chunk:
                        print(text_chunk, end="", flush=True)
                        response_text += text_chunk

        end_time = time.time()
        execution_time = end_time - start_time
        print(f"\n\n✅ **Analysis Complete** (Execution Time: {execution_time:.2f} seconds)")
        
        # Retrieve final explicitly formatted report from state
        session = await session_service.get_session(user_id=user_id,
                                                    session_id=session_id,
                                                    app_name="observability_analyst_app")
        final_report = session.state.get("final_report", response_text)

        # Save Report
        if final_report.strip():
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            report_path = os.path.join(dir_path, f"../reports/observability_{playbook}_report_{timestamp}.md")
            os.makedirs(os.path.dirname(report_path), exist_ok=True)
            
            with open(report_path, "w") as f:
                f.write(final_report)
            
            rel_report_path = os.path.normpath(os.path.relpath(report_path))
            print(f"\n📄 Report saved to: {rel_report_path}")
        else:
            print("\n⚠️ No report content generated.")
        
    except Exception as e:
        logger.error(f"Agent execution failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        from opentelemetry import trace
        provider = trace.get_tracer_provider()
        if hasattr(provider, "force_flush"):
            provider.force_flush(timeout_millis=3000)

if __name__ == "__main__":
    asyncio.run(main())
