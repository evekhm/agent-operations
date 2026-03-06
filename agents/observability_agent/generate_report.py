import argparse
import asyncio
import json
import logging
import os
import sys
import time
import uuid

from dotenv import load_dotenv

# Setup path to import agents
dir_path = os.path.dirname(__file__)
sys.path.append(os.path.join(dir_path, "../.."))

from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.genai import types
from agents.observability_agent.config import OBSERVABILITY_APP_NAME, DEFAULT_KPIS
from agents.observability_agent.agent import root_agent

# Load Environment
load_dotenv(os.path.join(dir_path, "../../.env"), override=True)

# Configure Logging
log_level = os.getenv("LOG_LEVEL", "ERROR").upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.ERROR),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def load_analyst_config() -> dict:
    config = {
        "time_period": "7d",
        "kpis": DEFAULT_KPIS
    }

    agent_config_path = os.path.join(os.path.dirname(__file__), "config.json")
    if os.path.exists(agent_config_path):
        try:
            with open(agent_config_path, 'r') as f:
                logger.info(f"Loaded analyst config from {agent_config_path}")
                loaded = json.load(f)
                config.update(loaded)
        except Exception as e:
            logger.error(f"Failed to load config from {agent_config_path}: {e}")

    env_path = os.getenv("AGENT_CONFIG_FILE")
    if env_path and os.path.exists(env_path):
        try:
            with open(env_path, 'r') as f:
                logger.info(f"Loaded analyst config from {env_path}")
                loaded = json.load(f)
                config.update(loaded)
        except Exception as e:
            logger.error(f"Failed to load config from {env_path}: {e}")

    parser = argparse.ArgumentParser(description="Observability Analyst CLI")
    parser.add_argument("--time_period", type=str, help="Time range for Current Reality")
    parser.add_argument("--baseline_period", type=str, help="Time range for Historical Baseline")
    parser.add_argument("--bucket_size", type=str, help="Bucket size for Playbook C")
    parser.add_argument("--playbook", type=str, choices=["overview", "health", "incident", "trend", "latest"], help="Force explicitly route to Playbook")
    
    args, _ = parser.parse_known_args(sys.argv[1:])
    
    if args.time_period: config["time_period"] = args.time_period
    if args.baseline_period: config["baseline_period"] = args.baseline_period
    if args.bucket_size: config["bucket_size"] = args.bucket_size
    if args.playbook: config["playbook"] = args.playbook

    return config

async def main():
    print("🤖 Initializing Observability Analyst Agent...")
    config = load_analyst_config()
    if "config" in config:
        config = config["config"]

    if "playbook" not in config: config["playbook"] = "overview"
    
    data_retrieval = config.get("data_retrieval", {})
    time_period = config.get("time_period") or data_retrieval.get("time_period", "7d")
    baseline_period = config.get("baseline_period") or data_retrieval.get("baseline_period", "7d")
    bucket_size = config.get("bucket_size", "1d")
    playbook_name = config.get("playbook", "overview")
    
    print(f"🚀 Starting Autonomous {playbook_name.capitalize()} Report Generation...")
    
    try:
        start_time = time.time()
        
        session_id = f"session_{uuid.uuid4().hex[:8]}"
        user_id = f"user_{uuid.uuid4().hex[:8]}"
        
        session_service = InMemorySessionService()
        await session_service.create_session(session_id=session_id, user_id=user_id, app_name=OBSERVABILITY_APP_NAME)
        
        report_runner = Runner(
            agent=root_agent,
            session_service=session_service,
            app_name=OBSERVABILITY_APP_NAME
        )
        
        prompt = f"Generate an observability {playbook_name} report. Use time_period='{time_period}', baseline_period='{baseline_period}', and bucket_size='{bucket_size}'."
        report_msg = types.Content(role="user", parts=[types.Part(text=prompt)])
        
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
                    
        print(f"\n\n⏱️ Total script execution wall time: {time.time() - start_time:.2f} seconds")
        
    except Exception as e:
        logger.error(f"Agent execution failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
